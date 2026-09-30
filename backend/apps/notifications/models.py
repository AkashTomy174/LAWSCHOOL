"""Notification records.

A single table backs both channels: an in-app row is the durable record, and the
email is a delivery attempt against it.  That means "did we email them?" is a
column, not a separate log, and the UI can show the same history the user got by
email.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.constants import NotificationChannel, NotificationKind


class Notification(models.Model):
    """One message to one user on one channel."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    kind = models.CharField(
        max_length=40, choices=NotificationKind.choices, db_index=True
    )
    channel = models.CharField(
        max_length=20, choices=NotificationChannel.choices, db_index=True
    )

    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    # Deep link the SPA can navigate to (e.g. /subscription).
    action_url = models.CharField(max_length=300, blank=True)
    # Template context, retained so a failed send can be retried verbatim.
    context = models.JSONField(default=dict, blank=True)

    read_at = models.DateTimeField(null=True, blank=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivery_error = models.TextField(blank=True)
    attempts = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = _("notification")
        verbose_name_plural = _("notifications")
        indexes = [
            # The unread-badge query: (user, channel, unread) is served directly.
            models.Index(
                fields=["user", "channel", "read_at"], name="notif_user_unread_idx"
            ),
            models.Index(fields=["user", "-created_at"], name="notif_user_created_idx"),
            models.Index(fields=["kind", "created_at"], name="notif_kind_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} {self.kind} ({self.channel})"

    @property
    def is_read(self) -> bool:
        return self.read_at is not None

    def mark_read(self) -> None:
        if self.read_at is None:
            self.read_at = timezone.now()
            self.save(update_fields=["read_at"])

    def mark_sent(self) -> None:
        self.sent_at = timezone.now()
        self.attempts += 1
        self.save(update_fields=["sent_at", "attempts"])

    def mark_failed(self, error: str) -> None:
        self.attempts += 1
        self.delivery_error = error[:1000]
        self.save(update_fields=["attempts", "delivery_error"])
