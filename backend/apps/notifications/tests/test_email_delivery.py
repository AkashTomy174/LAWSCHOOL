"""Email delivery: misconfiguration is reported, failures are contained.

* Production with SMTP but no host, or with a console/locmem/dummy backend
  (console writes reset and verification links, i.e. live tokens, into the
  logs), now raises a system check warning that shows in ``check`` and in the
  pre-deploy ``migrate`` output.
* A failed send never breaks registration or password reset.
* A notification already sent is never sent again by a retry.
"""

from __future__ import annotations

import pytest
from django.core import mail
from django.core.mail.backends.base import BaseEmailBackend
from django.test import override_settings

from apps.core.checks import check_email_delivery


class ExplodingBackend(BaseEmailBackend):
    def send_messages(self, messages):
        raise ConnectionRefusedError("smtp down")


PROD = {"EMAIL_DELIVERY_REQUIRED": True}


class TestConfigurationCheck:
    @override_settings(**PROD, EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend", EMAIL_HOST="")
    def test_smtp_without_host_is_reported(self):
        assert [w.id for w in check_email_delivery(None)] == ["lawschool.W001"]

    @pytest.mark.parametrize("backend", ["console", "locmem", "dummy", "filebased"])
    def test_non_delivering_backends_are_reported(self, backend):
        with override_settings(**PROD, EMAIL_BACKEND=f"django.core.mail.backends.{backend}.EmailBackend"):
            assert [w.id for w in check_email_delivery(None)] == ["lawschool.W002"]

    @override_settings(**PROD, EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend", EMAIL_HOST="smtp.example.com")
    def test_configured_smtp_passes(self):
        assert check_email_delivery(None) == []

    @override_settings(EMAIL_DELIVERY_REQUIRED=False, EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend")
    def test_development_and_tests_are_not_nagged(self):
        assert check_email_delivery(None) == []

    def test_check_is_registered(self):
        from django.core.checks import registry

        assert check_email_delivery in registry.registry.registered_checks


@pytest.mark.django_db
class TestFailuresAreContained:
    @override_settings(EMAIL_BACKEND="apps.notifications.tests.test_email_delivery.ExplodingBackend")
    def test_registration_succeeds_when_email_fails(self, api_client):
        response = api_client.post(
            "/api/v1/auth/register/",
            {"email": "new@test.local", "name": "New", "password": "A-strong-pass-123",
             "password_confirm": "A-strong-pass-123"},
            format="json",
        )
        assert response.status_code == 201, response.data
        from apps.notifications.models import Notification

        note = Notification.objects.get(user__email="new@test.local", channel="email")
        assert note.sent_at is None and note.delivery_error

    @override_settings(EMAIL_BACKEND="apps.notifications.tests.test_email_delivery.ExplodingBackend")
    def test_password_reset_request_stays_neutral_when_email_fails(self, api_client, student):
        response = api_client.post("/api/v1/auth/password/reset/", {"email": student.email}, format="json")
        assert response.status_code == 200

    def test_reset_email_is_sent_with_a_working_backend(self, api_client, student):
        api_client.post("/api/v1/auth/password/reset/", {"email": student.email}, format="json")
        assert len(mail.outbox) == 1
        assert "/reset-password?uid=" in mail.outbox[0].body
        assert mail.outbox[0].to == [student.email]


@pytest.mark.django_db
def test_a_sent_notification_is_never_resent(student):
    from apps.notifications.models import Notification
    from apps.notifications.services import send_email_now
    from apps.notifications.tasks import retry_failed_notification_emails

    note = Notification.objects.create(user=student, channel="email", title="T", body="B", kind="quiz_result")
    assert send_email_now(note) is True
    assert len(mail.outbox) == 1

    assert send_email_now(note) is False  # e.g. a Celery retry racing the sweep
    retry_failed_notification_emails()
    assert len(mail.outbox) == 1
