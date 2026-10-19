"""WhatsApp notification service: persist -> enqueue -> deliver -> track.

Flow::

    enqueue()  --(row, unique idempotency key)-->  Notification(pending)
        -> Celery send task -> deliver() -> client.send_template()
        -> Notification(accepted, provider_message_id)
        -> Meta status webhook -> apply_status_event() -> sent/delivered/read/failed

``deliver`` never holds a database transaction or lock across the HTTP call: the
row is *claimed* with a single conditional UPDATE, then released.
"""

from __future__ import annotations

import random
import time
from datetime import timedelta
from functools import partial

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from apps.core.constants import NotificationChannel
from apps.core.logging import get_logger
from apps.notifications.models import (
    OPEN_STATUSES,
    STATUS_RANK,
    ApprovalStatus,
    Notification,
    NotificationAuditLog,
    NotificationPreference,
    NotificationSettings,
    NotificationStatus,
    NotificationTemplate,
)
from apps.notifications.whatsapp import client
from apps.notifications.whatsapp.templates import (
    SPECS,
    TemplateVariableError,
    build_params,
)

logger = get_logger(__name__)

S = NotificationStatus

# Templates whose content depends on live-class state that can change after queueing.
_STALE_CHECKED = {"live_class_reminder"}
# A claimed row older than this was abandoned by a dead worker.
STUCK_AFTER = timedelta(minutes=10)


class RetryLater(Exception):
    """Raised by :func:`deliver` when the task should be retried."""

    def __init__(self, countdown: int):
        super().__init__(f"retry in {countdown}s")
        self.countdown = countdown


def audit(actor, action: str, *, subject=None, **detail) -> None:
    NotificationAuditLog.objects.create(
        actor=actor if getattr(actor, "pk", None) else None,
        subject_user_id=str(getattr(subject, "pk", subject or "")),
        action=action,
        detail=detail,
    )


def display_name(user) -> str:
    return (user.name or "").split(" ")[0] or "there"


# --------------------------------------------------------------------------- #
# Enqueue
# --------------------------------------------------------------------------- #
def enqueue(
    *,
    user,
    template: str,
    variables: dict,
    key: str,
    related: tuple[str, object] = ("", ""),
    scheduled_at=None,
    prefs: NotificationPreference | None = None,
) -> Notification | None:
    """Persist one WhatsApp notification and queue its delivery.

    Returns ``None`` -- without raising -- when WhatsApp is off, the user has not
    consented or has switched the category off, or the template is disabled.  A
    duplicate ``key`` returns the existing row and queues nothing.
    """
    if not settings.WHATSAPP_ENABLED:
        return None
    spec = SPECS[template]  # unknown template == programmer error
    if template in NotificationSettings.load().disabled_templates:
        return None
    if not getattr(user, "is_active", False):
        return None
    if prefs is None:
        prefs = NotificationPreference.objects.filter(user=user).first()
    if prefs is None or not prefs.allows(spec.category):
        return None
    build_params(spec, variables)  # fail fast on bad variables

    notification, created = Notification.objects.get_or_create(
        idempotency_key=key,
        defaults={
            "user": user,
            "kind": template,
            "channel": NotificationChannel.WHATSAPP,
            "title": template,
            "template_name": template,
            "context": variables,
            "related_object_type": related[0],
            "related_object_id": str(related[1]),
            "scheduled_at": scheduled_at,
            "status": S.PENDING,
        },
    )
    if created:
        transaction.on_commit(partial(dispatch, notification.pk))
    return notification


def dispatch(notification_id) -> None:
    """Hand a row to Celery.  If the broker is down the sweeper re-dispatches it."""
    try:
        from apps.notifications.tasks import send_whatsapp_notification

        send_whatsapp_notification.delay(str(notification_id))
    except Exception:
        logger.warning(
            "Could not queue WhatsApp send; sweeper will retry",
            extra={"notification_id": str(notification_id)},
        )


