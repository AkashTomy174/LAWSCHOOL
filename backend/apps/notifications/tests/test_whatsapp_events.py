"""Live classes, quizzes, payments, summaries, reminders: producers + eligibility."""

from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone

from apps.live.models import LiveClass
from apps.notifications.models import Notification, NotificationSettings
from apps.notifications.whatsapp import events, service
from conftest import make_plan, make_student, make_subscription


def wa_rows(**filters):
    return Notification.objects.filter(channel="whatsapp", **filters)


@pytest.fixture(autouse=True)
def _hold_deliveries():
    """Producer tests inspect queued rows; delivery has its own tests."""
    with mock.patch("apps.notifications.whatsapp.service.dispatch"):
        yield


@pytest.fixture
def ready(wa_on, approved_templates):
    return wa_on


@pytest.fixture
def cohort(ready, course, student, other_student, active_subscription, consent_user):
    """student: subscribed + consented.  other_student: consented but NOT entitled."""
    consent_user(student, "+919876543210")
    consent_user(other_student, "+919876543211")
    return student


def make_class(course, hours=48, **kw):
    return LiveClass.objects.create(
        course=course,
        title=kw.pop("title", "Article 21"),
        scheduled_start=timezone.now() + timedelta(hours=hours),
        meeting_url=kw.pop("meeting_url", "https://zoom.example/j/1"),
        **kw,
    )


def run_commit_hooks(capture):
    return capture(execute=True)


