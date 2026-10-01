"""Video API views: playback tokens, progress, and instructor upload helpers."""

from __future__ import annotations

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from django.http import Http404
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.core.logging import get_logger
from apps.core.permissions import (
    IsCourseOwnerOrAdmin,
    IsInstructorOrAdmin,
    is_admin,
    is_schema_generation,
)
from apps.core.exceptions import EntitlementError
from apps.courses.models import Lesson
from apps.subscriptions.services import can_user_access_lesson, can_user_access_video
from apps.videos.models import Video, VideoProgress
from apps.videos.serializers import (
    PlaybackRequestSerializer,
    ProgressUpdateSerializer,
    RegisterVideoSerializer,
    VideoAdminSerializer,
    VideoProgressSerializer,
    VideoSerializer,
)
from apps.videos.services import (
    issue_playback_token,
    register_video,
    update_video_progress,
)

logger = get_logger(__name__)


class VideoListView(generics.ListAPIView):
    """GET /api/v1/videos/ -- instructor/admin asset inventory."""

    serializer_class = VideoAdminSerializer
    permission_classes = [IsInstructorOrAdmin]
    pagination_class = None

    def get_queryset(self):
        queryset = Video.objects.select_related("lesson").order_by("-created_at")
        if not is_admin(self.request):
            queryset = queryset.filter(
                lesson__section__course__instructor=self.request.user
            )
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return queryset


class VideoDetailView(generics.RetrieveAPIView):
    """GET /api/v1/videos/<uuid>/ -- safe metadata (no Cloudflare id)."""

    serializer_class = VideoSerializer
    permission_classes = [IsAuthenticated]
    queryset = Video.objects.select_related("lesson")

    def get_object(self):
        video = get_object_or_404(self.get_queryset(), playback_uid=self.kwargs["uid"])
        # Same entitlement rule as playback; 404 (not 403) so the existence of
        # unpublished or locked material is not disclosed.
        if not can_user_access_video(self.request.user, video):
            raise Http404
        return video


class VideoPlaybackView(APIView):
    """GET /api/v1/videos/<uid>/playback/ -- the protected playback door.

    Order of operations (all server-side):

    1. authenticate (JWT),
    2. ``can_user_access_video`` -> course + lesson + subscription + preview rules,
    3. mint a short-lived Cloudflare Stream signed token,
    4. record the issuing in ``PlaybackSession`` and return the token.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "playback"

    @extend_schema(
        summary="Issue a short-lived signed playback token",
        responses={200: PlaybackRequestSerializer, 403: None, 404: None, 409: None},
    )
    def get(self, request, uid):
        video = get_object_or_404(
            Video.objects.select_related("lesson"), playback_uid=uid
        )
        payload = issue_playback_token(user=request.user, video=video, request=request)
        return Response(payload)


class LessonPlaybackView(APIView):
    """GET /api/v1/videos/lessons/<lesson_id>/playback/ -- convenience for the player."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "playback"

    @extend_schema(
        summary="Issue a playback token for a lesson's video",
        description=(
            "Convenience wrapper used by the player when it knows only the lesson "
            "id. Performs the same authorization sequence as the video playback "
            "endpoint: authenticate -> active subscription -> course entitlement "
            "-> lesson access, and only then mints a short-lived signed token."
        ),
        responses={200: None, 403: None, 409: None, 503: None},
    )
    def get(self, request, lesson_id):
        lesson = get_object_or_404(
            Lesson.objects.select_related("section", "section__course", "video"),
            pk=lesson_id,
        )
        decision = can_user_access_lesson(request.user, lesson)
        if not decision.allowed:
            raise EntitlementError({"detail": decision.detail}, code=decision.reason)
        if lesson.video_id is None:
            raise EntitlementError(
                {"detail": "This lesson has no video attached."}, code="no_video"
            )
        payload = issue_playback_token(
            user=request.user, video=lesson.video, request=request
        )
        return Response(payload)


