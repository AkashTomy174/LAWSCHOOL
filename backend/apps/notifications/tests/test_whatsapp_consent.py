"""Linking, OTP verification, preferences, opt-out -- and what they gate."""

from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone

from apps.notifications.models import (
    ConsentStatus,
    Notification,
    NotificationPreference,
    WhatsAppVerification,
)
from apps.notifications.whatsapp import consent, service
from apps.notifications.whatsapp.templates import seed_templates

LINK = "/api/v1/notifications/whatsapp/link/"
VERIFY = "/api/v1/notifications/whatsapp/verify/"
PREFS = "/api/v1/notifications/whatsapp/preferences/"
OPT_OUT = "/api/v1/notifications/whatsapp/opt-out/"


# Linking requires a verified email; these tests are about the OTP flow itself.
@pytest.fixture
def student(student):
    student.is_email_verified = True
    student.save(update_fields=["is_email_verified"])
    return student


@pytest.fixture
def other_student(other_student):
    other_student.is_email_verified = True
    other_student.save(update_fields=["is_email_verified"])
    return other_student


def _sent_code(mock_post):
    """The OTP is only ever visible in the outbound request."""
    return mock_post.call_args.kwargs["json"]["template"]["components"][0]["parameters"][0]["text"]


def _link(auth_client, user, mock_post, phone="+919876543210"):
    client = auth_client(user)
    response = client.post(LINK, {"phone": phone, "consent": True}, format="json")
    return client, response


def test_anonymous_cannot_use_any_endpoint(api_client):
    for url in (PREFS, LINK, VERIFY, OPT_OUT):
        assert api_client.get(url).status_code == 401


def test_link_requires_whatsapp_enabled(auth_client, student, mock_post):
    response = auth_client(student).post(LINK, {"phone": "+919876543210", "consent": True}, format="json")
    assert response.status_code == 503
    mock_post.assert_not_called()


def test_link_requires_explicit_consent(wa_on, auth_client, student, mock_post):
    response = auth_client(student).post(LINK, {"phone": "+919876543210", "consent": False}, format="json")
    assert response.status_code == 400
    mock_post.assert_not_called()
    assert not NotificationPreference.objects.filter(user=student, whatsapp_verified_at__isnull=False).exists()


def test_invalid_number_is_rejected(wa_on, auth_client, student, mock_post):
    response = auth_client(student).post(LINK, {"phone": "12345", "consent": True}, format="json")
    assert response.status_code == 400
    mock_post.assert_not_called()


def test_full_link_flow_verifies_number_and_records_consent(wa_on, auth_client, student, mock_post):
    client, response = _link(auth_client, student, mock_post)
    assert response.status_code == 202
    assert "9876543210" not in response.content.decode()  # masked in the API
    code = _sent_code(mock_post)

    stored = WhatsAppVerification.objects.get(user=student)
    assert code not in stored.code_hash and len(stored.code_hash) == 64  # hashed, not clear

    bad = client.post(VERIFY, {"code": "000000" if code != "000000" else "111111"}, format="json")
    assert bad.status_code == 400

    ok = client.post(VERIFY, {"code": code}, format="json")
    assert ok.status_code == 200
    prefs = NotificationPreference.objects.get(user=student)
    assert prefs.is_verified and prefs.whatsapp_enabled
    assert prefs.consent_status == ConsentStatus.OPTED_IN
    assert prefs.consent_at and prefs.consent_source == "web_otp"
    assert ok.json()["whatsapp_number_masked"].endswith("3210")


def test_wrong_code_attempts_are_limited(wa_on, auth_client, student, mock_post):
    client, _ = _link(auth_client, student, mock_post)
    code = _sent_code(mock_post)
    wrong = "123456" if code != "123456" else "654321"
    for _ in range(consent.MAX_ATTEMPTS):
        assert client.post(VERIFY, {"code": wrong}, format="json").status_code == 400
    # Even the right code is refused once the budget is spent.
    assert client.post(VERIFY, {"code": code}, format="json").status_code == 429
    assert not NotificationPreference.objects.filter(user=student, whatsapp_verified_at__isnull=False).exists()


def test_expired_code_is_rejected(wa_on, auth_client, student, mock_post):
    client, _ = _link(auth_client, student, mock_post)
    code = _sent_code(mock_post)
    WhatsAppVerification.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    assert client.post(VERIFY, {"code": code}, format="json").status_code == 400


def test_resend_cooldown(wa_on, auth_client, student, mock_post):
    client, _ = _link(auth_client, student, mock_post)
    again = client.post(LINK, {"phone": "+919876543210", "consent": True}, format="json")
    assert again.status_code == 429
    assert mock_post.call_count == 1


def test_number_verified_by_one_account_cannot_be_claimed_by_another(
    wa_on, auth_client, student, other_student, mock_post, consent_user
):
    consent_user(student, "+919876543210")
    client, response = _link(auth_client, other_student, mock_post)
    # Same answer as for a free number (no account enumeration) ...
    assert response.status_code == 202
    # ... but nothing is sent to the number, so it can never be verified.
    mock_post.assert_not_called()


