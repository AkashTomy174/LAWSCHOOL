"""Course, section and lesson API views.

Views orchestrate: they select objects, delegate authorization to permission
classes and the entitlement service, then serialize.  No business rules live here.
"""

from __future__ import annotations

from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import (
    IsAdminRole,
    IsCourseOwnerOrAdmin,
    IsInstructorOrAdmin,
    is_admin,
)
from apps.courses import selectors
from apps.courses.models import Course, CourseStatus, Lesson, Section
from apps.courses.serializers import (
    CourseDetailSerializer,
    CourseListSerializer,
    CourseWriteSerializer,
    LessonListSerializer,
    LessonWriteSerializer,
    SectionWriteSerializer,
)
from apps.subscriptions.services import accessible_course_ids, can_user_access_course


# --------------------------------------------------------------------------- #
# Shared context helpers
# --------------------------------------------------------------------------- #
def _visible_course_or_404(request, slug) -> Course:
    """Course by slug with its tree prefetched; 404 unless the caller may see it."""
    course = selectors.course_detail(slug, user=request.user)
    if course is None:
        raise Http404
    return course


def _progress_context(user, courses) -> dict:
    """Bulk-load completion state for one page of courses.

    Deliberately takes the *page*, not the whole table: progress is then computed
    with a constant number of aggregate queries rather than one per course.
    """
    if not user or not user.is_authenticated:
        return {
            "course_progress": {},
            "completed_lesson_ids": set(),
            "accessible_course_ids": set(),
        }

    from apps.videos.models import VideoProgress

    course_ids = [course.id for course in courses]
    # Scoped to the courses on this page; an unscoped query would load every
    # completed lesson the user has ever finished.
    completed = set(
        VideoProgress.objects.filter(
            user=user, completed=True, lesson__section__course_id__in=course_ids
        ).values_list("lesson_id", flat=True)
    )
    totals = dict(
        Lesson.objects.filter(section__course_id__in=course_ids, status="published")
        .values_list("section__course_id")
        .annotate(total=Count("id"))
    )
    done = dict(
        VideoProgress.objects.filter(
            user=user, completed=True, lesson__section__course_id__in=course_ids
        )
        .values_list("lesson__section__course_id")
        .annotate(total=Count("id", distinct=True))
    )
    course_progress = {
        course_id: round(min(100.0, (done.get(course_id, 0) / total) * 100), 2)
        for course_id, total in totals.items()
        if total
    }
    return {
        "course_progress": course_progress,
        "completed_lesson_ids": completed,
        "accessible_course_ids": accessible_course_ids(user),
    }


def _course_detail_context(request, course) -> dict:
    """Context for the course page: lock flags + completion flags."""
    lessons = selectors.lessons_for_course(course)
    user = request.user
    decision = can_user_access_course(user, course)

    locked_ids = set()
    if not decision.allowed:
        locked_ids = {lesson.id for lesson in lessons if not lesson.is_preview}

    context = _progress_context(user, [course])
    context.update(
        {
            "accessible_course_ids": {course.id} if decision.allowed else set(),
            "locked_lesson_ids": locked_ids,
            "access_decision": decision,
        }
    )
    return context


# --------------------------------------------------------------------------- #
# Courses
# --------------------------------------------------------------------------- #
class CourseListView(generics.ListCreateAPIView):
    """GET /api/v1/courses/ (public catalogue) · POST (instructors and admins).

    An instructor can only create courses under their own name (the serializer
    enforces it) and they start as drafts; only an admin publishes.
    """

    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["level", "language"]
    search_fields = ["title", "summary", "description"]
    ordering_fields = ["published_at", "price", "title"]
    ordering = ["-published_at"]

    def get_serializer_class(self):
        return (
            CourseWriteSerializer
            if self.request.method == "POST"
            else CourseListSerializer
        )

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsInstructorOrAdmin()]
        return super().get_permissions()

    def perform_create(self, serializer):
        if is_admin(self.request):
            serializer.save()
        else:
            serializer.save(instructor=self.request.user, status=CourseStatus.DRAFT)

    def get_queryset(self):
        search = self.request.query_params.get("search")
        scope = self.request.query_params.get("scope")
        # ?scope=mine: only courses the caller teaches (drafts included).
        if scope == "mine":
            if not self.request.user.is_authenticated:
                return Course.objects.none()
            return selectors.all_courses_for_staff(
                self.request.user,
                status=self.request.query_params.get("status"),
                search=search,
            ).filter(instructor=self.request.user)
        # ?scope=all adds whatever drafts the caller may see (none for students).
        if scope == "all":
            return selectors.all_courses_for_staff(
                self.request.user,
                status=self.request.query_params.get("status"),
                search=search,
            )
        return selectors.published_courses(search=search)

    def list(self, request, *args, **kwargs):
        """Paginate first, then compute progress for that page only."""
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        courses = page if page is not None else list(queryset)
        context = {
            **self.get_serializer_context(),
            **_progress_context(request.user, courses),
        }
        serializer = self.get_serializer_class()(courses, many=True, context=context)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)


