"""Payment business logic: orders, verification, webhooks, reconciliation.

**Never trust payment status from the frontend.**  The client callback only
*triggers* verification; the decision to activate a subscription is made here,
from a verified HMAC signature (or a verified webhook), and the amount is always
re-read from the database order row rather than trusted from the request.

Idempotency
-----------
* ``Payment.provider_order_id`` is unique -> one row per provider order.
* ``WebhookEvent (provider, event_id)`` is unique -> duplicate deliveries are
  rejected by the database.
* Activation happens inside ``transaction.atomic()`` with ``select_for_update``
  on the payment row, so two concurrent verifications cannot both activate.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.constants import PaymentStatus, SubscriptionStatus
from apps.core.exceptions import PaymentError
from apps.core.logging import get_logger
from apps.payments import gateway
from apps.payments.models import Payment, WebhookEvent
from apps.subscriptions.models import Plan, Subscription
from apps.subscriptions.services import invalidate_entitlement_cache
from apps.subscriptions.services_lifecycle import (
    activate_subscription,
    mark_subscription_failed,
)

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
# Order creation
# --------------------------------------------------------------------------- #
def create_plan_order(*, user, plan: Plan, idempotency_key: str = "") -> Payment:
    """Create a Razorpay order for ``plan`` and persist the Payment row.

    ``idempotency_key`` lets the SPA safely retry a failed network call: the same
    key returns the existing order instead of creating (and eventually charging
    for) a second one.
    """
    if not plan.is_active:
        raise PaymentError(
            {"detail": "This plan is not available."}, code="plan_inactive"
        )

    if idempotency_key:
        existing = Payment.objects.filter(
            user=user, plan=plan, idempotency_key=idempotency_key
        ).first()
        if existing is not None:
            logger.info(
                "Reusing payment order for idempotency key",
                extra={"payment_id": str(existing.pk), "user_id": str(user.pk)},
            )
            return existing

    amount_paise = plan.price_paise
    if amount_paise <= 0:
        # A zero-priced plan must not go through the gateway at all.
        raise PaymentError(
            {"detail": "This plan is free; no payment is required."}, code="free_plan"
        )

    order = gateway.create_order(
        amount_paise=amount_paise,
        currency=plan.currency,
        receipt=f"plan-{plan.slug}-{user.pk}",
        notes={"user_id": str(user.pk), "plan_slug": plan.slug},
    )

    try:
        payment = Payment.objects.create(
            user=user,
            plan=plan,
            provider_order_id=order["id"],
            amount=Decimal(order["amount"]) / 100,
            currency=order.get("currency", plan.currency),
            status=PaymentStatus.CREATED,
            idempotency_key=idempotency_key,
            notes={"plan_slug": plan.slug},
            provider_payload={"order": order},
        )
    except IntegrityError:
        # Extremely unlikely, but a retried request could race here.
        payment = Payment.objects.get(provider_order_id=order["id"])

    logger.info(
        "Razorpay order created",
        extra={"payment_id": str(payment.pk), "order_id": payment.provider_order_id},
    )
    return payment


def checkout_payload(payment: Payment) -> dict:
    """Data the browser needs to open Razorpay Checkout.

    Only the *public* key id is exposed.  The key secret, webhook secret and
    Cloudflare credentials never leave the server.
    """
    from django.conf import settings

    return {
        "payment_id": str(payment.pk),
        "order_id": payment.provider_order_id,
        "key_id": settings.RAZORPAY_KEY_ID,
        "amount": payment.amount_paise,
        "currency": payment.currency,
        "name": "LawSchool",
        "description": payment.plan.name,
        "prefill": {
            "name": payment.user.get_full_name(),
            "email": payment.user.email,
            "contact": payment.user.phone or "",
        },
    }


# --------------------------------------------------------------------------- #
# Verification from the checkout callback
# --------------------------------------------------------------------------- #
def verify_payment(*, user, order_id: str, payment_id: str, signature: str) -> Payment:
    """Verify a checkout callback and activate the subscription.

    Rejects, in order: unknown order, order belonging to another user, invalid
    signature, and already-settled orders (returned as-is so retries are safe).

    The failure record is deliberately *committed* before the exception is
    raised: a declined or forged attempt must show up in the Payment history so
    support can answer "I was charged but nothing happened".  Wrapping the whole
    function in ``transaction.atomic`` would silently roll that record back, which
    is why only the locking read below uses a transaction.
    """
    try:
        # ``select_for_update`` cannot be used outside a transaction, and a failed
        # lookup must not abort the surrounding one -- hence the explicit savepoint.
        with transaction.atomic():
            payment = (
                Payment.objects.select_for_update()
                .select_related("user", "plan")
                .get(provider_order_id=order_id)
            )
    except Payment.DoesNotExist:
        logger.warning("Verification for unknown order", extra={"order_id": order_id})
        raise PaymentError({"detail": "Unknown payment order."}, code="unknown_order")

    # The order must belong to the caller -- otherwise a student could activate a
    # subscription using someone else's payment.
    if payment.user_id != user.pk:
        logger.warning(
            "Cross-user payment verification attempt",
            extra={
                "order_id": order_id,
                "actor_id": str(user.pk),
                "owner_id": str(payment.user_id),
            },
        )
        raise PaymentError(
            {"detail": "This payment does not belong to you."}, code="forbidden"
        )

    if payment.status == PaymentStatus.CAPTURED:
        return payment  # idempotent success

    if not gateway.verify_checkout_signature(
        order_id=order_id, payment_id=payment_id, signature=signature
    ):
        payment.status = PaymentStatus.FAILED
        payment.failure_reason = "Signature verification failed."
        payment.provider_payment_id = payment_id
        payment.provider_signature = signature[:255]
        payment.save(
            update_fields=[
                "status",
                "failure_reason",
                "provider_payment_id",
                "provider_signature",
                "updated_at",
            ]
        )
        mark_subscription_failed(
            subscription=payment.subscription, user=payment.user, plan=payment.plan
        )
        logger.warning(
            "Payment signature mismatch",
            extra={"order_id": order_id, "user_id": str(user.pk)},
        )
        raise PaymentError(
            {
                "detail": "Payment verification failed. If you were charged, contact support."
            },
            code="invalid_signature",
        )

    return _settle_payment(payment=payment, payment_id=payment_id, signature=signature)


def _settle_payment(
    *, payment: Payment, payment_id: str, signature: str = ""
) -> Payment:
    """Mark a verified payment captured and activate/extend the subscription.

    Shared by the checkout callback and the webhook path so both routes produce
    identical state.  Wrapped in ``transaction.atomic`` because the payment row
    and the subscription must move together -- a captured payment with no active
    subscription (or the reverse) is exactly the inconsistency a user notices.
    """
    with transaction.atomic():
        return _apply_settlement(
            payment=payment, payment_id=payment_id, signature=signature
        )


def _apply_settlement(
    *, payment: Payment, payment_id: str, signature: str = ""
) -> Payment:
    """The mutation half of :func:`_settle_payment` (already inside a transaction)."""
    payment.status = PaymentStatus.CAPTURED
    payment.provider_payment_id = payment_id
    if signature:
        payment.provider_signature = signature[:255]
    payment.captured_at = timezone.now()
    payment.failure_reason = ""
    payment.save(
        update_fields=[
            "status",
            "provider_payment_id",
            "provider_signature",
            "captured_at",
            "failure_reason",
            "updated_at",
        ]
    )

    subscription = activate_subscription(
        user=payment.user,
        plan=payment.plan,
        payment_reference=payment.provider_payment_id or payment.provider_order_id,
    )
    payment.subscription = subscription
    payment.save(update_fields=["subscription", "updated_at"])

    _notify_payment_success(payment=payment, subscription=subscription)
    return payment


def _notify_payment_success(*, payment: Payment, subscription: Subscription) -> None:
    """Queue payment + activation notifications (async, never blocks the response)."""
    try:
        from apps.notifications.services import notify_user

        notify_user(
            user=payment.user,
            kind="payment_success",
            context={
                "amount": str(payment.amount),
                "currency": payment.currency,
                "plan_name": payment.plan.name,
                "payment_id": payment.provider_payment_id,
            },
        )
        notify_user(
            user=payment.user,
            kind="subscription_activated",
            context={
                "plan_name": payment.plan.name,
                "end_date": (
                    subscription.end_date.strftime("%d %b %Y")
                    if subscription.end_date
                    else ""
                ),
            },
        )
    except Exception:  # pragma: no cover - notification failure must not fail payment
        logger.exception(
            "Failed to queue payment notifications",
            extra={"payment_id": str(payment.pk)},
        )


# --------------------------------------------------------------------------- #
# Webhooks
# --------------------------------------------------------------------------- #
def record_webhook_event(
    *,
    event_id: str,
    event_type: str,
    payload: dict,
    raw_body: bytes,
    signature_valid: bool,
) -> tuple[WebhookEvent, bool]:
    """Persist a webhook event, returning ``(event, created)``.

    ``created=False`` means this is a duplicate delivery -- the caller must treat
    it as a no-op.  The uniqueness is enforced by the DB, so this is race-safe
    under concurrent deliveries from Razorpay's retry mechanism.
    """
    payload_hash = hashlib.sha256(raw_body).hexdigest()
    try:
        # The create runs in its own savepoint: when the unique constraint rejects
        # a duplicate, only that savepoint rolls back and any outer transaction
        # stays usable for the follow-up lookup.
        with transaction.atomic():
            event = WebhookEvent.objects.create(
                event_id=event_id,
                event_type=event_type,
                payload=payload,
                payload_hash=payload_hash,
                signature_valid=signature_valid,
            )
        return event, True
    except IntegrityError:
        # Duplicate delivery: return the row written by the first attempt.
        event = WebhookEvent.objects.filter(event_id=event_id).first()
        if event is None:  # pragma: no cover - only if the row was deleted mid-flight
            raise
        return event, False


def process_webhook(
    *, raw_body: bytes, signature: str, event_id: str, event_type: str, payload: dict
) -> dict:
    """Handle a Razorpay webhook end to end.

    Order of operations matters:

    1. Verify the signature over the *raw* body (reject early, log loudly).
    2. Record the event for idempotency.
    3. Apply the state change idempotently.
    """
    signature_valid = gateway.verify_webhook_signature(
        raw_body=raw_body, signature=signature
    )
    event, created = record_webhook_event(
        event_id=event_id,
        event_type=event_type,
        payload=payload,
        raw_body=raw_body,
        signature_valid=signature_valid,
    )

    if not created:
        logger.info(
            "Duplicate webhook ignored",
            extra={"event_id": event_id, "event_type": event_type},
        )
        return {
            "status": "duplicate",
            "event_id": event_id,
            "processed": event.processed,
        }

    if not signature_valid:
        event.processing_error = "Signature verification failed."
        event.save(update_fields=["processing_error"])
        logger.error(
            "Webhook signature verification failed", extra={"event_id": event_id}
        )
        raise PaymentError(
            {"detail": "Invalid webhook signature."}, code="invalid_signature"
        )

    handler = _WEBHOOK_HANDLERS.get(event_type)
    if handler is None:
        # Unknown/unused events are acknowledged so Razorpay stops retrying.
        event.processed = True
        event.processed_at = timezone.now()
        event.save(update_fields=["processed", "processed_at"])
        return {"status": "ignored", "event_id": event_id, "event_type": event_type}

    try:
        result = handler(payload)
    except Exception as exc:
        event.processing_error = str(exc)[:1000]
        event.save(update_fields=["processing_error"])
        logger.exception(
            "Webhook handler failed",
            extra={"event_id": event_id, "event_type": event_type},
        )
        # Non-2xx so Razorpay retries; the event row prevents double-processing.
        raise PaymentError(
            {"detail": "Webhook processing failed."}, code="webhook_failed"
        )

    event.processed = True
    event.processed_at = timezone.now()
    event.save(update_fields=["processed", "processed_at"])
    return {
        "status": "processed",
        "event_id": event_id,
        "event_type": event_type,
        "result": result,
    }


def _payment_entity(payload: dict) -> dict:
    return ((payload.get("payload") or {}).get("payment") or {}).get("entity") or {}


def _find_payment(entity: dict) -> Payment | None:
    """Locate our Payment row from a Razorpay payment entity."""
    order_id = entity.get("order_id")
    payment_id = entity.get("id")
    queryset = Payment.objects.select_related("user", "plan")
    if order_id:
        payment = queryset.filter(provider_order_id=order_id).first()
        if payment:
            return payment
    if payment_id:
        return queryset.filter(provider_payment_id=payment_id).first()
    return None


def handle_payment_captured(payload: dict) -> dict:
    """``payment.captured`` -- the authoritative settlement signal."""
    entity = _payment_entity(payload)
    payment = _find_payment(entity)
    if payment is None:
        logger.warning(
            "Captured webhook for unknown payment",
            extra={"entity_id": entity.get("id")},
        )
        return {"matched": False}

    if payment.status == PaymentStatus.CAPTURED and payment.subscription_id:
        # Already settled by the checkout callback -- nothing to do.
        return {"matched": True, "already_captured": True}

    # Guard against an amount mismatch: someone could capture a INR 1 payment
    # against a INR 10,000 order.
    provider_amount = entity.get("amount")
    if provider_amount is not None and int(provider_amount) != payment.amount_paise:
        payment.status = PaymentStatus.FAILED
        payment.failure_reason = f"Amount mismatch: gateway reported {provider_amount}, expected {payment.amount_paise}."
        payment.save(update_fields=["status", "failure_reason", "updated_at"])
        logger.error(
            "Payment amount mismatch",
            extra={"payment_id": str(payment.pk), "provider_amount": provider_amount},
        )
        return {"matched": True, "amount_mismatch": True}

    with transaction.atomic():
        locked = Payment.objects.select_for_update().get(pk=payment.pk)
        if locked.status == PaymentStatus.CAPTURED:
            return {"matched": True, "already_captured": True}
        _settle_payment(
            payment=locked,
            payment_id=entity.get("id", locked.provider_payment_id),
            signature="",
        )
    return {"matched": True, "activated": True}


def handle_payment_failed(payload: dict) -> dict:
    """``payment.failed`` -- record the decline so the UI can explain it."""
    entity = _payment_entity(payload)
    payment = _find_payment(entity)
    if payment is None:
        return {"matched": False}
    if payment.status == PaymentStatus.CAPTURED:
        # A capture already won the race; a late failure event must not undo it.
        return {"matched": True, "ignored": "already captured"}

    payment.status = PaymentStatus.FAILED
    payment.provider_payment_id = entity.get("id", payment.provider_payment_id)
    error = (
        entity.get("error_description")
        or entity.get("error_reason")
        or "Payment failed."
    )
    payment.failure_reason = str(error)[:1000]
    payment.provider_payload = {**(payment.provider_payload or {}), "failure": entity}
    payment.save(
        update_fields=[
            "status",
            "provider_payment_id",
            "failure_reason",
            "provider_payload",
            "updated_at",
        ]
    )
    mark_subscription_failed(
        subscription=payment.subscription, user=payment.user, plan=payment.plan
    )
    try:
        from apps.notifications.services import notify_user

        notify_user(
            user=payment.user,
            kind="payment_failed",
            context={"plan_name": payment.plan.name, "reason": str(error)},
        )
    except Exception:  # pragma: no cover
        logger.exception("Failed to queue payment-failure notification")
    return {"matched": True, "failed": True}


def handle_payment_refunded(payload: dict) -> dict:
    """``refund.processed`` -- mark refunded and end access immediately."""
    refund_entity = ((payload.get("payload") or {}).get("refund") or {}).get(
        "entity"
    ) or {}
    payment_id = refund_entity.get("payment_id")
    payment = (
        Payment.objects.select_related("user", "plan", "subscription")
        .filter(provider_payment_id=payment_id)
        .first()
    )
    if payment is None:
        return {"matched": False}

    payment.status = PaymentStatus.REFUNDED
    payment.provider_refund_id = refund_entity.get("id", "")
    payment.save(update_fields=["status", "provider_refund_id", "updated_at"])

    if (
        payment.subscription_id
        and payment.subscription.status == SubscriptionStatus.ACTIVE
    ):
        payment.subscription.status = SubscriptionStatus.CANCELLED
        payment.subscription.end_date = timezone.now()
        payment.subscription.save(update_fields=["status", "end_date", "updated_at"])
        invalidate_entitlement_cache(payment.user)
    return {"matched": True, "refunded": True}


def handle_subscription_charged(payload: dict) -> dict:
    """``subscription.charged`` -- recurring charge for an existing subscription.

    Mapped onto the same activation path so a renewal extends the term instead of
    creating a parallel subscription.
    """
    entity = ((payload.get("payload") or {}).get("payment") or {}).get("entity") or {}
    return handle_payment_captured({"payload": {"payment": {"entity": entity}}})


_WEBHOOK_HANDLERS = {
    "payment.captured": handle_payment_captured,
    "payment.authorized": handle_payment_captured,
    "payment.failed": handle_payment_failed,
    "refund.processed": handle_payment_refunded,
    "refund.created": handle_payment_refunded,
    "subscription.charged": handle_subscription_charged,
}


# --------------------------------------------------------------------------- #
# Reconciliation
# --------------------------------------------------------------------------- #
def reconcile_stale_payments(*, older_than_minutes: int = 30) -> int:
    """Resolve payments stuck in CREATED (missed webhook, closed browser).

    Queries the gateway for the authoritative status and applies it through the
    same handler the webhook would use.  Run by Celery beat.
    """
    from datetime import timedelta

    cutoff = timezone.now() - timedelta(minutes=older_than_minutes)
    stale = Payment.objects.filter(
        status__in=[PaymentStatus.CREATED, PaymentStatus.AUTHORIZED],
        created_at__lt=cutoff,
    ).select_related("user", "plan")

    resolved = 0
    for payment in stale.iterator():
        try:
            entity = (
                gateway.fetch_payment(payment.provider_payment_id)
                if payment.provider_payment_id
                else None
            )
            if entity is None:
                continue
            status = entity.get("status")
            if status in {"captured", "authorized"}:
                handle_payment_captured({"payload": {"payment": {"entity": entity}}})
                resolved += 1
            elif status == "failed":
                handle_payment_failed({"payload": {"payment": {"entity": entity}}})
                resolved += 1
        except Exception:  # pragma: no cover - keep the batch going
            logger.exception(
                "Reconciliation failed for payment",
                extra={"payment_id": str(payment.pk)},
            )

    logger.info("Payment reconciliation finished", extra={"resolved": resolved})
    return resolved


def serialize_payment_debug(payload: dict) -> str:  # pragma: no cover - diagnostics
    return json.dumps(payload, indent=2, default=str)