def test_db_forbids_two_verified_accounts_on_one_number(student, other_student, consent_user):
    from django.db import IntegrityError, transaction

    consent_user(student, "+919876543210")
    with pytest.raises(IntegrityError), transaction.atomic():
        consent_user(other_student, "+919876543210")


def test_preferences_are_private_to_the_caller(auth_client, student, other_student, consent_user):
    consent_user(other_student, "+919000000001")
    body = auth_client(student).get(PREFS).json()
    assert body["whatsapp_number_masked"] == "" and body["is_verified"] is False
    assert "9000000001" not in str(body)


def test_category_toggle_and_pause_via_api(auth_client, student, consent_user):
    consent_user(student)
    client = auth_client(student)
    response = client.patch(
        PREFS, {"quiz_updates_enabled": False, "study_reminders_paused_until": "2999-01-01"}, format="json"
    )
    assert response.status_code == 200
    prefs = NotificationPreference.objects.get(user=student)
    assert prefs.quiz_updates_enabled is False
    assert not prefs.allows("study_reminders")  # paused
    assert prefs.allows("live_class")


def test_cannot_enable_without_a_verified_number(auth_client, student):
    response = auth_client(student).patch(PREFS, {"whatsapp_enabled": True}, format="json")
    assert response.status_code == 400
    assert not NotificationPreference.objects.get(user=student).whatsapp_enabled


def test_client_cannot_forge_consent_or_number_through_patch(auth_client, student):
    auth_client(student).patch(
        PREFS,
        {"consent_status": "opted_in", "whatsapp_number": "+919999999999", "whatsapp_verified_at": "2026-01-01T00:00:00Z"},
        format="json",
    )
    prefs = NotificationPreference.objects.get(user=student)
    assert prefs.consent_status == ConsentStatus.NONE
    assert prefs.whatsapp_number == "" and prefs.whatsapp_verified_at is None


def test_opt_out_stops_messages_and_cancels_queued(
    wa_on, approved_templates, auth_client, student, consent_user
):
    consent_user(student)
    queued = service.enqueue(
        user=student,
        template="payment_success",
        variables={"student_name": "A", "amount": "INR 1", "plan_name": "P"},
        key="k1",
    )
    response = auth_client(student).post(OPT_OUT)
    assert response.status_code == 200
    queued.refresh_from_db()
    assert queued.status == "cancelled"
    prefs = NotificationPreference.objects.get(user=student)
    assert prefs.consent_status == ConsentStatus.OPTED_OUT and prefs.opted_out_at
    assert not prefs.allows("payment_updates")
    assert service.enqueue(
        user=student,
        template="payment_success",
        variables={"student_name": "A", "amount": "INR 1", "plan_name": "P"},
        key="k2",
    ) is None
    # Re-enabling after an opt-out needs a fresh verification, not a toggle.
    assert auth_client(student).patch(PREFS, {"whatsapp_enabled": True}, format="json").status_code == 400


def test_otp_send_failure_cleans_up_and_hides_provider_detail(wa_on, auth_client, student):
    from apps.notifications.tests.wa_support import FakeResponse

    boom = FakeResponse(401, {"error": {"code": 190, "message": "token abc"}})
    with mock.patch("apps.notifications.whatsapp.client.requests.post", return_value=boom):
        response = auth_client(student).post(LINK, {"phone": "+919876543210", "consent": True}, format="json")
    assert response.status_code == 502
    assert "abc" not in response.content.decode()
    assert not WhatsAppVerification.objects.exists()


def test_disabled_category_and_unverified_number_suppress_enqueue(
    wa_on, approved_templates, student, consent_user
):
    kwargs = dict(
        user=student,
        template="quiz_result_available",
        variables={"student_name": "A", "quiz_title": "Q", "score_text": "1/1"},
    )
    assert service.enqueue(key="a", **kwargs) is None  # no preference row at all
    prefs = consent_user(student, whatsapp_verified_at=None)
    assert service.enqueue(key="b", **kwargs) is None  # number not verified
    prefs.whatsapp_verified_at = timezone.now()
    prefs.quiz_updates_enabled = False
    prefs.save()
    assert service.enqueue(key="c", **kwargs) is None  # category off
    prefs.quiz_updates_enabled = True
    prefs.save()
    assert service.enqueue(key="d", **kwargs) is not None
    assert Notification.objects.filter(channel="whatsapp").count() == 1


def test_whatsapp_disabled_is_a_complete_noop(settings, db, student, consent_user):
    seed_templates()
    consent_user(student)
    assert service.enqueue(
        user=student,
        template="payment_success",
        variables={"student_name": "A", "amount": "1", "plan_name": "P"},
        key="x",
    ) is None
    assert Notification.objects.filter(channel="whatsapp").count() == 0
