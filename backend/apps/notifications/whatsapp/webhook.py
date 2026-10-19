"""Meta webhook plumbing: handshake, signature check, payload ingestion.

Rules that matter:

* the signature is computed over the **raw request body bytes**, exactly as
  received -- the body is never parsed and re-serialised first;
* comparisons are constant-time;
* ingestion only persists / updates rows and queues work, so the request returns
  quickly (Meta retries slow or failing webhooks);
* a malformed payload is rejected without partially applying it.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone as dt_timezone
from functools import partial

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.logging import get_logger
from apps.notifications.models import IncomingProcessing, IncomingWhatsAppMessage
from apps.notifications.whatsapp import commands
from apps.notifications.whatsapp.service import apply_status_event

logger = get_logger(__name__)


def verify_handshake(mode: str, token: str, challenge: str) -> str | None:
    """Return the challenge to echo, or ``None`` if the token is wrong."""
    expected = settings.WHATSAPP_VERIFY_TOKEN
    if (
        mode == "subscribe"
        and expected
        and hmac.compare_digest(token.encode(), expected.encode())
    ):
        return challenge
    return None


def signature_valid(raw_body: bytes, header: str) -> bool:
    secret = settings.WHATSAPP_APP_SECRET
    if not secret or not header or not header.startswith("sha256="):
        return False
    digest = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, header[len("sha256="):])


class PayloadError(ValueError):
    pass


def parse(raw_body: bytes) -> dict:
    try:
        payload = json.loads(raw_body)
    except ValueError:
        raise PayloadError("not json") from None
    if not isinstance(payload, dict) or payload.get("object") != "whatsapp_business_account":
        raise PayloadError("unexpected object")
    if not isinstance(payload.get("entry", []), list):
        raise PayloadError("bad entry")
    return payload


def _values(payload: dict):
    for entry in payload.get("entry", []):
        for change in (entry or {}).get("changes", []) or []:
            value = (change or {}).get("value")
            if isinstance(value, dict):
                yield value


def _ts(raw) -> datetime:
    try:
        return datetime.fromtimestamp(int(raw), tz=dt_timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return timezone.now()


def _message_text(message: dict) -> str:
    kind = message.get("type")
    if kind == "text":
        return str((message.get("text") or {}).get("body", ""))[:100]
    if kind == "button":
        return str((message.get("button") or {}).get("text", ""))[:100]
    if kind == "interactive":
        inter = message.get("interactive") or {}
        reply = inter.get("button_reply") or inter.get("list_reply") or {}
        return str(reply.get("id") or reply.get("title") or "")[:100]
    return ""


def ingest(payload: dict) -> dict:
    """Apply a verified payload.  Returns counters (handy for tests and logs)."""
    stats = {"statuses": 0, "messages": 0, "duplicates": 0, "ignored": 0}
    for value in _values(payload):
        for status in value.get("statuses", []) or []:
            if not isinstance(status, dict) or not status.get("id"):
                stats["ignored"] += 1
                continue
            errors = status.get("errors") or [{}]
            code = str((errors[0] or {}).get("code", "")) if errors else ""
            apply_status_event(
                str(status["id"]), str(status.get("status", "")), _ts(status.get("timestamp")), code
            )
            stats["statuses"] += 1

        for message in value.get("messages", []) or []:
            if not isinstance(message, dict) or not message.get("id") or not message.get("from"):
                stats["ignored"] += 1
                continue
            sender = "".join(ch for ch in str(message["from"]) if ch.isdigit())[:20]
            kind = str(message.get("type", "unknown"))[:30]
            supported = kind in ("text", "button", "interactive")
            command = commands.parse_command(_message_text(message)) if supported else ""
            try:
                with transaction.atomic():
                    incoming = IncomingWhatsAppMessage.objects.create(
                        provider_message_id=str(message["id"])[:200],
                        sender_identifier=sender,
                        message_type=kind,
                        command=command,
                        received_at=_ts(message.get("timestamp")),
                        processing_status=(
                            IncomingProcessing.RECEIVED
                            if supported
                            else IncomingProcessing.IGNORED
                        ),
                    )
            except IntegrityError:
                stats["duplicates"] += 1  # Meta retry: already handled
                continue
            stats["messages"] += 1
            if not supported:
                continue
            if command == commands.STOP:
                commands.handle_stop(sender)  # compliance: do not wait for a worker
            transaction.on_commit(partial(_queue_reply, incoming.pk))
    return stats


def _queue_reply(incoming_id: int) -> None:
    try:
        from apps.notifications.tasks import process_incoming_whatsapp

        process_incoming_whatsapp.delay(incoming_id)
    except Exception:
        logger.exception("Could not queue WhatsApp reply", extra={"incoming_id": incoming_id})
