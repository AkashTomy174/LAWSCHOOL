"""Live-class access: 100% delegated to the existing course entitlement check."""

from __future__ import annotations

from datetime import timedelta
from urllib.parse import urlsplit

from django.utils import timezone

from apps.core.exceptions import ConflictError, EntitlementError
from apps.live.models import LiveClass
from apps.subscriptions.services import can_user_access_course


def get_live_class_join_info(user, live_class: LiveClass) -> dict:
    """Return the meeting link, or raise ``EntitlementError`` if not entitled.

    No new access logic here -- a live class is gated by the same
    course-level check as videos and quizzes.
    """
    decision = can_user_access_course(user, live_class.course)
    if not decision:
        raise EntitlementError(
            {
                "detail": decision.detail,
                "reason": decision.reason,
                "course_slug": getattr(live_class.course, "slug", ""),
            },
            code=decision.reason,
        )

    return {
        "meeting_url": live_class.meeting_url,
        "meeting_provider": live_class.meeting_provider,
        "scheduled_start": live_class.scheduled_start,
        "duration_minutes": live_class.duration_minutes,
    }


# The site lets students in shortly before the start so they can test audio.
JOIN_OPENS_BEFORE = timedelta(minutes=15)


def class_end(live_class: LiveClass):
    return live_class.scheduled_start + timedelta(minutes=live_class.duration_minutes)


def class_status(live_class: LiveClass, now=None) -> str:
    """``upcoming`` / ``live`` / ``ended``, always judged by the server clock."""
    now = now or timezone.now()
    if now >= class_end(live_class):
        return "ended"
    return "live" if now >= live_class.scheduled_start else "upcoming"


def can_join_now(live_class: LiveClass, now=None) -> bool:
    now = now or timezone.now()
    return live_class.scheduled_start - JOIN_OPENS_BEFORE <= now < class_end(live_class)


def check_meeting_url(live_class: LiveClass) -> None:
    """Refuse to hand out a stored link that is not a plain web address.

    The API validates links on write, but a raw ORM or data-migration write does
    not -- and ``URLField`` also accepts ``ftp://``.
    """
    parts = urlsplit(live_class.meeting_url or "")
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ConflictError(
            {"detail": "This class does not have a valid meeting link yet.",
             "reason": "meeting_link_invalid"},
            code="meeting_link_invalid",
        )


def check_join_window(live_class: LiveClass) -> None:
    """Raise ``EntitlementError`` unless the class is joinable right now."""
    now = timezone.now()
    if can_join_now(live_class, now):
        return
    if now >= class_end(live_class):
        raise EntitlementError(
            {"detail": "This class has ended.", "reason": "class_ended"},
            code="class_ended",
        )
    raise EntitlementError(
        {
            "detail": "This class has not opened yet. You can join 15 minutes before it starts.",
            "reason": "class_not_open",
            "join_opens_at": (live_class.scheduled_start - JOIN_OPENS_BEFORE).isoformat(),
        },
        code="class_not_open",
    )
