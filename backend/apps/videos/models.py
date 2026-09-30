"""Video metadata and per-student progress.

No video bytes ever live here.  Django stores only the Cloudflare Stream
identifier plus the metadata needed to render a lesson list and to authorize a
playback request:

    Video ── 1:1 ── Lesson
      │
      └──< VideoProgress ── User

``playback_uid`` (a UUID) is what the API exposes publicly; the Cloudflare
``cloudflare_video_id`` is only ever used server-side when minting a signed
token.  That separation means a leaked client payload can never be replayed
against Cloudflare's API.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.constants import VideoStatus


class Video(models.Model):
    """Cloudflare Stream asset metadata."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Public-facing identifier used in URLs so Cloudflare ids never leak outward.
    playback_uid = models.UUIDField(
        default=uuid.uuid4, unique=True, editable=False, db_index=True
    )

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    cloudflare_video_id = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text="Stream video UID returned by the Cloudflare API.",
    )
    # Cloudflare's per-video poster frame; also mirrored on the lesson card.
    thumbnail_url = models.URLField(max_length=500, blank=True)

    duration_seconds = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=VideoStatus.choices,
        default=VideoStatus.PENDING,
        db_index=True,
    )

    # Playback tuning enforced server-side when minting tokens.
    require_signed_urls = models.BooleanField(
        default=True,
        help_text="When true the asset is private and every playback needs a signed token.",
    )
    max_playback_seconds = models.PositiveIntegerField(
        default=0,
        help_text="Optional rating limit for signed tokens (0 = unlimited).",
    )

    # Encoding diagnostics, kept for support without another API round trip.
    processing_error = models.TextField(blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = _("video")
        verbose_name_plural = _("videos")
        indexes = [
            models.Index(
                fields=["status", "created_at"], name="video_status_created_idx"
            ),
            models.Index(fields=["cloudflare_video_id"], name="video_cf_id_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=[s.value for s in VideoStatus]),
                name="video_status_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.cloudflare_video_id})"

    @property
    def is_ready(self) -> bool:
        return self.status == VideoStatus.READY

    @property
    def duration_display(self) -> str:
        minutes, seconds = divmod(self.duration_seconds, 60)
        return f"{minutes}:{seconds:02d}"


class VideoProgress(models.Model):
    """One row per (user, video): resumable playback position and completion.

    A unique constraint on the pair makes the progress endpoint an idempotent
    upsert, so repeated updates from the player never duplicate rows.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="video_progress",
    )
    video = models.ForeignKey(
        Video, on_delete=models.CASCADE, related_name="progress_records"
    )
    # Denormalised for cheap joins on the lesson page and dashboard.
    lesson = models.ForeignKey(
        "courses.Lesson",
        on_delete=models.CASCADE,
        related_name="progress_records",
        null=True,
        blank=True,
    )

    watched_seconds = models.PositiveIntegerField(
        default=0, help_text="Furthest continuous position reached (seconds)."
    )
    last_position = models.PositiveIntegerField(
        default=0, help_text="Where to resume playback (seconds)."
    )
    completion_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    completed = models.BooleanField(default=False, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Cheap anti-abuse signal: how many incremental updates we have accepted.
    update_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ("-updated_at",)
        verbose_name = _("video progress")
        verbose_name_plural = _("video progress")
        constraints = [
            models.UniqueConstraint(
                fields=["user", "video"], name="unique_progress_per_user_video"
            ),
            models.CheckConstraint(
                condition=Q(completion_percentage__gte=0)
                & Q(completion_percentage__lte=100),
                name="progress_percentage_range",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "lesson"], name="progress_user_lesson_idx"),
            models.Index(
                fields=["user", "updated_at"], name="progress_user_recent_idx"
            ),
            models.Index(
                fields=["user", "completed"], name="progress_user_completed_idx"
            ),
            models.Index(
                fields=["video", "completed"], name="progress_video_completed_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} -> {self.video_id} ({self.completion_percentage}%)"

    def mark_completed(self) -> None:
        self.completed = True
        self.completion_percentage = 100
        self.completed_at = timezone.now()


class PlaybackSession(models.Model):
    """Audit + rate-limit trail for issued playback tokens.

    Storing one row per token request gives support a way to answer "who watched
    this and when", and gives security a way to detect token-harvesting patterns.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="playback_sessions",
    )
    video = models.ForeignKey(
        Video, on_delete=models.CASCADE, related_name="playback_sessions"
    )

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    # Short hash of the token, never the token itself.
    token_fingerprint = models.CharField(max_length=64, blank=True)
    expires_at = models.DateTimeField(db_index=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(
                fields=["user", "created_at"], name="playback_user_created_idx"
            ),
            models.Index(
                fields=["video", "created_at"], name="playback_video_created_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} -> {self.video_id} @ {self.created_at:%Y-%m-%d %H:%M}"
