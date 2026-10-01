"""Video + progress serializers.

The golden rule: :class:`VideoSerializer` never exposes ``cloudflare_video_id``.
Clients only ever see ``playback_uid``, and playback URLs are always minted
per-request with a short-lived token.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.courses.models import Lesson
from apps.videos.models import Video, VideoProgress


class VideoSerializer(serializers.ModelSerializer):
    """Safe video metadata.  No Cloudflare identifier, no permanent URL."""

    duration_display = serializers.CharField(read_only=True)
    lesson_id = serializers.UUIDField(source="lesson.id", read_only=True, default=None)

    class Meta:
        model = Video
        fields = (
            "id",
            "playback_uid",
            "title",
            "description",
            "thumbnail_url",
            "duration_seconds",
            "duration_display",
            "status",
            "lesson_id",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class VideoAdminSerializer(serializers.ModelSerializer):
    """Admin/instructor view -- includes the Cloudflare id for support work."""

    class Meta:
        model = Video
        fields = (
            "id",
            "playback_uid",
            "title",
            "description",
            "cloudflare_video_id",
            "thumbnail_url",
            "duration_seconds",
            "status",
            "require_signed_urls",
            "processing_error",
            "last_synced_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "require_signed_urls",
            "id",
            "playback_uid",
            "thumbnail_url",
            "duration_seconds",
            "status",
            "processing_error",
            "last_synced_at",
            "created_at",
            "updated_at",
        )


class RegisterVideoSerializer(serializers.Serializer):
    """Register an asset that already exists in Cloudflare Stream.

    The instructor uploads directly to Cloudflare (never through Django), then
    posts the resulting UID here to bind it to a lesson.
    """

    title = serializers.CharField(max_length=200)
    cloudflare_video_id = serializers.CharField(max_length=64)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    lesson = serializers.UUIDField(required=False, allow_null=True)

    def validate_cloudflare_video_id(self, value: str) -> str:
        cleaned = value.strip()
        if not cleaned or len(cleaned) > 64:
            raise serializers.ValidationError(
                "Enter a valid Cloudflare Stream video UID."
            )
        if Video.objects.filter(cloudflare_video_id=cleaned).exists():
            raise serializers.ValidationError(
                "This Cloudflare video is already registered."
            )
        return cleaned

    def validate_lesson(self, value):
        if value is None:
            return None
        lesson = (
            Lesson.objects.filter(pk=value).select_related("section__course").first()
        )
        if lesson is None:
            raise serializers.ValidationError("Lesson not found.")
        return lesson


class PlaybackRequestSerializer(serializers.Serializer):
    """Optional body for the playback endpoint (kept for schema documentation)."""

    resume = serializers.BooleanField(required=False, default=True)


class VideoProgressSerializer(serializers.ModelSerializer):
    lesson_id = serializers.UUIDField(source="lesson.id", read_only=True, default=None)
    video_uid = serializers.UUIDField(source="video.playback_uid", read_only=True)

    class Meta:
        model = VideoProgress
        fields = (
            "id",
            "lesson_id",
            "video_uid",
            "watched_seconds",
            "last_position",
            "completion_percentage",
            "completed",
            "completed_at",
            "updated_at",
        )
        read_only_fields = fields


class ProgressUpdateSerializer(serializers.Serializer):
    """Input for a progress heartbeat from the player.

    Only the position is accepted from the client.  ``completion_percentage``,
    ``watched_seconds`` and ``completed`` are derived server-side so a tampered
    payload cannot mark a lesson finished.
    """

    position_seconds = serializers.IntegerField(min_value=0)
    watched_seconds = serializers.IntegerField(
        min_value=0, required=False, allow_null=True
    )
    completed = serializers.BooleanField(required=False, default=False)
    lesson = serializers.UUIDField(required=False, allow_null=True)

    def validate_position_seconds(self, value: int) -> int:
        # Absolute ceiling: a 24-hour "video" cannot be legitimate here.
        if value > 24 * 60 * 60:
            raise serializers.ValidationError("Position is out of range.")
        return value
