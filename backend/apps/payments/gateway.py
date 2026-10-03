"""Razorpay gateway wrapper + signature verification.

The ``razorpay`` SDK is used for order creation only.  Signature *verification*
is implemented locally with ``hmac`` so the exact bytes being compared are
visible in this file and covered by unit tests -- verifying money is too important
to hide behind a library call.

Two different HMAC constructions are used by Razorpay, and mixing them up is a
classic source of silent vulnerabilities:

* **Checkout callback**: ``HMAC_SHA256(order_id + "|" + payment_id, key_secret)``
* **Webhook**: ``HMAC_SHA256(raw_request_body, webhook_secret)`` -- the *raw*
  body, before any JSON parsing.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

from django.conf import settings

from apps.core.exceptions import PaymentError
from apps.core.logging import get_logger

logger = get_logger(__name__)


def _credentials() -> tuple[str, str]:
    key_id = settings.RAZORPAY_KEY_ID
    key_secret = settings.RAZORPAY_KEY_SECRET
    if not key_id or not key_secret:
        raise PaymentError(
            {"detail": "Payment gateway is not configured."},
            code="gateway_unconfigured",
        )
    return key_id, key_secret


def get_client():
    """Return a configured Razorpay SDK client (order creation only)."""
    import razorpay

    key_id, key_secret = _credentials()
    return razorpay.Client(auth=(key_id, key_secret))


def create_order(
    *,
    amount_paise: int,
    currency: str,
    receipt: str,
    notes: dict[str, Any] | None = None,
) -> dict:
    """Create a Razorpay order server-side.

    The amount is computed from the *database* plan price -- never from a client
    supplied value -- which is why this function takes paise, not a plan id.
    """
    if amount_paise <= 0:
        raise PaymentError({"detail": "Invalid payment amount."}, code="invalid_amount")

    client = get_client()
    payload = {
        "amount": amount_paise,
        "currency": currency,
        "receipt": receipt[:40],
        "notes": notes or {},
        # Auto-capture removes an entire class of "authorized but never captured"
        # support tickets.
        "payment_capture": 1,
    }
    try:
        order = client.order.create(data=payload)
    except Exception as exc:  # SDK raises generic exceptions with provider text
        logger.exception("Razorpay order creation failed")
        raise PaymentError(
            {"detail": "Could not start the payment. Please retry."},
            code="gateway_error",
        )

    return order


def verify_checkout_signature(
    *, order_id: str, payment_id: str, signature: str
) -> bool:
    """Verify the signature returned by Razorpay Checkout on the client.

    Uses a constant-time comparison.  A failure here means the payload was forged
    or tampered with, so it must never activate a subscription.
    """
    if not order_id or not payment_id or not signature:
        return False

    _, key_secret = _credentials()
    message = f"{order_id}|{payment_id}".encode("utf-8")
    expected = hmac.new(key_secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_webhook_signature(*, raw_body: bytes, signature: str) -> bool:
    """Verify the ``X-Razorpay-Signature`` header against the raw body.

    ``raw_body`` must be the exact bytes Razorpay sent; re-serialising parsed JSON
    changes whitespace and key order and would break the HMAC.
    """
    webhook_secret = settings.RAZORPAY_WEBHOOK_SECRET
    if not webhook_secret or not signature:
        return False
    expected = hmac.new(
        webhook_secret.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def fetch_payment(payment_id: str) -> dict:
    """Authoritative payment lookup -- used for reconciliation tasks."""
    client = get_client()
    try:
        return client.payment.fetch(payment_id)
    except Exception:
        logger.exception(
            "Failed to fetch Razorpay payment", extra={"payment_id": payment_id}
        )
        raise PaymentError({"detail": "Could not verify the payment with the gateway."})


def fetch_order_payments(order_id: str) -> list[dict]:
    """All payment attempts made against an order (reconciliation helper)."""
    client = get_client()
    try:
        return client.order.payments(order_id).get("items", [])
    except Exception:
        logger.exception(
            "Failed to fetch Razorpay order payments", extra={"order_id": order_id}
        )
        raise PaymentError({"detail": "Could not verify the order with the gateway."})


def refund_payment(payment_id: str, amount_paise: int | None = None) -> dict:
    client = get_client()
    data = {"amount": amount_paise} if amount_paise else {}
    try:
        return client.payment.refund(payment_id, data)
    except Exception:
        logger.exception(
            "Failed to refund Razorpay payment", extra={"payment_id": payment_id}
        )
        raise PaymentError(
            {"detail": "Refund could not be initiated."}, code="refund_failed"
        )
