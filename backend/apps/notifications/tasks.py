"""Asynchronous tasks for the notifications app."""

from __future__ import annotations

from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.core.constants import NotificationChannel
from apps.core.logging import get_logger
from apps.notifications.models import Notification
from apps.notifications.services import send_email_now

logger = get_logger(__name__)

# Retry policy: short, bounded backoff.  A permanent SMTP failure should surface
# as a stored error, not an infinite retry loop.
_MAX_ATTEMPTS = 3


@shared_task(bind=True, max_retries=_MAX_ATTEMPTS, default_retry_delay=60)
def send_notification_email(self, notification_id: str) -> bool:
    """Deliver a single queued email notification."""
    try:
        notification = Notification.objects.select_related("user").get(
            pk=notification_id
        )
    except Notification.DoesNotExist:
        logger.warning(
            "Notification not found", extra={"notification_id": notification_id}
        )
        return False

    try:
        return send_email_now(notification)
    except Exception as exc:
        if self.request.retries >= _MAX_ATTEMPTS - 1:
            logger.error(
                "Giving up on notification email",
                extra={
                    "notification_id": notification_id,
                    "attempts": self.request.retries + 1,
                },
            )
            raise
        raise self.retry(exc=exc)


@shared_task
def retry_failed_notification_emails(limit: int = 100) -> int:
    """Retry recent email notifications that never reached a sent state."""
    cutoff = timezone.now() - timedelta(hours=24)
    pending = Notification.objects.filter(
        channel=NotificationChannel.EMAIL,
        sent_at__isnull=True,
        attempts__lt=_MAX_ATTEMPTS,
        created_at__gte=cutoff,
    ).select_related("user")[:limit]

    retried = 0
    for notification in pending:
        try:
            send_email_now(notification)
            retried += 1
        except Exception:  # pragma: no cover - keep the batch running
            logger.exception(
                "Retry failed", extra={"notification_id": str(notification.pk)}
            )
    return retried


# --------------------------------------------------------------------------- #
# WhatsApp
# --------------------------------------------------------------------------- #
@shared_task(bind=True, max_retries=None, acks_late=True)
def send_whatsapp_notification(self, notification_id: str) -> str:
    """Send one WhatsApp notification; retries are bounded by the service."""
    from apps.notifications.whatsapp.service import RetryLater, deliver

    try:
        return deliver(notification_id)
    except RetryLater as later:
        raise self.retry(countdown=later.countdown, exc=None)


@shared_task
def fan_out_live_class_event(event: str, snapshot: dict) -> int:
    from apps.notifications.whatsapp.events import fan_out_live_class_event as run

    return run(event, snapshot)


@shared_task
def dispatch_class_reminders() -> int:
    if not settings.WHATSAPP_ENABLED:
        return 0
    from apps.notifications.whatsapp.events import dispatch_class_reminders as run

    return run()


@shared_task
def sweep_pending_whatsapp(limit: int = 200) -> int:
    """Outbox sweeper: re-dispatch rows whose enqueue was lost, fail abandoned ones."""
    if not settings.WHATSAPP_ENABLED:
        return 0
    from apps.notifications.models import OPEN_STATUSES
    from apps.notifications.whatsapp import service

    service.release_stuck()
    ids = list(
        Notification.objects.filter(
            channel=NotificationChannel.WHATSAPP,
            status__in=OPEN_STATUSES,
            created_at__lt=timezone.now() - timedelta(minutes=2),
        )
        .filter(attempts__lt=settings.WHATSAPP_MAX_ATTEMPTS)
        .order_by("created_at")
        .values_list("pk", flat=True)[:limit]
    )
    for pk in ids:
        service.dispatch(pk)
    return len(ids)


@shared_task
def send_weekly_summaries() -> int:
    if not settings.WHATSAPP_ENABLED:
        return 0
    from apps.notifications.whatsapp.events import send_weekly_summaries as run

    return run()


@shared_task
def send_inactivity_reminders() -> int:
    if not settings.WHATSAPP_ENABLED:
        return 0
    from apps.notifications.whatsapp.events import send_inactivity_reminders as run

    return run()


@shared_task
def send_announcement(title: str, text: str, course_id: str | None, batch_id: str) -> int:
    from apps.notifications.whatsapp.events import send_announcement as run

    return run(title=title, text=text, course_id=course_id, batch_id=batch_id)


@shared_task
def process_incoming_whatsapp(incoming_id: int) -> str:
    from apps.notifications.whatsapp.commands import process_incoming

    return process_incoming(incoming_id)


@shared_task
def cleanup_whatsapp_records() -> dict:
    """Retention: drop old WhatsApp rows, inbound dedupe records and OTPs."""
    from apps.notifications.models import (
        IncomingWhatsAppMessage,
        NotificationAuditLog,
        WhatsAppVerification,
    )

    now = timezone.now()
    deleted_notifications = Notification.objects.filter(
        channel=NotificationChannel.WHATSAPP,
        created_at__lt=now - timedelta(days=settings.WHATSAPP_RETENTION_DAYS),
    ).delete()[0]
    deleted_incoming = IncomingWhatsAppMessage.objects.filter(
        received_at__lt=now - timedelta(days=settings.WHATSAPP_INBOUND_RETENTION_DAYS)
    ).delete()[0]
    deleted_codes = WhatsAppVerification.objects.filter(
        created_at__lt=now - timedelta(days=1)
    ).delete()[0]
    deleted_audit = NotificationAuditLog.objects.filter(
        created_at__lt=now - timedelta(days=365)
    ).delete()[0]
    return {
        "notifications": deleted_notifications,
        "incoming": deleted_incoming,
        "codes": deleted_codes,
        "audit": deleted_audit,
    }
