"""Admin endpoints: permissions, filters, masking, announcements, settings."""

from unittest import mock

import pytest

from apps.notifications.models import (
    Notification,
    NotificationAuditLog,
    NotificationSettings,
    NotificationTemplate,
)
from apps.notifications.whatsapp.templates import seed_templates

BASE = "/api/v1/notifications/admin/"
ADMIN_GETS = ["overview/", "history/", "failed/", "templates/", "settings/", "announcements/preview/"]


@pytest.fixture(autouse=True)
def _hold_deliveries():
    with mock.patch("apps.notifications.whatsapp.service.dispatch"):
        yield


def _row(user, status="failed", **kw):
    return Notification.objects.create(
        user=user, kind=kw.pop("kind", "payment_success"), channel="whatsapp",
        title="x", status=status, template_name="payment_success", **kw,
    )


@pytest.mark.parametrize("path", ADMIN_GETS)
def test_admin_endpoints_reject_anonymous_students_and_instructors(path, api_client, auth_client, student, instructor):
    assert api_client.get(BASE + path).status_code == 401
    assert auth_client(student).get(BASE + path).status_code == 403
    assert auth_client(instructor).get(BASE + path).status_code == 403


def test_admin_can_read_everything(auth_client, admin_user, student, consent_user):
    consent_user(student)
    _row(student)
    client = auth_client(admin_user)
    for path in ADMIN_GETS:
        assert client.get(BASE + path).status_code == 200, path


def test_history_masks_numbers_and_paginates(auth_client, admin_user, student, consent_user):
    consent_user(student, "+919876543210")
    for _ in range(25):
        _row(student, status="delivered")
    body = auth_client(admin_user).get(BASE + "history/").json()
    assert body["count"] == 25 and len(body["results"]) == 20
    text = str(body)
    assert "9876543210" not in text and body["results"][0]["recipient_number"].endswith("3210")
    assert "context" not in body["results"][0]  # message variables are not exposed


def test_history_filters(auth_client, admin_user, student, other_student):
    _row(student, status="delivered")
    _row(other_student, status="failed", kind="quiz_result_available")
    client = auth_client(admin_user)
    assert client.get(BASE + "history/", {"status": "failed"}).json()["count"] == 1
    assert client.get(BASE + "history/", {"kind": "quiz_result_available"}).json()["count"] == 1
    assert client.get(BASE + "history/", {"recipient": "other@"}).json()["count"] == 1
    assert client.get(BASE + "failed/").json()["count"] == 1
    assert client.get(BASE + "history/", {"date_from": "2999-01-01"}).json()["count"] == 0


def test_history_excludes_email_and_in_app_rows(auth_client, admin_user, student):
    Notification.objects.create(user=student, kind="payment_success", channel="in_app", title="x")
    assert auth_client(admin_user).get(BASE + "history/").json()["count"] == 0


def test_overview_distinguishes_accepted_from_delivered(auth_client, admin_user, student, settings):
    _row(student, status="accepted")
    _row(student, status="delivered")
    _row(student, status="failed")
    body = auth_client(admin_user).get(BASE + "overview/").json()
    assert body["by_status"] == {"accepted": 1, "delivered": 1, "failed": 1}
    assert body["accepted_or_later"] == 2
    assert body["estimated_cost"] is None  # no pricing assumed unless configured
    settings.WHATSAPP_ESTIMATED_COST_PER_MESSAGE = "0.50"
    body = auth_client(admin_user).get(BASE + "overview/").json()
    assert body["estimated_cost"] == "1.00" and "estimate" in body["estimated_cost_note"].lower()


def test_retry_endpoint_only_moves_failed_rows(auth_client, admin_user, student, wa_on):
    failed, ok = _row(student, status="failed"), _row(student, status="delivered")
    client = auth_client(admin_user)
    assert client.post(f"{BASE}{failed.pk}/retry/").status_code == 200
    failed.refresh_from_db()
    assert failed.status == "pending"
    assert client.post(f"{BASE}{ok.pk}/retry/").status_code == 409
    assert NotificationAuditLog.objects.filter(action="notification_retry").count() == 1


def test_students_cannot_retry(auth_client, student):
    row = _row(student)
    assert auth_client(student).post(f"{BASE}{row.pk}/retry/").status_code == 403


def test_template_approval_is_recorded_not_assumed(auth_client, admin_user):
    client = auth_client(admin_user)
    rows = client.get(BASE + "templates/").json()
    assert len(rows) >= 17 and {r["approval_status"] for r in rows} == {"unknown"}
    target = rows[0]
    response = client.patch(f"{BASE}templates/{target['id']}/", {"approval_status": "approved", "internal_name": "hacked"}, format="json")
    assert response.status_code == 200
    row = NotificationTemplate.objects.get(pk=target["id"])
    assert row.approval_status == "approved" and row.internal_name == target["internal_name"]
    assert NotificationAuditLog.objects.filter(action="template_updated", actor=admin_user).exists()


