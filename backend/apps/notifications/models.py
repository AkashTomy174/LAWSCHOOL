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


class NotificationStatus(models.TextChoices):
    """Delivery lifecycle of a WhatsApp notification.

    ``accepted`` means Meta's API returned a message id -- it is *not* delivery.
    ``delivered`` / ``read`` only ever come from Meta's status webhook.
    """

    PENDING = "pending", "Pending"
    SCHEDULED = "scheduled", "Scheduled"
    PROCESSING = "processing", "Processing"
    ACCEPTED = "accepted", "Accepted by WhatsApp"
    SENT = "sent", "Sent"
    DELIVERED = "delivered", "Delivered"
    READ = "read", "Read"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"
    SUPPRESSED = "suppressed", "Suppressed"


# Forward-only ordering of provider-confirmed states.  A late webhook must never
# move a notification backwards (e.g. "sent" arriving after "delivered").
STATUS_RANK = {
    NotificationStatus.ACCEPTED: 2,
    NotificationStatus.SENT: 3,
    NotificationStatus.DELIVERED: 4,
    NotificationStatus.READ: 5,
}
OPEN_STATUSES = (NotificationStatus.PENDING, NotificationStatus.SCHEDULED)


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

    # ---- WhatsApp delivery (unused by in-app / email rows) ----------------- #
    status = models.CharField(
        max_length=20,
        choices=NotificationStatus.choices,
        default=NotificationStatus.PENDING,
        db_index=True,
    )
    template_name = models.CharField(max_length=80, blank=True)
    provider_message_id = models.CharField(max_length=200, blank=True, db_index=True)
    # Natural key of the business event ("class_reminder:<id>:<start>:<min>:<user>").
    # Unique, so a duplicate event or a concurrent worker cannot create a second row.
    idempotency_key = models.CharField(
        max_length=200, null=True, blank=True, unique=True
    )
    related_object_type = models.CharField(max_length=40, blank=True)
    related_object_id = models.CharField(max_length=64, blank=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    # Provider "read" receipt (the user may have read receipts turned off).
    provider_read_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.CharField(max_length=40, blank=True)
    last_error_at = models.DateTimeField(null=True, blank=True)

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
            models.Index(
                fields=["channel", "status", "created_at"], name="notif_chan_status_idx"
            ),
            models.Index(
                fields=["related_object_type", "related_object_id"],
                name="notif_related_idx",
            ),
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


class Category(models.TextChoices):
    """User-facing notification categories (one preference toggle each)."""

    LIVE_CLASS = "live_class", "Live classes"
    SCHEDULE_CHANGE = "schedule_change", "Class schedule changes"
    QUIZ_UPDATES = "quiz_updates", "Quiz updates"
    ASSIGNMENT_REMINDERS = "assignment_reminders", "Assignment reminders"
    PROGRESS_UPDATES = "progress_updates", "Learning progress summaries"
    STUDY_REMINDERS = "study_reminders", "Study reminders"
    PAYMENT_UPDATES = "payment_updates", "Subscription and payment updates"
    ANNOUNCEMENTS = "announcements", "Platform announcements"


class ConsentStatus(models.TextChoices):
    NONE = "none", "Not asked"
    OPTED_IN = "opted_in", "Opted in"
    OPTED_OUT = "opted_out", "Opted out"


class NotificationPreference(models.Model):
    """A user's WhatsApp number, consent and per-category switches."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preference",
    )
    # E.164 ("+919876543210").  Only trusted for sending once ``whatsapp_verified_at``
    # is set; a number typed into a profile is never consent.
    whatsapp_number = models.CharField(max_length=20, blank=True)
    whatsapp_verified_at = models.DateTimeField(null=True, blank=True)

    whatsapp_enabled = models.BooleanField(default=False)
    consent_status = models.CharField(
        max_length=12, choices=ConsentStatus.choices, default=ConsentStatus.NONE
    )
    consent_at = models.DateTimeField(null=True, blank=True)
    consent_source = models.CharField(max_length=40, blank=True)
    opted_out_at = models.DateTimeField(null=True, blank=True)

    live_class_enabled = models.BooleanField(default=True)
    schedule_change_enabled = models.BooleanField(default=True)
    quiz_updates_enabled = models.BooleanField(default=True)
    assignment_reminders_enabled = models.BooleanField(default=True)
    progress_updates_enabled = models.BooleanField(default=True)
    study_reminders_enabled = models.BooleanField(default=True)
    payment_updates_enabled = models.BooleanField(default=True)
    announcements_enabled = models.BooleanField(default=True)
    study_reminders_paused_until = models.DateField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("notification preference")
        constraints = [
            # One verified number belongs to exactly one account, so a phone can
            # never be used to reach someone else's data over WhatsApp.
            models.UniqueConstraint(
                fields=["whatsapp_number"],
                condition=models.Q(whatsapp_verified_at__isnull=False),
                name="unique_verified_whatsapp_number",
            ),
        ]

    def __str__(self) -> str:
        return f"prefs({self.user_id})"

    @property
    def is_verified(self) -> bool:
        return bool(self.whatsapp_number and self.whatsapp_verified_at)

    @property
    def can_receive_whatsapp(self) -> bool:
        return (
            self.is_verified
            and self.whatsapp_enabled
            and self.consent_status == ConsentStatus.OPTED_IN
        )

    def allows(self, category: str) -> bool:
        """True when this user may be messaged for ``category`` right now."""
        if not self.can_receive_whatsapp:
            return False
        if category and not getattr(self, f"{category}_enabled", False):
            return False
        if (
            category == Category.STUDY_REMINDERS
            and self.study_reminders_paused_until
            and self.study_reminders_paused_until >= timezone.localdate()
        ):
            return False
        return True


class WhatsAppVerification(models.Model):
    """A pending one-time code proving the user controls a WhatsApp number."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="whatsapp_verifications",
    )
    number = models.CharField(max_length=20)
    code_hash = models.CharField(max_length=64)  # HMAC-SHA256, never the code
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["user", "-created_at"], name="wa_verif_user_idx")]