def cancel_pending(
    *, related_type: str, related_id, kinds: list[str] | None = None
) -> int:
    """Cancel not-yet-claimed notifications for an object (e.g. a cancelled class)."""
    qs = Notification.objects.filter(
        channel=NotificationChannel.WHATSAPP,
        related_object_type=related_type,
        related_object_id=str(related_id),
        status__in=OPEN_STATUSES,
    )
    if kinds:
        qs = qs.filter(kind__in=kinds)
    return qs.update(status=S.CANCELLED)


# --------------------------------------------------------------------------- #
# Deliver
# --------------------------------------------------------------------------- #
def rate_slot_available() -> bool:
    limit = (
        NotificationSettings.load().send_rate_per_minute
        or settings.WHATSAPP_SEND_RATE_PER_MINUTE
    )
    key = f"wa:rate:{int(time.time() // 60)}"
    try:
        cache.add(key, 0, 120)
        return cache.incr(key) <= limit
    except Exception:  # cache outage: the provider's own limits still apply
        return True


def _stale_reason(notification: Notification) -> str:
    """Why a queued message should no longer go out ('' = still valid)."""
    if notification.template_name not in _STALE_CHECKED:
        return ""
    from apps.live.models import LiveClass

    live = LiveClass.objects.filter(pk=notification.related_object_id).first()
    if live is None or not live.is_published:
        return "class_unavailable"
    if notification.scheduled_at and live.scheduled_start != notification.scheduled_at:
        return "class_rescheduled"
    if live.scheduled_start < timezone.now() - timedelta(minutes=10):
        return "class_started"
    return ""


def _finish(notification: Notification, **fields) -> None:
    Notification.objects.filter(pk=notification.pk).update(**fields)


def _backoff(attempts: int) -> int:
    return min(30 * 2 ** max(attempts - 1, 0), 900) + random.randint(0, 15)


def deliver(notification_id) -> str:
    """Send one queued notification.  Returns an outcome label; may raise RetryLater."""
    if not settings.WHATSAPP_ENABLED:
        return "disabled"

    # Claim: exactly one worker wins this conditional UPDATE.
    claimed = Notification.objects.filter(
        pk=notification_id,
        channel=NotificationChannel.WHATSAPP,
        status__in=OPEN_STATUSES,
    ).update(status=S.PROCESSING, claimed_at=timezone.now())
    if not claimed:
        return "skipped"

    n = Notification.objects.select_related("user").get(pk=notification_id)
    spec = SPECS.get(n.template_name)
    row = NotificationTemplate.objects.filter(
        internal_name=n.template_name, active=True
    ).first()

    def suppress(code: str) -> str:
        _finish(
            n, status=S.SUPPRESSED, last_error_code=code, last_error_at=timezone.now()
        )
        return f"suppressed:{code}"

    if spec is None or row is None:
        return suppress("template_unavailable")
    if (
        row.approval_status != ApprovalStatus.APPROVED
        and not settings.WHATSAPP_ALLOW_UNAPPROVED_TEMPLATES
    ):
        return suppress("template_not_approved")

    prefs = NotificationPreference.objects.filter(user=n.user).first()
    if not n.user.is_active or prefs is None or not prefs.allows(spec.category):
        return suppress("no_consent")
    stale = _stale_reason(n)
    if stale:
        _finish(
            n, status=S.CANCELLED, last_error_code=stale, last_error_at=timezone.now()
        )
        return f"cancelled:{stale}"

    try:
        params = build_params(spec, n.context)
    except TemplateVariableError:
        _finish(
            n,
            status=S.FAILED,
            last_error_code="bad_variables",
            last_error_at=timezone.now(),
        )
        return "failed:bad_variables"

    if not rate_slot_available():
        _finish(n, status=S.PENDING)  # not an attempt: nothing was sent
        raise RetryLater(30 + random.randint(0, 30))

    attempts = n.attempts + 1
    try:
        result = client.send_template(
            prefs.whatsapp_number,
            row.provider_template_name,
            row.language_code,
            params,
        )
    except client.WhatsAppError as exc:
        base = {
            "attempts": attempts,
            "last_error_code": exc.code[:40],
            "last_error_at": timezone.now(),
        }
        if exc.ambiguous and not settings.WHATSAPP_RETRY_AMBIGUOUS:
            # Meta may already have accepted it; resending could duplicate.
            _finish(n, status=S.FAILED, **base)
            logger.warning(
                "WhatsApp send outcome unknown; not retried",
                extra={"notification_id": str(n.pk), "code": exc.code},
            )
            return f"failed:{exc.code}"
        if exc.retryable and attempts < settings.WHATSAPP_MAX_ATTEMPTS:
            _finish(n, status=S.PENDING, **base)
            raise RetryLater(_backoff(attempts)) from None
        _finish(n, status=S.FAILED, **base)
        logger.warning(
            "WhatsApp send failed",
            extra={"notification_id": str(n.pk), "code": exc.code},
        )
        return f"failed:{exc.code}"

    _finish(
        n,
        status=S.ACCEPTED,
        provider_message_id=result.message_id,
        accepted_at=timezone.now(),
        attempts=attempts,
        last_error_code="",
    )
    return "accepted"