def test_settings_validation_and_audit(auth_client, admin_user):
    client = auth_client(admin_user)
    assert client.get(BASE + "settings/").json()["reminder_offsets_minutes"] == [1440, 30]
    ok = client.patch(BASE + "settings/", {"reminder_offsets_minutes": [60, 1440, 60], "inactivity_days": 10}, format="json")
    assert ok.status_code == 200 and ok.json()["reminder_offsets_minutes"] == [1440, 60]
    for bad in (
        {"reminder_offsets_minutes": [-5]},
        {"reminder_offsets_minutes": ["x"]},
        {"reminder_offsets_minutes": list(range(10))},
        {"inactivity_days": 1},
        {"inactivity_max_reminders": 99},
        {"send_rate_per_minute": 0},
        {"disabled_templates": ["nope"]},
    ):
        assert client.patch(BASE + "settings/", bad, format="json").status_code == 400, bad
    assert NotificationSettings.load().inactivity_days == 10
    assert NotificationAuditLog.objects.filter(action="settings_changed").exists()


def test_disabled_template_is_never_queued(wa_on, approved_templates, student, consent_user):
    from apps.notifications.whatsapp import service

    consent_user(student)
    NotificationSettings.objects.update_or_create(pk=1, defaults={"disabled_templates": ["payment_success"]})
    assert service.enqueue(user=student, template="payment_success", variables={"student_name": "A", "amount": "1", "plan_name": "P"}, key="d") is None


# ------------------------------ announcements ------------------------------ #
@pytest.fixture
def audience(wa_on, approved_templates, student, other_student, consent_user):
    consent_user(student)
    consent_user(other_student, "+919876543211", announcements_enabled=False)


def _announce(client, **extra):
    return client.post(BASE + "announcements/", {"title": "Holiday", "text": "No class on Friday.", **extra}, format="json")


def test_announcement_preview_counts_only_consenting_recipients(auth_client, admin_user, audience):
    body = auth_client(admin_user).get(BASE + "announcements/preview/").json()
    assert body["recipients"] == 1


def test_announcement_requires_count_confirmation(auth_client, admin_user, audience):
    client = auth_client(admin_user)
    assert _announce(client).status_code == 409
    assert _announce(client, confirm_recipient_count=99).status_code == 409
    assert Notification.objects.filter(kind="platform_announcement").count() == 0


def test_announcement_fans_out_to_consenting_students_with_audit(auth_client, admin_user, audience, student):
    response = _announce(auth_client(admin_user), confirm_recipient_count=1)
    assert response.status_code == 202
    rows = Notification.objects.filter(kind="platform_announcement")
    assert [r.user_id for r in rows] == [student.pk]
    log = NotificationAuditLog.objects.get(action="announcement_sent")
    assert log.detail["recipients"] == 1 and log.actor == admin_user


def test_announcement_over_cap_is_refused(auth_client, admin_user, audience, settings):
    settings.WHATSAPP_MAX_BROADCAST_RECIPIENTS = 0
    assert _announce(auth_client(admin_user), confirm_recipient_count=1).status_code == 400


def test_announcement_needs_an_approved_template(auth_client, admin_user, audience):
    NotificationTemplate.objects.filter(internal_name="platform_announcement").update(approval_status="pending")
    assert _announce(auth_client(admin_user), confirm_recipient_count=1).status_code == 409


def test_instructors_and_students_cannot_broadcast(auth_client, instructor, student, audience):
    assert _announce(auth_client(instructor), confirm_recipient_count=1).status_code == 403
    assert _announce(auth_client(student), confirm_recipient_count=1).status_code == 403
    assert Notification.objects.filter(kind="platform_announcement").count() == 0


def test_announcement_input_is_validated(auth_client, admin_user, audience):
    client = auth_client(admin_user)
    assert client.post(BASE + "announcements/", {"title": "x" * 61, "text": "ok"}, format="json").status_code == 400
    assert client.post(BASE + "announcements/", {"title": "t", "text": "x" * 301}, format="json").status_code == 400


def test_course_scoped_announcement_respects_entitlement(auth_client, admin_user, audience, course, active_subscription):
    client = auth_client(admin_user)
    preview = client.get(BASE + "announcements/preview/", {"course": course.slug}).json()
    assert preview["recipients"] == 1  # only the subscribed, consenting student


# ------------------------------- student history --------------------------- #
def test_student_history_is_own_rows_only_and_has_no_message_content(auth_client, student, other_student):
    mine, theirs = _row(student, status="delivered"), _row(other_student, status="delivered")
    body = auth_client(student).get("/api/v1/notifications/whatsapp/history/").json()
    assert [r["id"] for r in body["results"]] == [str(mine.pk)]
    assert "context" not in body["results"][0]


def test_whatsapp_rows_never_leak_into_the_in_app_feed(auth_client, student):
    _row(student, status="delivered")
    assert auth_client(student).get("/api/v1/notifications/").json()["count"] == 0
