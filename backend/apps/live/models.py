"""Live classes: scheduled Zoom/Google Meet sessions gated by course entitlement.

Not hosted on this platform -- recorded lessons use Cloudflare Stream, but a
live class is just a meeting link plus a schedule.  Access reuses
``subscriptions.services.can_user_access_course`` (see ``apps/live/services.py``)
instead of inventing a second entitlement check.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class MeetingProvider(models.TextChoices):
    ZOOM = "zoom", _("Zoom")
    GOOGLE_MEET = "google_meet", _("Google Meet")
    OTHER = "other", _("Other")


class LiveClass(models.Model):
    """A scheduled live session for one course."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(
        "courses.Course", on_delete=models.CASCADE, related_name="live_classes"
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    scheduled_start = models.DateTimeField(db_index=True)
    duration_minutes = models.PositiveIntegerField(default=60)

    meeting_provider = models.CharField(
        max_length=20, choices=MeetingProvider.choices, default=MeetingProvider.ZOOM
    )
    meeting_url = models.URLField(max_length=500)

    instructor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="live_classes_hosted",
    )
    is_published = models.BooleanField(default=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("scheduled_start",)
        verbose_name = _("live class")
        verbose_name_plural = _("live classes")
        indexes = [
            models.Index(
                fields=["course", "scheduled_start"], name="liveclass_course_start_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.course.title} -- {self.title}"
