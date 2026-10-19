"""Inbound WhatsApp assistant: a fixed command set over existing LMS services.

Trust model: the *only* thing taken from the message is the command keyword.  The
sender's number is mapped to an account through ``NotificationPreference`` rows
whose number was verified by one-time code (and is unique to one account), so a
stranger -- or a student texting from a different number -- can never read
someone else's data.  Every handler receives the resolved ``user`` and queries
only that user's rows.  No AI, no free-text lookup, no state-changing action other
than STOP.
"""

from __future__ import annotations

import re
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db.models import Count
from django.utils import timezone

from apps.core.constants import CourseStatus, LessonStatus, UserRole
from apps.core.logging import get_logger
from apps.notifications.models import (
    IncomingProcessing,
    IncomingWhatsAppMessage,
    NotificationPreference,
)
from apps.notifications.whatsapp import client, consent
from apps.notifications.whatsapp.events import fmt_time
from apps.notifications.whatsapp.service import rate_slot_available

logger = get_logger(__name__)

HELP = "HELP"
NEXT_CLASS = "NEXT CLASS"
MY_COURSES = "MY COURSES"
MY_PROGRESS = "MY PROGRESS"
MY_QUIZZES = "MY QUIZZES"
MY_ASSIGNMENTS = "MY ASSIGNMENTS"
PAYMENT_STATUS = "PAYMENT STATUS"
CONTACT_SUPPORT = "CONTACT SUPPORT"
STOP = "STOP"
UNKNOWN = "UNKNOWN"

_ALIASES = {
    "HELP": HELP, "MENU": HELP, "HI": HELP, "HELLO": HELP, "START": HELP,
    "NEXT CLASS": NEXT_CLASS, "NEXTCLASS": NEXT_CLASS, "CLASS": NEXT_CLASS,
    "MY COURSES": MY_COURSES, "COURSES": MY_COURSES,
    "MY PROGRESS": MY_PROGRESS, "PROGRESS": MY_PROGRESS,
    "MY QUIZZES": MY_QUIZZES, "QUIZZES": MY_QUIZZES, "MY QUIZ": MY_QUIZZES,
    "MY ASSIGNMENTS": MY_ASSIGNMENTS, "ASSIGNMENTS": MY_ASSIGNMENTS,
    "PAYMENT STATUS": PAYMENT_STATUS, "PAYMENT": PAYMENT_STATUS,
    "CONTACT SUPPORT": CONTACT_SUPPORT, "SUPPORT": CONTACT_SUPPORT,
    "STOP": STOP, "UNSUBSCRIBE": STOP, "OPT OUT": STOP, "OPTOUT": STOP,
}


def parse_command(text: str) -> str:
    """Map free text to a canonical command (exact match only; never executes text)."""
    cleaned = re.sub(r"[^A-Z0-9 ]", "", (text or "").upper())
    return _ALIASES.get(re.sub(r"\s+", " ", cleaned).strip(), UNKNOWN)


# --------------------------------------------------------------------------- #
# Handlers -- each takes the verified user and returns reply text
# --------------------------------------------------------------------------- #
def _help(user) -> str:
    return (
        "LawSchool assistant. Reply with:\n"
        "NEXT CLASS - your next live class\n"
        "MY COURSES - courses you can access\n"
        "MY PROGRESS - lessons completed\n"
        "MY QUIZZES - recent quiz results\n"
        "PAYMENT STATUS - your plan\n"
        "CONTACT SUPPORT - reach us\n"
        "STOP - stop WhatsApp messages"
    )


def _next_class(user) -> str:
    from apps.live.models import LiveClass
    from apps.subscriptions.services import accessible_course_ids, can_user_access_course

    base = LiveClass.objects.filter(
        is_published=True,
        course__status=CourseStatus.PUBLISHED,
        scheduled_start__gt=timezone.now() - timedelta(minutes=10),
    ).select_related("course")
    if user.role == UserRole.STUDENT:
        base = base.filter(course_id__in=accessible_course_ids(user))
    elif user.role == UserRole.INSTRUCTOR:
        base = base.filter(course__instructor=user)
    else:
        return "Please use the LawSchool website for admin tasks."
    live = base.order_by("scheduled_start").first()
    if live is None:
        return "You have no upcoming live classes."
    if not can_user_access_course(user, live.course):  # same entitlement gate as the API
        return "You do not currently have access to your next class. Visit LawSchool to renew."
    # Never the meeting link itself: the signed-in join endpoint is its only source
    # and also enforces the join window.  Point to the page that calls it.
    page = "/instructor/live" if user.role == UserRole.INSTRUCTOR else "/live"
    return (
        f"Next class: {live.title} ({live.course.title})\n"
        f"When: {fmt_time(live.scheduled_start)}\n"
        f"Join from 15 minutes before the start: {settings.FRONTEND_URL}{page}"
    )


def _student_only(handler):
    def wrapped(user):
        if user.role != UserRole.STUDENT:
            return "This command is for student accounts. Please use the LawSchool website."
        return handler(user)

    return wrapped


@_student_only
def _my_courses(user) -> str:
    from apps.courses.models import Course
    from apps.subscriptions.services import accessible_course_ids

    titles = list(
        Course.objects.filter(
            id__in=accessible_course_ids(user), status=CourseStatus.PUBLISHED
        )
        .order_by("title")
        .values_list("title", flat=True)[:10]
    )
    if not titles:
        return "You have no active courses. Browse plans on LawSchool."
    return "Your courses:\n" + "\n".join(f"- {t}" for t in titles)


