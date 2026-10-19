"""Fixtures for the WhatsApp tests.  Nothing here ever touches the network."""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest import mock

import pytest
from django.utils import timezone

from apps.notifications.models import (
    ConsentStatus,
    NotificationPreference,
    NotificationTemplate,
)
from apps.notifications.whatsapp.templates import seed_templates


@pytest.fixture(autouse=True)
def _no_real_network():
    """Tests must never reach Meta: any un-mocked send fails loudly."""
    with mock.patch(
        "apps.notifications.whatsapp.client.requests.post",
        side_effect=AssertionError("real HTTP call to Meta attempted in a test"),
    ):
        yield


@pytest.fixture
def wa_on(settings):
    settings.WHATSAPP_ENABLED = True
    return settings


@pytest.fixture
def approved_templates(db):
    seed_templates()
    NotificationTemplate.objects.update(approval_status="approved")


class FakeResponse:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body if body is not None else {}

    def json(self):
        if self._body is ValueError:
            raise ValueError("bad json")
        return self._body


def ok_response(message_id="wamid.TEST1"):
    return FakeResponse(200, {"messages": [{"id": message_id}]})


@pytest.fixture
def mock_post():
    """Patch the single HTTP call to Meta; default response is a success."""
    with mock.patch(
        "apps.notifications.whatsapp.client.requests.post", return_value=ok_response()
    ) as m:
        yield m


@pytest.fixture
def consent_user():
    """Factory: give a user a verified, opted-in WhatsApp number."""

    def _make(user, number="+919876543210", **overrides):
        prefs, _ = NotificationPreference.objects.get_or_create(user=user)
        prefs.whatsapp_number = number
        prefs.whatsapp_verified_at = timezone.now()
        prefs.whatsapp_enabled = True
        prefs.consent_status = ConsentStatus.OPTED_IN
        prefs.consent_at = timezone.now()
        for k, v in overrides.items():
            setattr(prefs, k, v)
        prefs.save()
        return prefs

    return _make


def sign(body: bytes, secret="test-app-secret") -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def message_payload(wa_id, text, message_id="wamid.IN1", kind="text"):
    msg = {"from": wa_id, "id": message_id, "timestamp": "1760000000", "type": kind}
    if kind == "text":
        msg["text"] = {"body": text}
    return {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"value": {"messages": [msg]}}]}],
    }


def status_payload(message_id, status, errors=None):
    entry = {"id": message_id, "status": status, "timestamp": "1760000100"}
    if errors:
        entry["errors"] = errors
    return {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"value": {"statuses": [entry]}}]}],
    }


@pytest.fixture
def post_webhook(api_client):
    """POST a payload with a correct signature (or an override)."""

    def _post(payload, signature=None, raw=None):
        body = raw if raw is not None else json.dumps(payload).encode()
        return api_client.post(
            "/api/v1/notifications/whatsapp/webhook/",
            data=body,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=signature if signature is not None else sign(body),
        )

    return _post
