"""Meta WhatsApp Cloud API client -- the only module that talks HTTP to Meta.

Business code never imports ``requests``; it calls :func:`send_template` /
:func:`send_text` and handles :class:`WhatsAppError`.  Every failure is classified
so the caller can decide between *retry*, *give up* and *do not resend* (an
ambiguous outcome where Meta may already have accepted the message).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import requests
from django.conf import settings

from apps.core.logging import get_logger

logger = get_logger(__name__)

_E164 = re.compile(r"^\+[1-9]\d{7,14}$")

# Meta error codes grouped by what the caller should do about them.
_RATE_LIMIT_CODES = {4, 80007, 130429, 131048, 131056}
_AUTH_CODES = {0, 190, 10, 200}
_RECIPIENT_CODES = {131026, 131021, 1013, 131030, 131009}
_TEMPLATE_CODES = {132000, 132001, 132005, 132007, 132012, 132015, 132016, 131008}
_WINDOW_CODES = {131047, 131051}


class WhatsAppError(Exception):
    """A failed send.  ``str(exc)`` never contains credentials or full numbers."""

    def __init__(
        self,
        code: str,
        message: str = "",
        *,
        retryable: bool = False,
        ambiguous: bool = False,
        http_status: int | None = None,
    ):
        super().__init__(f"{code}: {message}" if message else code)
        self.code = code
        self.retryable = retryable
        # True when Meta may have accepted the message although we saw an error.
        self.ambiguous = ambiguous
        self.http_status = http_status


@dataclass(frozen=True)
class SendResult:
    message_id: str


def normalize_phone(raw: str, *, default_country: str = "91") -> str:
    """Return an E.164 number or raise ``ValueError``.

    Accepts "+91 98765-43210", "919876543210" and bare 10-digit Indian mobiles.
    """
    cleaned = re.sub(r"[\s\-().]", "", (raw or "").strip())
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    if not cleaned.startswith("+"):
        if re.fullmatch(r"[6-9]\d{9}", cleaned):
            cleaned = f"+{default_country}{cleaned}"
        elif cleaned.startswith(default_country) and len(cleaned) == 12:
            cleaned = "+" + cleaned
        else:
            raise ValueError("Enter the number with its country code, e.g. +919876543210.")
    if not _E164.match(cleaned):
        raise ValueError("Enter a valid phone number.")
    return cleaned


def mask_phone(number: str) -> str:
    digits = number or ""
    return f"{digits[:3]}{'*' * max(len(digits) - 7, 0)}{digits[-4:]}" if len(digits) > 7 else "***"


def redact(text: str) -> str:
    """Strip anything token-like from text destined for logs or the database."""
    text = str(text or "")
    token = getattr(settings, "WHATSAPP_ACCESS_TOKEN", "")
    if token:
        text = text.replace(token, "[redacted]")
    text = re.sub(r"(?i)bearer\s+[A-Za-z0-9._\-]+", "Bearer [redacted]", text)
    text = re.sub(r"\+?\d{10,15}", lambda m: mask_phone(m.group(0)), text)
    return text[:300]


def _endpoint() -> str:
    return (
        f"{settings.WHATSAPP_API_BASE_URL.rstrip('/')}/"
        f"{settings.WHATSAPP_API_VERSION}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    )


def _classify(status: int, body: dict) -> WhatsAppError:
    err = (body or {}).get("error") or {}
    code = int(err.get("code") or 0) if str(err.get("code") or "0").isdigit() else 0
    message = redact(err.get("message", ""))
    if status == 429 or code in _RATE_LIMIT_CODES:
        return WhatsAppError("rate_limited", message, retryable=True, http_status=status)
    if status == 401 or code in _AUTH_CODES:
        return WhatsAppError("auth_error", message, http_status=status)
    if code in _RECIPIENT_CODES:
        return WhatsAppError("invalid_recipient", message, http_status=status)
    if code in _TEMPLATE_CODES:
        return WhatsAppError("template_rejected", message, http_status=status)
    if code in _WINDOW_CODES:
        return WhatsAppError("window_closed", message, http_status=status)
    if status >= 500:
        return WhatsAppError("server_error", message, retryable=True, http_status=status)
    return WhatsAppError(f"client_error_{code or status}", message, http_status=status)


def _post(payload: dict) -> SendResult:
    if not (settings.WHATSAPP_PHONE_NUMBER_ID and settings.WHATSAPP_ACCESS_TOKEN):
        raise WhatsAppError("not_configured", "WhatsApp credentials are not set.")
    try:
        response = requests.post(
            _endpoint(),
            json=payload,
            headers={"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}"},
            timeout=settings.WHATSAPP_REQUEST_TIMEOUT,
        )
    except requests.ConnectTimeout as exc:
        # The request never reached Meta: always safe to retry.
        raise WhatsAppError("network_error", redact(exc), retryable=True) from None
    except requests.ConnectionError as exc:
        refused = "NewConnectionError" in repr(exc) or "Name or service" in repr(exc)
        raise WhatsAppError(
            "network_error", redact(exc), retryable=True, ambiguous=not refused
        ) from None
    except requests.RequestException as exc:  # read timeout etc.: outcome unknown
        raise WhatsAppError(
            "timeout", redact(exc), retryable=True, ambiguous=True
        ) from None

    try:
        body = response.json()
    except ValueError:
        body = {}

    if response.status_code >= 400:
        raise _classify(response.status_code, body)

    try:
        message_id = body["messages"][0]["id"]
    except (KeyError, IndexError, TypeError):
        # 2xx without a message id: Meta probably accepted it; do not resend.
        raise WhatsAppError(
            "malformed_response",
            "No message id in response.",
            ambiguous=True,
            http_status=response.status_code,
        ) from None
    return SendResult(message_id=str(message_id))


def send_template(
    to: str,
    template_name: str,
    language: str,
    body_params: list[str],
    *,
    url_button_param: str | None = None,
) -> SendResult:
    """Send an approved template.  ``to`` is E.164; params fill {{1}}, {{2}}..."""
    components: list[dict] = []
    if body_params:
        components.append(
            {
                "type": "body",
                "parameters": [{"type": "text", "text": p} for p in body_params],
            }
        )
    if url_button_param is not None:  # authentication (OTP) templates
        components.append(
            {
                "type": "button",
                "sub_type": "url",
                "index": "0",
                "parameters": [{"type": "text", "text": url_button_param}],
            }
        )
    return _post(
        {
            "messaging_product": "whatsapp",
            "to": to.lstrip("+"),
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language},
                "components": components,
            },
        }
    )


def send_text(to: str, body: str) -> SendResult:
    """Free-form reply; only valid inside the 24h window opened by the user."""
    return _post(
        {
            "messaging_product": "whatsapp",
            "to": to.lstrip("+"),
            "type": "text",
            "text": {"preview_url": False, "body": body[:4000]},
        }
    )