class ApprovalStatus(models.TextChoices):
    UNKNOWN = "unknown", "Not submitted"
    PENDING = "pending", "Pending Meta review"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class NotificationTemplate(models.Model):
    """Maps an internal template to a Meta template.

    ``approval_status`` is recorded by an administrator after checking Meta's
    dashboard; nothing in this codebase assumes approval.
    """

    internal_name = models.CharField(max_length=60, unique=True)
    provider_template_name = models.CharField(max_length=100)
    language_code = models.CharField(max_length=10, default="en")
    meta_category = models.CharField(
        max_length=20,
        choices=[
            ("utility", "Utility"),
            ("authentication", "Authentication"),
            ("marketing", "Marketing"),
        ],
        default="utility",
    )
    notification_category = models.CharField(
        max_length=30,
        choices=Category.choices,
        blank=True,
        help_text="Preference toggle gating this template. Blank = account/security (consent only).",
    )
    # Ordered variable names; position == {{n}} in the Meta template body.
    variable_schema = models.JSONField(default=list)
    body_preview = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    approval_status = models.CharField(
        max_length=12, choices=ApprovalStatus.choices, default=ApprovalStatus.UNKNOWN
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.internal_name


class IncomingProcessing(models.TextChoices):
    RECEIVED = "received", "Received"
    PROCESSED = "processed", "Processed"
    IGNORED = "ignored", "Ignored"
    FAILED = "failed", "Failed"


class IncomingWhatsAppMessage(models.Model):
    """Dedupe + outcome record for an inbound WhatsApp message.

    The message body is deliberately not stored -- only the recognised command
    keyword -- so chat content never accumulates in our database.
    """

    provider_message_id = models.CharField(max_length=200, unique=True)
    sender_identifier = models.CharField(max_length=30, db_index=True)
    mapped_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    message_type = models.CharField(max_length=30)
    command = models.CharField(max_length=40, blank=True)
    processing_status = models.CharField(
        max_length=12,
        choices=IncomingProcessing.choices,
        default=IncomingProcessing.RECEIVED,
        db_index=True,
    )
    error_code = models.CharField(max_length=40, blank=True)
    received_at = models.DateTimeField(default=timezone.now, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)


class NotificationSettings(models.Model):
    """Singleton (pk=1) of admin-tunable notification behaviour."""

    reminder_offsets_minutes = models.JSONField(
        default=list,
        help_text="Minutes before class start to remind (0 = at start).",
    )
    schedule_notifications_enabled = models.BooleanField(default=True)
    weekly_summary_enabled = models.BooleanField(default=True)
    inactivity_reminders_enabled = models.BooleanField(default=True)
    inactivity_days = models.PositiveSmallIntegerField(default=7)
    inactivity_max_reminders = models.PositiveSmallIntegerField(default=2)
    disabled_templates = models.JSONField(default=list, blank=True)
    send_rate_per_minute = models.PositiveIntegerField(default=600)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("notification settings")
        verbose_name_plural = _("notification settings")

    @classmethod
    def load(cls) -> "NotificationSettings":
        obj, _created = cls.objects.get_or_create(
            pk=1, defaults={"reminder_offsets_minutes": [1440, 30]}
        )
        return obj


class NotificationAuditLog(models.Model):
    """Who did what to notification configuration, consent or delivery."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    subject_user_id = models.CharField(max_length=40, blank=True)
    action = models.CharField(max_length=60, db_index=True)
    detail = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)