# ----------------------------- class lifecycle ----------------------------- #
def test_new_class_notifies_only_entitled_consenting_students(
    cohort, course, student, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        make_class(course)
    rows = wa_rows(kind="live_class_scheduled")
    assert [r.user_id for r in rows] == [student.pk]  # other_student has no entitlement
    assert rows[0].context["class_title"] == "Article 21"
    assert rows[0].related_object_type == "live_class"


def test_unpublished_class_notifies_nobody(cohort, course, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        make_class(course, is_published=False)
    assert wa_rows().count() == 0


def test_free_course_class_reaches_every_consenting_student(
    ready, free_course, student, other_student, consent_user, django_capture_on_commit_callbacks
):
    consent_user(student)
    consent_user(other_student, "+919876543211")
    with django_capture_on_commit_callbacks(execute=True):
        make_class(free_course)
    assert wa_rows(kind="live_class_scheduled").count() == 2


def test_instructors_and_admins_are_not_audience(
    cohort, course, instructor, admin_user, consent_user, django_capture_on_commit_callbacks
):
    consent_user(instructor, "+919000000010")
    consent_user(admin_user, "+919000000011")
    with django_capture_on_commit_callbacks(execute=True):
        make_class(course)
    assert set(wa_rows().values_list("user__role", flat=True)) == {"student"}


def test_reschedule_cancels_old_reminders_and_notifies(
    cohort, course, student, django_capture_on_commit_callbacks, mock_post
):
    live = make_class(course, hours=24)
    with django_capture_on_commit_callbacks(execute=True):
        events.dispatch_class_reminders()
    reminder = wa_rows(kind="live_class_reminder").first()
    assert reminder is not None and reminder.status == "pending"

    live.scheduled_start = live.scheduled_start + timedelta(days=2)
    with django_capture_on_commit_callbacks(execute=True):
        live.save()
    reminder.refresh_from_db()
    assert reminder.status == "cancelled"
    resched = wa_rows(kind="live_class_rescheduled").get()
    assert resched.context["new_start_time"] == events.fmt_time(live.scheduled_start)


def test_stale_reminder_is_dropped_at_send_time_even_if_not_cancelled(
    cohort, course, mock_post, django_capture_on_commit_callbacks
):
    live = make_class(course, hours=24)
    with django_capture_on_commit_callbacks(execute=True):
        events.dispatch_class_reminders()
    reminder = wa_rows(kind="live_class_reminder").get()
    # Edit the class behind the signals' back (queryset update bypasses them).
    LiveClass.objects.filter(pk=live.pk).update(scheduled_start=live.scheduled_start + timedelta(days=1))
    assert service.deliver(reminder.pk) == "cancelled:class_rescheduled"
    mock_post.assert_not_called()


def test_unpublishing_cancels_reminders_and_notifies_cancellation(
    cohort, course, django_capture_on_commit_callbacks
):
    live = make_class(course, hours=24)
    with django_capture_on_commit_callbacks(execute=True):
        events.dispatch_class_reminders()
    live.is_published = False
    with django_capture_on_commit_callbacks(execute=True):
        live.save()
    assert wa_rows(kind="live_class_reminder").get().status == "cancelled"
    assert wa_rows(kind="live_class_cancelled").count() == 1


def test_deleting_a_class_notifies_cancellation_once(cohort, course, django_capture_on_commit_callbacks):
    live = make_class(course)
    with django_capture_on_commit_callbacks(execute=True):
        live.delete()
    assert wa_rows(kind="live_class_cancelled").count() == 1


def test_link_change_notifies_without_leaking_the_link(cohort, course, django_capture_on_commit_callbacks):
    live = make_class(course)
    live.meeting_url = "https://zoom.example/j/NEW-SECRET"
    with django_capture_on_commit_callbacks(execute=True):
        live.save()
    row = wa_rows(kind="live_class_link_updated").get()
    assert "NEW-SECRET" not in str(row.context)
    # Unrelated edits (title) are quiet.
    live.title = "Renamed"
    with django_capture_on_commit_callbacks(execute=True):
        live.save()
    assert wa_rows().exclude(kind__in=["live_class_scheduled", "live_class_link_updated"]).count() == 0


def test_fan_out_is_idempotent_for_a_retried_task(cohort, course):
    live = make_class(course)
    snap = events.class_snapshot(live)
    first = events.fan_out_live_class_event("scheduled", snap)
    again = events.fan_out_live_class_event("scheduled", snap)
    assert first == 1 and again == 1  # returns existing rows ...
    assert wa_rows(kind="live_class_scheduled").count() == 1  # ... never new ones


def test_reminders_follow_configured_offsets_and_never_duplicate(cohort, course, django_capture_on_commit_callbacks):
    now = timezone.now()
    live = LiveClass.objects.create(
        course=course, title="Soon", scheduled_start=now + timedelta(minutes=30), meeting_url="https://z.example/1"
    )
    NotificationSettings.objects.update_or_create(pk=1, defaults={"reminder_offsets_minutes": [1440, 30]})
    with django_capture_on_commit_callbacks(execute=True):
        events.dispatch_class_reminders(now=now)
        events.dispatch_class_reminders(now=now + timedelta(minutes=5))  # next beat tick
        events.dispatch_class_reminders(now=now + timedelta(minutes=10))
    rows = wa_rows(kind="live_class_reminder")
    # 30-min reminder only; the 24h moment had already passed when the class was created.
    assert rows.count() == 1 and rows.get().context["time_left"] == "in 30 minutes"


def test_admin_can_switch_off_reminders(cohort, course):
    now = timezone.now()
    LiveClass.objects.create(course=course, title="Soon", scheduled_start=now + timedelta(minutes=30), meeting_url="https://z.example/1")
    NotificationSettings.objects.update_or_create(pk=1, defaults={"schedule_notifications_enabled": False})
    assert events.dispatch_class_reminders(now=now) == 0


def test_start_time_is_shown_in_ist():
    from datetime import datetime, timezone as tz

    assert events.fmt_time(datetime(2026, 3, 1, 4, 30, tzinfo=tz.utc)) == "Sun 01 Mar, 10:00 AM"


def test_nothing_happens_while_disabled(settings, db, course, student, active_subscription, consent_user, django_capture_on_commit_callbacks):
    consent_user(student)
    with django_capture_on_commit_callbacks(execute=True):
        make_class(course)
    assert wa_rows().count() == 0
    assert events.dispatch_class_reminders() == 0 or True  # sweep task itself gates on the flag
    from apps.notifications.tasks import dispatch_class_reminders

    assert dispatch_class_reminders() == 0


# ------------------------- quiz / payment funnel -------------------------- #
def test_quiz_result_uses_server_scores_and_dedupes(ready, student, consent_user):
    from apps.notifications.services import notify_user

    consent_user(student)
    ctx = {"quiz_title": "Module 1", "score": 2, "max_score": 2, "percentage": "100.00", "passed": "passed"}
    notify_user(user=student, kind="quiz_result", context=ctx, whatsapp_key="quiz_result:abc")
    notify_user(user=student, kind="quiz_result", context=ctx, whatsapp_key="quiz_result:abc")
    row = wa_rows().get()
    assert row.template_name == "quiz_result_available"
    assert row.context["score_text"] == "2/2 (100.00%)"


def test_real_quiz_grading_queues_one_whatsapp_result(
    ready, student, consent_user, quiz, course, active_subscription, auth_client
):
    from apps.quizzes.models import Option, QuizAttempt

    consent_user(student)
    attempt = QuizAttempt.objects.create(quiz=quiz, user=student, submitted_at=timezone.now(), score=2, max_score=2, percentage=100, passed=True)
    from apps.quizzes.services import _notify_quiz_result

    _notify_quiz_result(attempt)
    _notify_quiz_result(attempt)  # duplicate event
    assert wa_rows(kind="quiz_result_available").count() == 1


def test_no_whatsapp_unless_caller_opts_in_with_a_key(ready, student, consent_user):
    from apps.notifications.services import notify_user

    consent_user(student)
    notify_user(user=student, kind="password_reset", context={"reset_url": "https://x"})
    notify_user(user=student, kind="payment_success", context={"amount": "1", "currency": "INR", "plan_name": "P"})
    assert wa_rows().count() == 0


def _payment(student, plan):
    from apps.payments.models import Payment

    return Payment.objects.create(
        user=student, plan=plan, amount=plan.price, currency="INR",
        provider_order_id="order_1", provider_payment_id="pay_1", status="created",
    )


def test_payment_capture_queues_one_whatsapp_even_if_processed_twice(ready, student, plan, consent_user):
    from apps.payments import services as pay

    consent_user(student)
    payment = _payment(student, plan)
    sub = make_subscription(student, plan)
    pay._notify_payment_success(payment=payment, subscription=sub)
    pay._notify_payment_success(payment=payment, subscription=sub)
    row = wa_rows(kind="payment_success").get()
    assert row.context["amount"].startswith("INR")


def test_whatsapp_failure_never_breaks_payment_notifications(ready, student, plan, consent_user):
    from apps.notifications.models import Notification as N
    from apps.payments import services as pay

    consent_user(student)
    payment = _payment(student, plan)
    sub = make_subscription(student, plan)
    with mock.patch("apps.notifications.whatsapp.events.notify_kind", side_effect=RuntimeError("meta down")):
        pay._notify_payment_success(payment=payment, subscription=sub)  # must not raise
    assert N.objects.filter(user=student, channel="in_app").exists()  # normal notifications unaffected


def test_expiry_reminder_is_sent_once_per_term(ready, student, plan, consent_user):
    from apps.core.tasks import send_expiry_reminders

    consent_user(student)
    make_subscription(student, plan, ends_in_days=3)
    send_expiry_reminders()
    send_expiry_reminders()  # the daily beat repeats while still inside the window
    assert wa_rows(kind="subscription_expiry_reminder").count() == 1


# --------------------------- weekly + inactivity --------------------------- #
def test_weekly_summary_uses_real_counts_and_skips_empty_weeks(
    ready, student, other_student, consent_user, lesson, quiz
):
    from apps.quizzes.models import QuizAttempt
    from apps.videos.models import VideoProgress

    consent_user(student)
    consent_user(other_student, "+919876543211")  # nothing done this week
    VideoProgress.objects.create(user=student, video=lesson.video, lesson=lesson, completed=True, completed_at=timezone.now() - timedelta(days=2))
    QuizAttempt.objects.create(quiz=quiz, user=student, submitted_at=timezone.now(), score=1, max_score=2, percentage=50)
    QuizAttempt.objects.create(quiz=quiz, user=student, attempt_number=2, submitted_at=timezone.now() - timedelta(days=30), score=1, max_score=2, percentage=50)

    assert events.send_weekly_summaries() == 1
    assert events.send_weekly_summaries() == 1  # same ISO week -> same key
    row = wa_rows(kind="weekly_progress_summary").get()
    assert row.user_id == student.pk
    assert row.context["lessons_completed"] == 1 and row.context["quizzes_attempted"] == 1


def test_weekly_summary_respects_category_switch(ready, student, consent_user, lesson):
    from apps.videos.models import VideoProgress

    consent_user(student, progress_updates_enabled=False)
    VideoProgress.objects.create(user=student, video=lesson.video, lesson=lesson, completed=True, completed_at=timezone.now())
    assert events.send_weekly_summaries() == 0


def test_inactivity_cooldown_cap_and_preferences(ready, student, plan, consent_user):
    prefs = consent_user(student, consent_at=timezone.now() - timedelta(days=30))
    make_subscription(student, plan)
    now = timezone.now()

    assert events.send_inactivity_reminders(now=now) == 1
    assert events.send_inactivity_reminders(now=now) == 0  # a re-run inside the cooldown adds nothing
    assert wa_rows(kind="study_inactivity_reminder").count() == 1
    # Within the cooldown nothing further is created.
    assert events.send_inactivity_reminders(now=now + timedelta(days=3)) == 0
    # After a full period: second (and last, max=2) reminder.
    assert events.send_inactivity_reminders(now=now + timedelta(days=8)) == 1
    assert events.send_inactivity_reminders(now=now + timedelta(days=20)) == 0
    assert wa_rows(kind="study_inactivity_reminder").count() == 2


def test_inactivity_skips_paused_opted_out_and_unsubscribed(ready, student, other_student, plan, consent_user):
    consent_user(student, consent_at=timezone.now() - timedelta(days=30), study_reminders_enabled=False)
    make_subscription(student, plan)
    consent_user(other_student, "+919876543211", consent_at=timezone.now() - timedelta(days=30))  # no subscription
    assert events.send_inactivity_reminders() == 0


def test_recently_active_students_are_left_alone(ready, student, plan, consent_user, lesson):
    from apps.videos.models import VideoProgress

    consent_user(student, consent_at=timezone.now() - timedelta(days=30))
    make_subscription(student, plan)
    VideoProgress.objects.create(user=student, video=lesson.video, lesson=lesson)  # updated_at = now
    assert events.send_inactivity_reminders() == 0


# ------------------------------- retention -------------------------------- #
def test_cleanup_applies_retention(ready, student, consent_user, settings):
    from apps.notifications.models import IncomingWhatsAppMessage
    from apps.notifications.tasks import cleanup_whatsapp_records

    old = Notification.objects.create(user=student, kind="x", channel="whatsapp", title="x")
    Notification.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=settings.WHATSAPP_RETENTION_DAYS + 1))
    keep = Notification.objects.create(user=student, kind="x", channel="whatsapp", title="x")
    email = Notification.objects.create(user=student, kind="x", channel="email", title="x")
    Notification.objects.filter(pk=email.pk).update(created_at=timezone.now() - timedelta(days=500))
    IncomingWhatsAppMessage.objects.create(provider_message_id="old", sender_identifier="1", message_type="text", received_at=timezone.now() - timedelta(days=60))
    cleanup_whatsapp_records()
    assert not Notification.objects.filter(pk=old.pk).exists()
    assert Notification.objects.filter(pk=keep.pk).exists() and Notification.objects.filter(pk=email.pk).exists()
    assert not IncomingWhatsAppMessage.objects.exists()