class VideoProgressUpdateView(APIView):
    """POST /api/v1/videos/<uid>/progress/ -- heartbeat from the player.

    The client sends only a position (every 10-30s, plus on pause/end).  All
    derived numbers are computed server-side.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "progress"

    def post(self, request, uid):
        video = get_object_or_404(
            Video.objects.select_related("lesson"), playback_uid=uid
        )
        serializer = ProgressUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        progress = update_video_progress(
            user=request.user,
            video=video,
            position_seconds=data["position_seconds"],
            watched_seconds=data.get("watched_seconds"),
            completed=data.get("completed", False),
        )

        # Refresh the derived leaderboard row only on completion -- a heartbeat
        # must not trigger a write to another table.
        if progress.completed:
            try:
                from apps.leaderboard.models import refresh_user_leaderboard

                refresh_user_leaderboard(request.user)
            except Exception:  # pragma: no cover - leaderboard is derived data
                logger.exception(
                    "Leaderboard refresh failed",
                    extra={"user_id": str(request.user.pk)},
                )

        return Response(
            VideoProgressSerializer(progress).data, status=status.HTTP_200_OK
        )


class MyProgressView(generics.ListAPIView):
    """GET /api/v1/progress/ -- the student's own progress rows (paginated)."""

    serializer_class = VideoProgressSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if is_schema_generation(self):
            return VideoProgress.objects.none()
        queryset = (
            VideoProgress.objects.filter(user=self.request.user)
            .select_related(
                "video", "lesson", "lesson__section", "lesson__section__course"
            )
            .order_by("-updated_at")
        )
        course_slug = self.request.query_params.get("course")
        if course_slug:
            queryset = queryset.filter(lesson__section__course__slug=course_slug)
        if self.request.query_params.get("completed") == "true":
            queryset = queryset.filter(completed=True)
        return queryset


class CourseProgressView(APIView):
    """GET /api/v1/progress/course/<slug>/ -- aggregate progress for one course."""

    permission_classes = [IsAuthenticated]

    def get(self, request, slug):
        from apps.courses.models import Course

        course = get_object_or_404(Course, slug=slug)
        rows = VideoProgress.objects.filter(
            user=request.user, lesson__section__course=course
        )
        aggregates = rows.aggregate(
            completed_count=Count("id", filter=Q(completed=True)),
            total_tracked=Count("id"),
        )
        total_lessons = Lesson.objects.filter(
            section__course=course, status="published"
        ).count()
        completed = aggregates["completed_count"] or 0
        return Response(
            {
                "course": {
                    "id": str(course.id),
                    "slug": course.slug,
                    "title": course.title,
                },
                "total_lessons": total_lessons,
                "completed_lessons": completed,
                "completion_percentage": (
                    round((completed / total_lessons) * 100, 2)
                    if total_lessons
                    else 0.0
                ),
                "last_watched": (
                    VideoProgressSerializer(
                        rows.select_related("video", "lesson")
                        .order_by("-updated_at")
                        .first()
                    ).data
                    if rows.exists()
                    else None
                ),
            }
        )


class VideoRegisterView(APIView):
    """POST /api/v1/videos/register/ -- bind a Cloudflare asset to a lesson.

    The instructor uploads straight to Cloudflare (``upload-url`` below) so large
    files never touch the Django server or database.
    """

    # IsCourseOwnerOrAdmin supplies the object-level ownership check that
    # ``check_object_permissions`` below relies on (IsInstructorOrAdmin has none).
    permission_classes = [IsCourseOwnerOrAdmin]

    @extend_schema(
        request=RegisterVideoSerializer, responses={201: VideoAdminSerializer}
    )
    def post(self, request):
        serializer = RegisterVideoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        lesson = data.pop("lesson", None)
        if lesson is not None:
            self.check_object_permissions(request, lesson.section.course)

        video = register_video(
            title=data["title"],
            cloudflare_video_id=data["cloudflare_video_id"],
            description=data.get("description", ""),
            require_signed_urls=data.get("require_signed_urls", True),
        )
        if lesson is not None:
            lesson.video = video
            lesson.duration_seconds = video.duration_seconds
            lesson.save(update_fields=["video", "duration_seconds", "updated_at"])

        return Response(
            VideoAdminSerializer(video).data, status=status.HTTP_201_CREATED
        )


class DirectUploadURLView(APIView):
    """POST /api/v1/videos/upload-url/ -- one-time Cloudflare direct-upload URL.

    Returns a URL the browser posts the file to directly.  Keeps multi-gigabyte
    files away from the application server entirely.
    """

    permission_classes = [IsInstructorOrAdmin]

    def post(self, request):
        from apps.videos.cloudflare import CloudflareStreamError, client

        try:
            result = client.create_direct_upload()
        except CloudflareStreamError as exc:
            return Response(
                {
                    "error": {
                        "code": "cloudflare_error",
                        "message": str(exc),
                        "details": None,
                    }
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(
            {
                "upload_url": result.get("uploadURL"),
                "cloudflare_video_id": result.get("uid"),
            }
        )


class VideoSyncView(APIView):
    """POST /api/v1/videos/<uid>/sync/ -- re-pull metadata from Cloudflare."""

    permission_classes = [IsInstructorOrAdmin]

    def post(self, request, uid):
        from apps.videos.services import sync_video_metadata

        video = get_object_or_404(
            Video.objects.select_related("lesson__section__course"), playback_uid=uid
        )
        lesson = getattr(video, "lesson", None)
        owns = lesson is not None and (
            lesson.section.course.instructor_id == request.user.pk
        )
        if not (is_admin(request) or owns):
            raise Http404
        video = sync_video_metadata(video)
        return Response(VideoAdminSerializer(video).data)
