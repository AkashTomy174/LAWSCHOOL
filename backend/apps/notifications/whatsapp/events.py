"""Business-event producers: turn LMS events into WhatsApp notifications.

Everything here goes through :func:`service.enqueue`, so consent, preferences,
idempotency and the on/off switch are enforced in exactly one place.  Producers
are called from Celery tasks (bulk fan-out) or wrapped in try/except by the
callers that live inside payment/quiz flows -- a messaging problem must never
break those.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from django.db.models import Count
from django.utils import timezone

from apps.core.logging import get_logger
from apps.notifications.models import (
    Category,
    Notification,
    NotificationSettings,
)
from apps.notifications.whatsapp import recipients
from apps.notifications.whatsapp.service import cancel_pending, display_name, enqueue

logger = get_logger(__name__)


def fmt_time(dt) -> str:
    """Student-facing time in the project timezone (Asia/Kolkata), DST-safe."""
    return timezone.localtime(dt).strftime("%a %d %b, %I:%M %p")


def time_left(offset_minutes: int) -> str:
    if offset_minutes <= 0:
        return "now"
    if offset_minutes < 60:
        return f"in {offset_minutes} minutes"
    if offset_minutes % 1440 == 0:
        days = offset_minutes // 1440
        return "in 24 hours" if days == 1 else f"in {days} days"
    if offset_minutes % 60 == 0:
        return f"in {offset_minutes // 60} hours"
    return f"in {offset_minutes} minutes"


# --------------------------------------------------------------------------- #
# Live classes
# --------------------------------------------------------------------------- #
def class_snapshot(live) -> dict:
    """JSON-safe copy of a class, so tasks never depend on a row that may be gone."""
    return {
        "class_id": str(live.pk),
        "title": live.title,
        "course_id": str(live.course_id),
        "course_title": live.course.title,
        "start": live.scheduled_start.isoformat(),
        "version": live.updated_at.isoformat() if live.updated_at else "",
    }


_EVENTS = {
    # event -> (template, preference category, variables-from-snapshot)
    "scheduled": "live_class_scheduled",
    "rescheduled": "live_class_rescheduled",
    "cancelled": "live_class_cancelled",
    "link_updated": "live_class_link_updated",
}


def fan_out_live_class_event(event: str, snap: dict, previous_start: str = "") -> int:
    """Notify every entitled, consenting student about a class change."""
    from apps.courses.models import Course

    course = Course.objects.filter(pk=snap["course_id"]).first()
    if course is None:
        return 0
    template = _EVENTS[event]
    start = datetime.fromisoformat(snap["start"])
    start_ts = int(start.timestamp())
    category = (
        Category.LIVE_CLASS if event == "scheduled" else Category.SCHEDULE_CHANGE
    )
    if event in ("rescheduled", "link_updated", "cancelled"):
        # Obsolete reminders must not go out with the old time.
        cancel_pending(
            related_type="live_class",
            related_id=snap["class_id"],
            kinds=["live_class_reminder"],
        )

    sent = 0
    for user in recipients.iterate(
        recipients.students_entitled_to_course(course, category)
    ):
        name = display_name(user)
        variables = {
            "scheduled": {
                "student_name": name,
                "class_title": snap["title"],
                "course_title": snap["course_title"],
                "start_time": fmt_time(start),
            },
            "rescheduled": {
                "student_name": name,
                "class_title": snap["title"],
                "new_start_time": fmt_time(start),
            },
            "cancelled": {
                "student_name": name,
                "class_title": snap["title"],
                "original_start_time": fmt_time(start),
            },
            "link_updated": {
                "student_name": name,
                "class_title": snap["title"],
                "start_time": fmt_time(start),
            },
        }[event]
        # ``version`` distinguishes two genuine edits to the same time; a retried
        # task for the *same* edit carries the same version and dedupes.
        key = f"{template}:{snap['class_id']}:{start_ts}:{snap['version']}:{user.pk}"
        if enqueue(
            user=user,
            template=template,
            variables=variables,
            key=key,
            related=("live_class", snap["class_id"]),
            scheduled_at=start,
            prefs=user.notification_preference,
        ):
            sent += 1
    return sent


def dispatch_class_reminders(now=None, grace_minutes: int = 15) -> int:
    """Create reminders for classes whose reminder moment falls in the last ``grace``.

    Runs every few minutes from Celery beat.  Idempotency keys include the class
    start time, so a rescheduled class naturally gets fresh reminders and an old
    one can never double-send.  A class created *after* a reminder moment simply
    never gets that reminder (the moment is outside the window).
    """
    from apps.live.models import LiveClass

    now = now or timezone.now()
    ns = NotificationSettings.load()
    if not ns.schedule_notifications_enabled:
        return 0
    grace = timedelta(minutes=grace_minutes)
    created = 0
    offsets = sorted({int(o) for o in ns.reminder_offsets_minutes if 0 <= int(o) <= 10080})
    for offset in offsets:
        target = now + timedelta(minutes=offset)
        classes = LiveClass.objects.filter(
            is_published=True,
            course__status="published",
            scheduled_start__gte=target - grace,
            scheduled_start__lte=target,
        ).select_related("course")
        if offset > 0:
            classes = classes.filter(scheduled_start__gt=now)
        else:  # "starting now" -- allow a class that began moments ago
            classes = classes.filter(scheduled_start__gt=now - timedelta(minutes=10))
        for live in classes:
            start_ts = int(live.scheduled_start.timestamp())
            for user in recipients.iterate(
                recipients.students_entitled_to_course(live.course, Category.LIVE_CLASS)
            ):
                if enqueue(
                    user=user,
                    template="live_class_reminder",
                    variables={
                        "student_name": display_name(user),
                        "class_title": live.title,
                        "start_time": fmt_time(live.scheduled_start),
                        "time_left": time_left(offset),
                    },
                    key=f"class_reminder:{live.pk}:{start_ts}:{offset}:{user.pk}",
                    related=("live_class", live.pk),
                    scheduled_at=live.scheduled_start,
                    prefs=user.notification_preference,
                ):
                    created += 1
    return created


# --------------------------------------------------------------------------- #
# Payment / subscription / quiz (called from notifications.services.notify_user)
# --------------------------------------------------------------------------- #
def _end(ctx) -> str:
    return str(ctx.get("end_date") or "soon")


KIND_MAP = {
    "payment_success": (
        "payment_success",
        lambda u, c: {
            "student_name": display_name(u),
            "amount": f"{c.get('currency', '')} {c.get('amount', '')}".strip(),
            "plan_name": c.get("plan_name", "your plan"),
        },
    ),
    "payment_failed": (
        "payment_failure",
        lambda u, c: {
            "student_name": display_name(u),
            "plan_name": c.get("plan_name", "your plan"),
        },
    ),
    "subscription_activated": (
        "subscription_renewed",
        lambda u, c: {
            "student_name": display_name(u),
            "plan_name": c.get("plan_name", "your plan"),
            "end_date": _end(c),
        },
    ),
    "subscription_expiring": (
        "subscription_expiry_reminder",
        lambda u, c: {
            "student_name": display_name(u),
            "plan_name": c.get("plan_name", "your plan"),
            "end_date": _end(c),
        },
    ),
    "subscription_expired": (
        "subscription_expired",
        lambda u, c: {
            "student_name": display_name(u),
            "plan_name": c.get("plan_name", "your plan"),
            "end_date": _end(c),
        },
    ),
    "quiz_result": (
        "quiz_result_available",
        lambda u, c: {
            "student_name": display_name(u),
            "quiz_title": c.get("quiz_title", "your quiz"),
            "score_text": f"{c.get('score')}/{c.get('max_score')} ({c.get('percentage')}%)",
        },
    ),
}


def notify_kind(*, user, kind: str, context: dict, key: str, related=("", "")):
    """WhatsApp leg of ``notify_user``.  ``key`` comes from the business event."""
    entry = KIND_MAP.get(kind)
    if entry is None:
        return None
    template, build = entry
    return enqueue(
        user=user, template=template, variables=build(user, context), key=key, related=related
    )


# --------------------------------------------------------------------------- #
# Weekly summary
# --------------------------------------------------------------------------- #
def send_weekly_summaries(now=None) -> int:
    from apps.quizzes.models import QuizAttempt
    from apps.videos.models import VideoProgress

    if not NotificationSettings.load().weekly_summary_enabled:
        return 0
    now = now or timezone.now()
    since = now - timedelta(days=7)
    iso = now.isocalendar()
    sent = 0
    batch: list = []

    def flush() -> int:
        if not batch:
            return 0
        ids = [u.pk for u in batch]
        lessons = dict(
            VideoProgress.objects.filter(
                user_id__in=ids, completed=True, completed_at__gte=since
            )
            .values_list("user_id")
            .annotate(c=Count("id"))
        )
        quizzes = dict(
            QuizAttempt.objects.filter(
                user_id__in=ids, submitted_at__isnull=False, submitted_at__gte=since
            )
            .values_list("user_id")
            .annotate(c=Count("id"))
        )
        n = 0
        for user in batch:
            lc, qc = lessons.get(user.pk, 0), quizzes.get(user.pk, 0)
            if not (lc or qc):
                continue  # nothing meaningful to say
            if enqueue(
                user=user,
                template="weekly_progress_summary",
                variables={
                    "student_name": display_name(user),
                    "lessons_completed": lc,
                    "quizzes_attempted": qc,
                },
                key=f"weekly_summary:{user.pk}:{iso[0]}-W{iso[1]}",
                prefs=user.notification_preference,
            ):
                n += 1
        batch.clear()
        return n

    for user in recipients.iterate(
        recipients.consenting_students(Category.PROGRESS_UPDATES)
    ):
        batch.append(user)
        if len(batch) >= recipients.CHUNK:
            sent += flush()
    return sent + flush()


# --------------------------------------------------------------------------- #
# Inactivity reminders
# --------------------------------------------------------------------------- #
def send_inactivity_reminders(now=None) -> int:
    from django.db.models import Max

    ns = NotificationSettings.load()
    if not ns.inactivity_reminders_enabled:
        return 0
    now = now or timezone.now()
    threshold = now - timedelta(days=ns.inactivity_days)
    # Only students who still have a live subscription: nothing to nudge once the
    # course access has ended.
    audience = (
        recipients.consenting_students(Category.STUDY_REMINDERS)
        .filter(id__in=recipients.active_subscription_user_ids())
        .annotate(
            last_video=Max("video_progress__updated_at"),
            last_quiz=Max("quiz_attempts__started_at"),
        )
    )
    sent = 0
    for user in recipients.iterate(audience):
        prefs = user.notification_preference
        last = max(
            [d for d in (user.last_video, user.last_quiz, prefs.consent_at) if d],
            default=None,
        )
        if last is None or last > threshold:
            continue
        previous = list(
            Notification.objects.filter(
                user=user, kind="study_inactivity_reminder", created_at__gt=last
            ).values_list("created_at", flat=True)
        )
        if len(previous) >= ns.inactivity_max_reminders:
            continue
        if previous and max(previous) > threshold:  # cooldown between reminders
            continue
        if enqueue(
            user=user,
            template="study_inactivity_reminder",
            variables={
                "student_name": display_name(user),
                "days": (now - last).days,
            },
            key=f"inactivity:{user.pk}:{last.date().isoformat()}:{len(previous) + 1}",
            prefs=prefs,
        ):
            sent += 1
    return sent


# --------------------------------------------------------------------------- #
# Announcements (admin only -- see views)
# --------------------------------------------------------------------------- #
def announcement_audience(course=None):
    if course is not None:
        return recipients.students_entitled_to_course(course, Category.ANNOUNCEMENTS)
    return recipients.consenting_students(Category.ANNOUNCEMENTS)


def send_announcement(*, title: str, text: str, course_id: str | None, batch_id: str) -> int:
    from apps.courses.models import Course

    course = Course.objects.filter(pk=course_id).first() if course_id else None
    sent = 0
    for user in recipients.iterate(announcement_audience(course)):
        if enqueue(
            user=user,
            template="platform_announcement",
            variables={
                "student_name": display_name(user),
                "announcement_title": title,
                "announcement_text": text,
            },
            key=f"announce:{batch_id}:{user.pk}",
            related=("announcement", batch_id),
            prefs=user.notification_preference,
        ):
            sent += 1
    return sent


def new_batch_id() -> str:
    return uuid.uuid4().hex
