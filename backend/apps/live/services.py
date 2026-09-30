"""Live-class access: 100% delegated to the existing course entitlement check."""

from __future__ import annotations

from apps.core.exceptions import EntitlementError
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