@_student_only
def _my_progress(user) -> str:
    from apps.courses.models import Lesson
    from apps.videos.models import VideoProgress

    done = list(
        VideoProgress.objects.filter(
            user=user, completed=True, lesson__status=LessonStatus.PUBLISHED
        )
        .values("lesson__section__course_id", "lesson__section__course__title")
        .annotate(c=Count("id"))
        .order_by("-c")[:5]
    )
    if not done:
        return "No completed lessons yet. Start watching on LawSchool!"
    course_ids = [d["lesson__section__course_id"] for d in done]
    totals = dict(
        Lesson.objects.filter(
            section__course_id__in=course_ids, status=LessonStatus.PUBLISHED
        )
        .values_list("section__course_id")
        .annotate(c=Count("id"))
    )
    lines = [
        f"- {d['lesson__section__course__title']}: {d['c']}/{totals.get(d['lesson__section__course_id'], d['c'])} lessons"
        for d in done
    ]
    return "Your progress:\n" + "\n".join(lines)


@_student_only
def _my_quizzes(user) -> str:
    from apps.quizzes.models import QuizAttempt

    attempts = (
        QuizAttempt.objects.filter(user=user, submitted_at__isnull=False)
        .select_related("quiz")
        .order_by("-submitted_at")[:5]
    )
    lines = [
        f"- {a.quiz.title}: {a.score}/{a.max_score} ({a.percentage}%) "
        f"{'passed' if a.passed else 'not passed'}"
        for a in attempts
    ]
    return "Recent quizzes:\n" + "\n".join(lines) if lines else "No quiz attempts yet."


def _my_assignments(user) -> str:
    return "Assignments are not available on LawSchool yet."


@_student_only
def _payment_status(user) -> str:
    from apps.subscriptions.services import active_subscriptions

    subs = active_subscriptions(user)
    if not subs:
        return "You have no active subscription. Visit LawSchool > Plans to subscribe."
    lines = [
        f"- {s.plan.name}: active until {s.end_date.strftime('%d %b %Y') if s.end_date else 'further notice'}"
        for s in subs[:3]
    ]
    return "Your subscription:\n" + "\n".join(lines)


def _contact_support(user) -> str:
    return f"Contact LawSchool support at {settings.SUPPORT_EMAIL}."


def _stop(user) -> str:
    return "You are unsubscribed from LawSchool WhatsApp messages. Re-enable them any time in Settings."


HANDLERS = {
    HELP: _help,
    NEXT_CLASS: _next_class,
    MY_COURSES: _my_courses,
    MY_PROGRESS: _my_progress,
    MY_QUIZZES: _my_quizzes,
    MY_ASSIGNMENTS: _my_assignments,
    PAYMENT_STATUS: _payment_status,
    CONTACT_SUPPORT: _contact_support,
    STOP: _stop,
}

LINK_INSTRUCTION = (
    "We could not match this number to a LawSchool account. Sign in to LawSchool, "
    "open Settings > WhatsApp notifications and verify this number to use the assistant."
)
UNKNOWN_REPLY = "Sorry, I did not understand that. Reply HELP to see what I can do."


def resolve_sender(wa_id: str):
    """Verified, active account for a WhatsApp sender id, or ``None``."""
    prefs = (
        NotificationPreference.objects.select_related("user")
        .filter(whatsapp_number=f"+{wa_id}", whatsapp_verified_at__isnull=False)
        .first()
    )
    if prefs is None or not prefs.user.is_active:
        return None
    return prefs.user


def _reply(to_wa_id: str, text: str) -> None:
    if not rate_slot_available():
        raise client.WhatsAppError("rate_limited", retryable=True)
    client.send_text(f"+{to_wa_id}", text)


def process_incoming(incoming_id: int) -> str:
    """Handle one stored inbound message; safe to run twice."""
    msg = IncomingWhatsAppMessage.objects.filter(pk=incoming_id).first()
    if msg is None or msg.processing_status != IncomingProcessing.RECEIVED:
        return "skipped"
    user = resolve_sender(msg.sender_identifier)

    if user is None:
        # Bounded reflector: one link-instruction per sender per hour.
        gate = f"wa:unlinked:{msg.sender_identifier}"
        if cache.add(gate, 1, 3600):
            return _send(msg, LINK_INSTRUCTION, user=None)
        return _finish(msg, IncomingProcessing.IGNORED, "rate_limited")

    msg.mapped_user = user
    handler = HANDLERS.get(msg.command)
    text = handler(user) if handler else UNKNOWN_REPLY
    return _send(msg, text, user=user)


def _send(msg: IncomingWhatsAppMessage, text: str, *, user) -> str:
    if not settings.WHATSAPP_ENABLED:
        return _finish(msg, IncomingProcessing.IGNORED, "disabled", user)
    try:
        _reply(msg.sender_identifier, text)
    except client.WhatsAppError as exc:
        return _finish(msg, IncomingProcessing.FAILED, exc.code, user)
    return _finish(msg, IncomingProcessing.PROCESSED, "", user)


def _finish(msg, status: str, error: str, user=None) -> str:
    IncomingWhatsAppMessage.objects.filter(pk=msg.pk).update(
        processing_status=status,
        error_code=error[:40],
        processed_at=timezone.now(),
        mapped_user=user or msg.mapped_user,
    )
    return status


def handle_stop(wa_id: str) -> None:
    """Synchronous opt-out (compliance): runs in the webhook request, DB-only."""
    user = resolve_sender(wa_id)
    if user is not None:
        consent.opt_out(user, source="whatsapp_stop")
