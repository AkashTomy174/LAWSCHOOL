"""Asynchronous tasks for the notifications app."""

from __future__ import annotations

from datetime import timedelta

from celery import shared_task

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
    from django.utils import timezone

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
