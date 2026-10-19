"""Persist -> claim -> send -> track, including retries and webhook status events."""

from datetime import timedelta
from unittest import mock

import pytest
import requests
from django.utils import timezone

from apps.notifications.models import Notification, NotificationTemplate
from apps.notifications.tests.wa_support import FakeResponse, ok_response
from apps.notifications.whatsapp import service

VARS = {"student_name": "Asha", "amount": "INR 1999", "plan_name": "Foundations"}


@pytest.fixture
def queued(wa_on, approved_templates, student, consent_user):
    consent_user(student)
    return service.enqueue(user=student, template="payment_success", variables=VARS, key="pay:1")


def test_enqueue_creates_one_pending_row_and_is_idempotent(queued, student):
    again = service.enqueue(user=student, template="payment_success", variables=VARS, key="pay:1")
    assert again.pk == queued.pk
    assert Notification.objects.filter(channel="whatsapp").count() == 1
    assert queued.status == "pending" and queued.template_name == "payment_success"


def test_enqueue_dispatches_after_commit_only(wa_on, approved_templates, student, consent_user, django_capture_on_commit_callbacks):
    consent_user(student)
    with mock.patch("apps.notifications.whatsapp.service.dispatch") as dispatch:
        with django_capture_on_commit_callbacks(execute=True):
            n = service.enqueue(user=student, template="payment_success", variables=VARS, key="pay:2")
            dispatch.assert_not_called()  # not before the transaction commits
        dispatch.assert_called_once_with(n.pk)
        # A duplicate event queues nothing.
        with django_capture_on_commit_callbacks(execute=True):
            service.enqueue(user=student, template="payment_success", variables=VARS, key="pay:2")
        assert dispatch.call_count == 1


def test_bad_variables_are_rejected_before_anything_is_stored(wa_on, approved_templates, student, consent_user):
    consent_user(student)
    from apps.notifications.whatsapp.templates import TemplateVariableError

    for bad in ({"student_name": "A"}, {**VARS, "extra": "x"}, {**VARS, "plan_name": "  "}):
        with pytest.raises(TemplateVariableError):
            service.enqueue(user=student, template="payment_success", variables=bad, key="bad")
    assert not Notification.objects.filter(channel="whatsapp").exists()


def test_deliver_sends_template_and_marks_accepted_not_delivered(queued, mock_post):
    assert service.deliver(queued.pk) == "accepted"
    queued.refresh_from_db()
    assert queued.status == "accepted"  # NOT delivered
    assert queued.provider_message_id == "wamid.TEST1"
    assert queued.accepted_at and queued.delivered_at is None and queued.attempts == 1
    sent = mock_post.call_args.kwargs["json"]["template"]
    assert sent["name"] == "payment_success"
    assert [p["text"] for p in sent["components"][0]["parameters"]] == ["Asha", "INR 1999", "Foundations"]


def test_two_workers_cannot_send_the_same_notification(queued, mock_post):
    assert service.deliver(queued.pk) == "accepted"
    assert service.deliver(queued.pk) == "skipped"
    assert mock_post.call_count == 1


def test_unapproved_template_is_never_sent(wa_on, approved_templates, student, consent_user, mock_post):
    consent_user(student)
    NotificationTemplate.objects.filter(internal_name="payment_success").update(approval_status="pending")
    n = service.enqueue(user=student, template="payment_success", variables=VARS, key="u1")
    assert service.deliver(n.pk) == "suppressed:template_not_approved"
    mock_post.assert_not_called()
    n.refresh_from_db()
    assert n.status == "suppressed"


def test_unapproved_allowed_only_by_explicit_setting(queued, mock_post, settings):
    NotificationTemplate.objects.filter(internal_name="payment_success").update(approval_status="unknown")
    settings.WHATSAPP_ALLOW_UNAPPROVED_TEMPLATES = True
    assert service.deliver(queued.pk) == "accepted"


def test_consent_withdrawn_after_queueing_suppresses_at_send_time(queued, student, mock_post):
    from apps.notifications.whatsapp import consent

    # Opt-out cancels open rows; simulate the race where it lands after the claim check.
    from apps.notifications.models import NotificationPreference

    NotificationPreference.objects.filter(user=student).update(whatsapp_enabled=False)
    assert service.deliver(queued.pk) == "suppressed:no_consent"
    mock_post.assert_not_called()


def test_permanent_errors_fail_without_retry(queued):
    with mock.patch(
        "apps.notifications.whatsapp.client.requests.post",
        return_value=FakeResponse(400, {"error": {"code": 131026, "message": "undeliverable"}}),
    ) as post:
        assert service.deliver(queued.pk) == "failed:invalid_recipient"
    queued.refresh_from_db()
    assert queued.status == "failed" and queued.last_error_code == "invalid_recipient"
    assert post.call_count == 1


def test_temporary_errors_requeue_with_backoff_until_attempts_exhausted(queued, settings):
    settings.WHATSAPP_MAX_ATTEMPTS = 3
    boom = FakeResponse(503, {"error": {"code": 2, "message": "down"}})
    with mock.patch("apps.notifications.whatsapp.client.requests.post", return_value=boom):
        with pytest.raises(service.RetryLater) as later:
            service.deliver(queued.pk)
        assert 30 <= later.value.countdown <= 45
        queued.refresh_from_db()
        assert queued.status == "pending" and queued.attempts == 1
        with pytest.raises(service.RetryLater):
            service.deliver(queued.pk)
        assert service.deliver(queued.pk) == "failed:server_error"  # 3rd attempt: give up
    queued.refresh_from_db()
    assert queued.status == "failed" and queued.attempts == 3


