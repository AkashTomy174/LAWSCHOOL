"""Notification dispatch.

Callers use :func:`notify_user` and stay unaware of channels, templates or
transport.  The in-app row is written synchronously because it is cheap and the
UI may render immediately afterwards; the email is handed to Celery so a slow SMTP
server can never delay an HTTP response.

This is the rule that governs the whole module: **nothing here blocks a request**
except one INSERT.
"""

from __future__ import annotations

from django.conf import settings
from django.utils import timezone

from apps.core.constants import NotificationChannel, NotificationKind
from apps.core.logging import get_logger
from apps.notifications.models import Notification

logger = get_logger(__name__)

# Subject/body templates per event.  Kept as data so a new event is one entry,
# not a new code path.
TEMPLATES: dict[str, dict[str, str]] = {
    NotificationKind.ACCOUNT_VERIFICATION: {
        "title": "Verify your LawSchool email",
        "body": "Welcome to LawSchool! Confirm your email address to secure your account: {verify_url}",
        "action_url": "/profile",
    },
    NotificationKind.PASSWORD_RESET: {
        "title": "Reset your LawSchool password",
        "body": "We received a request to reset your password. Use this link within 24 hours: {reset_url}",
        "action_url": "/login",
    },
    NotificationKind.PAYMENT_SUCCESS: {
        "title": "Payment received",
        "body": "We received your payment of {currency} {amount} for {plan_name}. Reference: {payment_id}",
        "action_url": "/subscription",
    },
    NotificationKind.PAYMENT_FAILED: {
        "title": "Your payment could not be completed",
        "body": "The payment for {plan_name} failed ({reason}). You can retry any time from your subscription page.",
        "action_url": "/subscription",
    },
    NotificationKind.SUBSCRIPTION_ACTIVATED: {
        "title": "Your subscription is active",
        "body": "{plan_name} is now active. You have full access until {end_date}.",
        "action_url": "/courses",
    },
    NotificationKind.SUBSCRIPTION_EXPIRING: {
        "title": "Your subscription expires soon",
        "body": "Your {plan_name} access ends on {end_date}. Renew to keep your courses unlocked.",
        "action_url": "/subscription",
    },
    NotificationKind.SUBSCRIPTION_EXPIRED: {
        "title": "Your subscription has expired",
        "body": "Your {plan_name} access ended on {end_date}. Renew to continue watching.",
        "action_url": "/subscription",
    },
    NotificationKind.COURSE_ENROLLED: {
        "title": "New course unlocked",
        "body": "{course_title} is now available in your library.",
        "action_url": "/courses",
    },
    NotificationKind.QUIZ_RESULT: {
        "title": "Quiz result: {quiz_title}",
        "body": "You scored {score}/{max_score} ({percentage}%). You {passed} this quiz.",
        "action_url": "/leaderboard",
    },
}

DEFAULT_TEMPLATE = {
    "title": "LawSchool update",
    "body": "You have a new update on LawSchool.",
    "action_url": "",
}


def render(kind: str, context: dict) -> dict[str, str]:
    """Render a notification from its template.

    Uses ``str.format`` over a closed set of templates with attacker-influenced
    values (names, emails) only as *substituted data* -- never as the format
    string.  Missing keys degrade to the raw placeholder rather than raising, so a
    notification failure can never roll back a payment.
    """
    template = TEMPLATES.get(kind, DEFAULT_TEMPLATE)
    safe_context = _DefaultingDict(context)
    try:
        return {
            "title": template["title"].format_map(safe_context)[:200],
            "body": template["body"].format_map(safe_context),
            "action_url": template.get("action_url", ""),
        }
    except Exception:  # pragma: no cover - defensive
        logger.exception("Notification template rendering failed", extra={"kind": kind})
        return {
            "title": DEFAULT_TEMPLATE["title"],
            "body": DEFAULT_TEMPLATE["body"],
            "action_url": "",
        }


class _DefaultingDict(dict):
    """``format_map`` helper that leaves unknown keys as ``{key}`` placeholders."""

    def __missing__(self, key):  # noqa: D105
        return "{" + key + "}"


def notify_user(
    *,
    user,
    kind: str,
    context: dict | None = None,
    channels: list[str] | None = None,
    send_email: bool = True,
) -> list[Notification]:
    """Create in-app notification rows and queue email delivery.

    Returns the created rows so a caller (or a test) can assert on them without
    re-querying.
    """
    context = context or {}
    channels = channels or [
        NotificationChannel.IN_APP,
        *([NotificationChannel.EMAIL] if send_email else []),
    ]
    rendered = render(kind, context)

    created: list[Notification] = []
    for channel in channels:
        notification = Notification.objects.create(
            user=user,
            kind=kind,
            channel=channel,
            title=rendered["title"],
            body=rendered["body"],
            action_url=rendered["action_url"],
            context=context,
        )
        created.append(notification)

        if channel == NotificationChannel.EMAIL:
            _queue_email(notification)

    return created


def _queue_email(notification: Notification) -> None:
    """Hand the send off to Celery; fall back to inline delivery if it is down.

    The fallback matters in development (eager mode) and when Redis is briefly
    unavailable -- an unsent email is better than an exception on a payment
    callback.
    """
    try:
        from apps.notifications.tasks import send_notification_email

        send_notification_email.delay(str(notification.pk))
    except Exception:
        logger.warning(
            "Could not queue notification email; sending inline",
            extra={"notification_id": str(notification.pk)},
        )
        try:
            send_notification_email(str(notification.pk))
        except Exception:
            logger.exception(
                "Inline notification email send failed",
                extra={"notification_id": str(notification.pk)},
            )


def send_email_now(notification: Notification) -> bool:
    """Actually deliver one email notification.  Called by the Celery task."""
    from django.core.mail import send_mail

    if notification.channel != NotificationChannel.EMAIL:
        return False

    subject = notification.title
    message = notification.body
    try:
        sent = send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[notification.user.email],
            fail_silently=False,
        )
    except Exception as exc:
        notification.mark_failed(str(exc))
        logger.exception(
            "Email delivery failed", extra={"notification_id": str(notification.pk)}
        )
        raise

    if sent:
        notification.mark_sent()
        return True
    notification.mark_failed("Mail backend returned 0.")
    return False


def unread_count(user) -> int:
    """Unread in-app badge count -- one indexed COUNT, no row loading."""
    return Notification.objects.filter(
        user=user, channel=NotificationChannel.IN_APP, read_at__isnull=True
    ).count()


def mark_all_read(user) -> int:
    return Notification.objects.filter(
        user=user, channel=NotificationChannel.IN_APP, read_at__isnull=True
    ).update(read_at=timezone.now())