class CourseDetailView(generics.RetrieveUpdateAPIView):
    """GET /api/v1/courses/<slug>/ -- public metadata; writes are admin-only."""

    lookup_field = "slug"
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_serializer_class(self):
        if self.request.method in {"PATCH", "PUT"}:
            return CourseWriteSerializer
        return CourseDetailSerializer

    def get_permissions(self):
        if self.request.method in {"PATCH", "PUT"}:
            return [IsAdminRole()]
        return super().get_permissions()

    def get_queryset(self):
        return selectors.visible_courses(self.request.user)

    def get_object(self):
        course = _visible_course_or_404(self.request, self.kwargs["slug"])
        self.check_object_permissions(self.request, course)
        return course

    def retrieve(self, request, *args, **kwargs):
        course = self.get_object()
        serializer = self.get_serializer_class()(
            course,
            context=_course_detail_context(request, course)
            | self.get_serializer_context(),
        )
        return Response(serializer.data)


class CourseLessonListView(APIView):
    """GET /api/v1/courses/<slug>/lessons/ -- flat list for the player sidebar.

    Returns lock/completion flags but **no** video playback data.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="List a course's lessons with lock and completion flags",
        description=(
            "Returns lesson metadata only. Locked lessons report ``is_locked: true`` "
            "and never carry playback data; use ``/api/v1/videos/<uid>/playback/`` "
            "after entitlements are confirmed."
        ),
        parameters=[OpenApiParameter("slug", str, OpenApiParameter.PATH)],
        responses={200: LessonListSerializer(many=True)},
    )
    def get(self, request, slug):
        course = _visible_course_or_404(request, slug)
        lessons = selectors.lessons_for_course(course)
        decision = can_user_access_course(request.user, course)
        context = _progress_context(request.user, [course])
        context["locked_lesson_ids"] = (
            set()
            if decision.allowed
            else {lesson.id for lesson in lessons if not lesson.is_preview}
        )
        serializer = LessonListSerializer(lessons, many=True, context=context)
        return Response(
            {
                "course": {
                    "id": str(course.id),
                    "slug": course.slug,
                    "title": course.title,
                },
                "access": {
                    "allowed": decision.allowed,
                    "reason": decision.reason,
                    "detail": decision.detail,
                },
                "lessons": serializer.data,
            }
        )


class CourseAccessCheckView(APIView):
    """GET /api/v1/courses/<slug>/access/ -- entitlement answer for the UI."""

    permission_classes = [IsAuthenticatedOrReadOnly]

    @extend_schema(
        summary="Check course access for the current user",
        parameters=[OpenApiParameter("slug", str, OpenApiParameter.PATH)],
        responses={200: None},
    )
    def get(self, request, slug):
        course = _visible_course_or_404(request, slug)
        decision = can_user_access_course(request.user, course)
        return Response(
            {
                "course": {
                    "id": str(course.id),
                    "slug": course.slug,
                    "title": course.title,
                },
                "allowed": decision.allowed,
                "reason": decision.reason,
                "detail": decision.detail,
            },
            status=status.HTTP_200_OK,
        )


# --------------------------------------------------------------------------- #
# Sections & lessons (authoring surface)
# --------------------------------------------------------------------------- #
class SectionListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/v1/sections/?course=<slug>.

    ``IsCourseOwnerOrAdmin`` is used rather than the role-only permission so an
    instructor cannot add sections to a course they do not own.
    """

    serializer_class = SectionWriteSerializer
    permission_classes = [IsCourseOwnerOrAdmin]

    def get_queryset(self):
        queryset = Section.objects.select_related("course").order_by("ordering")
        course_slug = self.request.query_params.get("course")
        if course_slug:
            queryset = queryset.filter(course__slug=course_slug)
        if not is_admin(self.request):
            queryset = queryset.filter(course__instructor=self.request.user)
        return queryset

    def perform_create(self, serializer):
        # Object-level guard: instructors cannot add sections to others' courses.
        self.check_object_permissions(self.request, serializer.validated_data["course"])
        serializer.save()


class SectionDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /api/v1/sections/<uuid>/."""

    serializer_class = SectionWriteSerializer
    permission_classes = [IsCourseOwnerOrAdmin]

    def get_queryset(self):
        queryset = Section.objects.select_related("course")
        if not is_admin(self.request):
            queryset = queryset.filter(course__instructor=self.request.user)
        return queryset

    def perform_update(self, serializer):
        # Moving a section needs ownership of the destination course too.
        if "course" in serializer.validated_data:
            self.check_object_permissions(
                self.request, serializer.validated_data["course"]
            )
        serializer.save()


class LessonListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/v1/lessons/

    Filters: ``section=<uuid>``, ``course=<slug>``, ``without_video=true`` and
    ``search=<text>`` (lesson or course title).  The order is total so page
    boundaries never skip or repeat a lesson.
    """

    serializer_class = LessonWriteSerializer
    permission_classes = [IsCourseOwnerOrAdmin]

    def get_queryset(self):
        queryset = Lesson.objects.select_related(
            "section", "section__course", "video", "quiz"
        ).order_by("section__course__title", "section__ordering", "ordering", "id")
        section_id = self.request.query_params.get("section")
        if section_id:
            queryset = queryset.filter(section_id=section_id)
        course_slug = self.request.query_params.get("course")
        if course_slug:
            queryset = queryset.filter(section__course__slug=course_slug)
        if self.request.query_params.get("without_video") == "true":
            queryset = queryset.filter(video__isnull=True)
        search = self.request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) | Q(section__course__title__icontains=search)
            )
        if not is_admin(self.request):
            queryset = queryset.filter(section__course__instructor=self.request.user)
        return queryset

    def perform_create(self, serializer):
        self.check_object_permissions(
            self.request, serializer.validated_data["section"].course
        )
        serializer.save()


class LessonDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /api/v1/lessons/<uuid>/."""

    serializer_class = LessonWriteSerializer
    permission_classes = [IsCourseOwnerOrAdmin]

    def get_queryset(self):
        queryset = Lesson.objects.select_related(
            "section", "section__course", "video", "quiz"
        )
        if not is_admin(self.request):
            queryset = queryset.filter(section__course__instructor=self.request.user)
        return queryset

    def perform_update(self, serializer):
        # Moving a lesson needs ownership of the destination section's course too.
        if "section" in serializer.validated_data:
            self.check_object_permissions(
                self.request, serializer.validated_data["section"].course
            )
        serializer.save()


class LessonWatchView(APIView):
    """GET /api/v1/lessons/<uuid>/watch/ -- everything the player needs to start.

    Returns lesson metadata, the *authorization decision*, and -- only when access
    is allowed -- a freshly minted playback token.  This is the single entry point
    the video player uses, so there is no path that renders a video without an
    entitlement check.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        lesson = selectors.lesson_with_context(pk)
        if lesson is None:
            return Response(
                {
                    "error": {
                        "code": "not_found",
                        "message": "Lesson not found.",
                        "details": None,
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        from apps.subscriptions.services import can_user_access_lesson

        decision = can_user_access_lesson(request.user, lesson)
        if decision.reason in {"lesson_unavailable", "not_published"}:
            # Draft lessons / courses do not exist as far as students can tell.
            raise Http404
        payload = {
            "lesson": {
                "id": str(lesson.id),
                "title": lesson.title,
                "description": lesson.description,
                "duration_seconds": lesson.duration_seconds,
                "is_preview": lesson.is_preview,
                "ordering": lesson.ordering,
            },
            "course": {
                "id": str(lesson.section.course_id),
                "slug": lesson.section.course.slug,
                "title": lesson.section.course.title,
            },
            "access": {
                "allowed": decision.allowed,
                "reason": decision.reason,
                "detail": decision.detail,
            },
            "playback": None,
        }

        if not decision.allowed:
            # Explicitly no playback key: locked content never carries video data.
            return Response(payload, status=status.HTTP_403_FORBIDDEN)

        if lesson.video_id:
            # Only the identifier: the player fetches its signed token from
            # /videos/<uid>/playback/, so this page load neither mints a token nor
            # spends the student's playback budget.
            video = lesson.video
            payload["playback"] = {
                "video_uid": str(video.playback_uid),
                "status": video.status,
                "thumbnail_url": video.thumbnail_url,
                "duration_seconds": video.duration_seconds,
            }
        return Response(payload)


class InstructorDashboardView(APIView):
    """GET /api/v1/courses/instructor/dashboard/ -- teaching overview.

    Instructors see their own courses; admins see every course.  "Students" are
    learners with recorded activity (video progress or a quiz attempt) in the
    course: there is no enrolment table, access comes from subscriptions.
    """

    permission_classes = [IsCourseOwnerOrAdmin]

    @extend_schema(responses={200: dict})
    def get(self, request):
        from django.db.models import Avg, Count, Q
        from django.utils import timezone

        from apps.live.models import LiveClass
        from apps.quizzes.models import QuizAttempt
        from apps.videos.models import VideoProgress

        courses = Course.objects.order_by("title")
        if not is_admin(request):
            courses = courses.filter(instructor=request.user)
        courses = list(courses)
        course_ids = [c.pk for c in courses]
        owners = {c.pk: c.instructor_id for c in courses}

        progress = VideoProgress.objects.filter(lesson__section__course_id__in=course_ids)
        attempts = QuizAttempt.objects.filter(
            quiz__course_id__in=course_ids, submitted_at__isnull=False
        )

        students: dict = {cid: set() for cid in course_ids}
        for cid, uid in progress.values_list("lesson__section__course_id", "user_id").distinct():
            students[cid].add(uid)
        for cid, uid in attempts.values_list("quiz__course_id", "user_id").distinct():
            students[cid].add(uid)
        for cid in course_ids:  # the teacher's own activity is not a student's
            students[cid].discard(owners[cid])

        completed = dict(
            progress.filter(completed=True)
            .values_list("lesson__section__course_id")
            .annotate(n=Count("pk"))
        )
        quiz_stats = {
            row["quiz__course_id"]: row
            for row in attempts.values("quiz__course_id").annotate(
                n=Count("pk"),
                avg=Avg("percentage"),
                passed=Count("pk", filter=Q(passed=True)),
            )
        }
        lesson_stats = {
            row["lesson_id"]: row
            for row in progress.values("lesson_id").annotate(
                watchers=Count("user", distinct=True),
                done=Count("pk", filter=Q(completed=True)),
            )
        }
        lessons_by_course: dict = {cid: [] for cid in course_ids}
        for lesson in Lesson.objects.filter(section__course_id__in=course_ids).select_related(
            "section"
        ).order_by("section__ordering", "ordering"):
            stat = lesson_stats.get(lesson.pk, {})
            lessons_by_course[lesson.section.course_id].append(
                {
                    "id": str(lesson.pk),
                    "title": lesson.title,
                    "status": lesson.status,
                    "watchers": stat.get("watchers", 0),
                    "completed": stat.get("done", 0),
                }
            )

        course_rows = []
        for c in courses:
            lessons = lessons_by_course[c.pk]
            n_students = len(students[c.pk])
            slots = n_students * len(lessons)
            q = quiz_stats.get(c.pk)
            course_rows.append(
                {
                    "id": str(c.pk),
                    "slug": c.slug,
                    "title": c.title,
                    "status": c.status,
                    "lesson_count": len(lessons),
                    "student_count": n_students,
                    # completed lesson-views over (students x lessons)
                    "completion_percent": round(100 * completed.get(c.pk, 0) / slots) if slots else 0,
                    "quiz_attempts": q["n"] if q else 0,
                    "avg_quiz_percent": round(float(q["avg"]), 1) if q else None,
                    "pass_rate_percent": round(100 * q["passed"] / q["n"]) if q else None,
                    "lessons": lessons,
                }
            )

        all_students = set().union(*students.values()) if students else set()
        total_attempts = sum(r["quiz_attempts"] for r in course_rows)
        total_passed = sum(row["passed"] for row in quiz_stats.values())
        overall_avg = attempts.aggregate(a=Avg("percentage"))["a"]

        upcoming = (
            LiveClass.objects.filter(course_id__in=course_ids, scheduled_start__gte=timezone.now())
            .select_related("course")
            .order_by("scheduled_start")[:6]
        )
        recent = (
            attempts.select_related("user", "quiz", "quiz__course").order_by("-submitted_at")[:8]
        )

        return Response(
            {
                "totals": {
                    "courses": len(courses),
                    "published_courses": sum(c.status == "published" for c in courses),
                    "students": len(all_students),
                    "quiz_attempts": total_attempts,
                    "avg_quiz_percent": round(float(overall_avg), 1) if overall_avg is not None else None,
                    "pass_rate_percent": round(100 * total_passed / total_attempts) if total_attempts else None,
                },
                "courses": course_rows,
                "upcoming_live_classes": [
                    {
                        "id": str(lc.pk),
                        "title": lc.title,
                        "course_title": lc.course.title,
                        "scheduled_start": lc.scheduled_start,
                        "duration_minutes": lc.duration_minutes,
                        "provider": lc.meeting_provider,
                        "is_published": lc.is_published,
                    }
                    for lc in upcoming
                ],
                "recent_attempts": [
                    {
                        "id": str(a.pk),
                        "student": a.user.name,
                        "quiz": a.quiz.title,
                        "course_title": a.quiz.course.title,
                        "percentage": float(a.percentage),
                        "passed": a.passed,
                        "submitted_at": a.submitted_at,
                    }
                    for a in recent
                ],
            }
        )