def test_ambiguous_timeout_is_not_resent(queued):
    with mock.patch(
        "apps.notifications.whatsapp.client.requests.post", side_effect=requests.ReadTimeout("slow")
    ) as post:
        assert service.deliver(queued.pk) == "failed:timeout"
    queued.refresh_from_db()
    assert queued.status == "failed"
    assert post.call_count == 1


def test_ambiguous_retry_can_be_enabled_explicitly(queued, settings):
    settings.WHATSAPP_RETRY_AMBIGUOUS = True
    with mock.patch(
        "apps.notifications.whatsapp.client.requests.post", side_effect=requests.ReadTimeout("slow")
    ):
        with pytest.raises(service.RetryLater):
            service.deliver(queued.pk)


def test_send_rate_limit_defers_without_sending(queued, mock_post):
    with mock.patch("apps.notifications.whatsapp.service.rate_slot_available", return_value=False):
        with pytest.raises(service.RetryLater):
            service.deliver(queued.pk)
    mock_post.assert_not_called()
    queued.refresh_from_db()
    assert queued.status == "pending" and queued.attempts == 0


def test_disabled_flag_means_no_send(queued, settings, mock_post):
    settings.WHATSAPP_ENABLED = False
    assert service.deliver(queued.pk) == "disabled"
    mock_post.assert_not_called()


def test_abandoned_processing_rows_fail_instead_of_resending(queued):
    Notification.objects.filter(pk=queued.pk).update(
        status="processing", claimed_at=timezone.now() - timedelta(minutes=30)
    )
    assert service.release_stuck() == 1
    queued.refresh_from_db()
    assert queued.status == "failed" and queued.last_error_code == "stuck_processing"


def test_sweeper_redispatches_lost_rows(queued):
    from apps.notifications.tasks import sweep_pending_whatsapp

    Notification.objects.filter(pk=queued.pk).update(created_at=timezone.now() - timedelta(minutes=10))
    with mock.patch("apps.notifications.whatsapp.service.dispatch") as dispatch:
        assert sweep_pending_whatsapp() == 1
    dispatch.assert_called_once_with(queued.pk)


def test_send_task_retries_through_celery(queued):
    from celery.exceptions import Retry

    from apps.notifications.tasks import send_whatsapp_notification

    with mock.patch(
        "apps.notifications.whatsapp.service.deliver", side_effect=service.RetryLater(42)
    ):
        with pytest.raises(Retry):
            send_whatsapp_notification.apply(args=[str(queued.pk)], throw=True)


# ------------------------------ status events ----------------------------- #
@pytest.fixture
def accepted(queued, mock_post):
    service.deliver(queued.pk)
    queued.refresh_from_db()
    return queued


def _event(status, ts=None, code=""):
    return service.apply_status_event("wamid.TEST1", status, ts or timezone.now(), code)


def test_status_progression_sent_delivered_read(accepted):
    assert _event("sent") and _event("delivered") and _event("read")
    accepted.refresh_from_db()
    assert accepted.status == "read"
    assert accepted.sent_at and accepted.delivered_at and accepted.provider_read_at


def test_late_events_never_regress_state(accepted):
    _event("delivered")
    assert _event("sent") is False  # stale: arrives after delivered
    accepted.refresh_from_db()
    assert accepted.status == "delivered"
    assert accepted.sent_at is not None  # timestamp still backfilled
    _event("read")
    assert _event("delivered") is False
    accepted.refresh_from_db()
    assert accepted.status == "read"


def test_duplicate_events_are_harmless(accepted):
    assert _event("delivered") is True
    assert _event("delivered") is False
    accepted.refresh_from_db()
    assert accepted.status == "delivered"


def test_failed_event_records_code_but_cannot_undo_delivery(accepted):
    assert _event("failed", code="131026")
    accepted.refresh_from_db()
    assert accepted.status == "failed" and accepted.last_error_code == "131026"


def test_failed_after_delivered_is_ignored(accepted):
    _event("delivered")
    assert _event("failed", code="1") is False
    accepted.refresh_from_db()
    assert accepted.status == "delivered"


def test_unknown_message_id_or_status_is_ignored(accepted):
    assert service.apply_status_event("wamid.NOPE", "delivered", timezone.now()) is False
    assert _event("deleted") is False


def test_admin_retry_requeues_same_row_without_duplicating(queued, admin_user, django_capture_on_commit_callbacks):
    with mock.patch("apps.notifications.whatsapp.client.requests.post", return_value=FakeResponse(400, {"error": {"code": 132001}})):
        service.deliver(queued.pk)
    queued.refresh_from_db()
    assert queued.status == "failed"
    with mock.patch("apps.notifications.whatsapp.service.dispatch") as dispatch:
        with django_capture_on_commit_callbacks(execute=True):
            assert service.retry_failed(queued, admin_user) is True
        assert service.retry_failed(queued, admin_user) is False  # no longer failed
    dispatch.assert_called_once()
    assert Notification.objects.filter(channel="whatsapp").count() == 1
    queued.refresh_from_db()
    assert queued.status == "pending"