def retry_failed(notification: Notification, actor) -> bool:
    """Admin retry.  Only FAILED rows move back to pending; the key is unchanged,
    so a retry can never create a second row."""
    updated = Notification.objects.filter(
        pk=notification.pk, channel=NotificationChannel.WHATSAPP, status=S.FAILED
    ).update(status=S.PENDING, attempts=0)
    if updated:
        audit(
            actor,
            "notification_retry",
            subject=notification.user_id,
            notification=str(notification.pk),
        )
        transaction.on_commit(partial(dispatch, notification.pk))
    return bool(updated)


def release_stuck() -> int:
    """Fail rows abandoned mid-send by a dead worker.

    They are *not* resent: Meta may already have accepted the message.  An admin
    can retry them knowingly from the failures view.
    """
    return Notification.objects.filter(
        channel=NotificationChannel.WHATSAPP,
        status=S.PROCESSING,
        claimed_at__lt=timezone.now() - STUCK_AFTER,
    ).update(
        status=S.FAILED, last_error_code="stuck_processing", last_error_at=timezone.now()
    )


# --------------------------------------------------------------------------- #
# Delivery-status webhooks
# --------------------------------------------------------------------------- #
_EVENT_STATUS = {"sent": S.SENT, "delivered": S.DELIVERED, "read": S.READ}


def apply_status_event(
    message_id: str, status: str, timestamp, error_code: str = ""
) -> bool:
    """Apply one Meta status event.  Idempotent, order-tolerant, never regresses."""
    qs = Notification.objects.filter(
        channel=NotificationChannel.WHATSAPP, provider_message_id=message_id
    )
    if status == "failed":
        return bool(
            qs.filter(status__in=[S.PROCESSING, S.ACCEPTED, S.SENT]).update(
                status=S.FAILED,
                last_error_code=(error_code or "provider_failed")[:40],
                last_error_at=timezone.now(),
            )
        )
    new = _EVENT_STATUS.get(status)
    if new is None:
        return False
    rank = STATUS_RANK[new]
    lower = [s for s, r in STATUS_RANK.items() if r < rank] + [S.PROCESSING, S.PENDING]
    moved = qs.filter(status__in=lower).update(status=new)
    # Keep timestamps truthful even when events arrive out of order.
    if status == "sent":
        qs.filter(sent_at__isnull=True).update(sent_at=timestamp)
    else:
        qs.filter(delivered_at__isnull=True).update(delivered_at=timestamp)
        if status == "read":
            qs.filter(provider_read_at__isnull=True).update(provider_read_at=timestamp)
    return bool(moved)