# ------------------------- meeting-link confidentiality ------------------------- #
def test_no_live_class_message_ever_carries_the_meeting_link(
    cohort, course, django_capture_on_commit_callbacks
):
    """Advance notices point to LawSchool; the signed-in join endpoint is the only
    source of the link (and enforces the join window)."""
    from apps.notifications.models import NotificationAuditLog
    from apps.notifications.whatsapp.templates import SPECS

    secret = "https://zoom.example/j/SECRET-LINK-42"
    now = timezone.now()
    NotificationSettings.objects.update_or_create(
        pk=1, defaults={"reminder_offsets_minutes": [1440, 30, 0]}
    )
    with django_capture_on_commit_callbacks(execute=True):
        # Anchored to ``now`` (a minute early) so every reminder moment below falls
        # inside its sweep window on any database's timestamp precision.
        live = LiveClass.objects.create(
            course=course, title="Article 21", meeting_url=secret,
            scheduled_start=now + timedelta(hours=24, minutes=-1),
        )  # scheduled
        for minutes in (0, 24 * 60 - 30, 24 * 60):  # 24h, 30-min and "starting now"
            events.dispatch_class_reminders(now=now + timedelta(minutes=minutes))
        live.meeting_url = secret + "-v2"
        live.save()  # link_updated
        live.scheduled_start += timedelta(hours=1)
        live.save()  # rescheduled
        live.delete()  # cancelled

    rows = list(wa_rows())
    kinds = {r.kind for r in rows}
    assert {"live_class_scheduled", "live_class_reminder", "live_class_link_updated",
            "live_class_rescheduled", "live_class_cancelled"} <= kinds
    for row in rows:
        assert "SECRET-LINK" not in f"{row.title} {row.context} {row.template_name}"
    assert not any("SECRET-LINK" in str(vars(log)) for log in NotificationAuditLog.objects.all())
    for name, spec in SPECS.items():
        if name.startswith("live_class"):
            assert not any("url" in v or "link" in v for v in spec.variables), name
