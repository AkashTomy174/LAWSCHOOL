"""Provider client: success and every failure class, with secrets redacted."""

from unittest import mock

import pytest
import requests

from apps.notifications.tests.wa_support import FakeResponse, ok_response
from apps.notifications.whatsapp import client


def _err(status, code, message="boom"):
    return FakeResponse(status, {"error": {"code": code, "message": message}})


def test_successful_send_records_message_id_and_payload(wa_on, mock_post):
    result = client.send_template("+919876543210", "live_class_reminder", "en", ["A", "B"])
    assert result.message_id == "wamid.TEST1"
    kwargs = mock_post.call_args.kwargs
    assert kwargs["json"]["to"] == "919876543210"  # Meta wants digits only
    assert kwargs["json"]["template"]["components"][0]["parameters"][1]["text"] == "B"
    assert kwargs["timeout"] == wa_on.WHATSAPP_REQUEST_TIMEOUT
    assert "/v21.0/1234567890/messages" in mock_post.call_args.args[0]


@pytest.mark.parametrize(
    "response, code, retryable",
    [
        (_err(401, 190, "Invalid OAuth access token"), "auth_error", False),
        (_err(400, 131026, "Message undeliverable"), "invalid_recipient", False),
        (_err(400, 132001, "Template name does not exist"), "template_rejected", False),
        (_err(400, 131047, "Re-engagement message"), "window_closed", False),
        (_err(429, 130429, "Rate limit hit"), "rate_limited", True),
        (_err(500, 1, "Internal"), "server_error", True),
        (_err(503, 2, "Unavailable"), "server_error", True),
    ],
)
def test_provider_errors_are_classified(wa_on, response, code, retryable):
    with mock.patch("apps.notifications.whatsapp.client.requests.post", return_value=response):
        with pytest.raises(client.WhatsAppError) as exc:
            client.send_template("+919876543210", "t", "en", [])
    assert exc.value.code == code
    assert exc.value.retryable is retryable
    assert exc.value.ambiguous is False


def test_connect_timeout_is_safe_to_retry(wa_on):
    with mock.patch(
        "apps.notifications.whatsapp.client.requests.post",
        side_effect=requests.ConnectTimeout("connect"),
    ):
        with pytest.raises(client.WhatsAppError) as exc:
            client.send_text("+919876543210", "hi")
    assert exc.value.retryable and not exc.value.ambiguous


def test_read_timeout_is_ambiguous(wa_on):
    """Meta may have accepted the message: the caller must not blindly resend."""
    with mock.patch(
        "apps.notifications.whatsapp.client.requests.post",
        side_effect=requests.ReadTimeout("read"),
    ):
        with pytest.raises(client.WhatsAppError) as exc:
            client.send_text("+919876543210", "hi")
    assert exc.value.code == "timeout" and exc.value.ambiguous


@pytest.mark.parametrize("body", [{}, {"messages": []}, {"messages": [{}]}, ValueError])
def test_malformed_success_response_is_ambiguous(wa_on, body):
    with mock.patch(
        "apps.notifications.whatsapp.client.requests.post",
        return_value=FakeResponse(200, body),
    ):
        with pytest.raises(client.WhatsAppError) as exc:
            client.send_text("+919876543210", "hi")
    assert exc.value.code == "malformed_response" and exc.value.ambiguous


def test_missing_credentials_never_hit_the_network(settings):
    settings.WHATSAPP_ACCESS_TOKEN = ""
    with mock.patch("apps.notifications.whatsapp.client.requests.post") as post:
        with pytest.raises(client.WhatsAppError) as exc:
            client.send_text("+919876543210", "hi")
    assert exc.value.code == "not_configured"
    post.assert_not_called()


def test_access_token_and_numbers_are_redacted(wa_on):
    token = wa_on.WHATSAPP_ACCESS_TOKEN
    leaky = _err(400, 100, f"bad token {token} for +919876543210 Bearer abc.def")
    with mock.patch("apps.notifications.whatsapp.client.requests.post", return_value=leaky):
        with pytest.raises(client.WhatsAppError) as exc:
            client.send_text("+919876543210", "hi")
    text = str(exc.value)
    assert token not in text and "919876543210" not in text and "abc.def" not in text


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("+91 98765-43210", "+919876543210"),
        ("9876543210", "+919876543210"),
        ("919876543210", "+919876543210"),
        ("+14155552671", "+14155552671"),
    ],
)
def test_normalize_phone_accepts(raw, expected):
    assert client.normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", ["", "12345", "abcdefghij", "+0123456789", "+91123"])
def test_normalize_phone_rejects(raw):
    with pytest.raises(ValueError):
        client.normalize_phone(raw)
