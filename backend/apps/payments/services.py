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
from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.constants import PaymentStatus, SubscriptionStatus
from apps.core.exceptions import PaymentError, code_for
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
        # Own savepoint: a constraint violation must not poison an outer transaction.
        with transaction.atomic():
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
        # A concurrent request with the same idempotency key won the insert; the
        # unique constraint guarantees exactly one row, so return that one.
        payment = None
        if idempotency_key:
            payment = Payment.objects.filter(
                user=user, plan=plan, idempotency_key=idempotency_key
            ).first()
        if payment is None:
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

    # A refunded payment is terminal.  Its checkout signature is still
    # cryptographically valid, so without this guard it could be replayed to
    # re-capture the payment and re-activate the refunded subscription.  This also
    # runs before the signature check so a bad signature cannot overwrite REFUNDED
    # with FAILED.
    _ensure_settleable(payment)

    if not gateway.verify_checkout_signature(
        order_id=order_id, payment_id=payment_id, signature=signature
    ):
        # Recorded under the row lock: a concurrent *valid* verification may have
        # captured this order since the read above, and must not be overwritten.
        _record_failure(
            payment.pk,
            failure_reason="Signature verification failed.",
            provider_payment_id=payment_id,
            provider_signature=signature[:255],
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


def _record_failure(
    payment_pk,
    *,
    failure_reason: str,
    provider_payment_id: str,
    provider_signature: str | None = None,
    failure_entity: dict | None = None,
) -> Payment | None:
    """Mark a payment FAILED unless a capture or refund already settled it.

    Lock, re-check and write happen in one transaction.  Checking first and
    writing later let a failure overwrite a concurrent capture; since FAILED is
    settleable, a later capture webhook then granted the same payment a second
    term.  Returns ``None`` when the payment was already settled.  (No
    ``select_related("subscription")``: PostgreSQL refuses FOR UPDATE on the
    nullable side of an outer join.)
    """
    with transaction.atomic():
        payment = (
            Payment.objects.select_for_update()
            .select_related("user", "plan")
            .get(pk=payment_pk)
        )
        if payment.status in {PaymentStatus.CAPTURED, PaymentStatus.REFUNDED}:
            return None
        payment.status = PaymentStatus.FAILED
        payment.failure_reason = failure_reason
        payment.provider_payment_id = provider_payment_id
        fields = ["status", "failure_reason", "provider_payment_id", "updated_at"]
        if provider_signature is not None:
            payment.provider_signature = provider_signature
            fields.append("provider_signature")
        if failure_entity is not None:
            payment.provider_payload = {
                **(payment.provider_payload or {}),
                "failure": failure_entity,
            }
            fields.append("provider_payload")
        payment.save(update_fields=fields)
        mark_subscription_failed(
            subscription=payment.subscription, user=payment.user, plan=payment.plan
        )
        return payment


# States a payment may be settled (captured) from.  FAILED is included because a
# customer can retry within the same Razorpay order after a declined attempt.
# REFUNDED is deliberately absent: it is terminal.
_SETTLEABLE_STATUSES = frozenset(
    {PaymentStatus.CREATED, PaymentStatus.AUTHORIZED, PaymentStatus.FAILED}
)


def _ensure_settleable(payment: Payment) -> None:
    if payment.status == PaymentStatus.REFUNDED:
        logger.warning(
            "Settlement refused for refunded payment",
            extra={"payment_id": str(payment.pk)},
        )
        raise PaymentError(
            {"detail": "This payment was refunded and cannot be verified again."},
            code="payment_refunded",
        )
    if payment.status != PaymentStatus.CAPTURED and (
        payment.status not in _SETTLEABLE_STATUSES
    ):
        raise PaymentError(
            {"detail": "This payment cannot be settled."}, code="payment_not_settleable"
        )


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
        # Lock and re-read here (not in the caller): a checkout callback and a
        # webhook can arrive together, and only the first may extend the term.
        locked = (
            Payment.objects.select_for_update()
            .select_related("user", "plan")
            .get(pk=payment.pk)
        )
        if locked.status == PaymentStatus.CAPTURED and locked.subscription_id:
            return locked
        # Re-checked under the row lock: a refund may have been committed between
        # the caller's read and this lock.
        _ensure_settleable(locked)
        return _apply_settlement(
            payment=locked, payment_id=payment_id, signature=signature
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
            # One WhatsApp message per payment, however often the webhook repeats.
            whatsapp_key=f"payment_success:{payment.pk}",
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
    # Rows written before content-addressed ids existed carry the provider header
    # id; a replay of the same signed body must still count as a duplicate.
    legacy = WebhookEvent.objects.filter(payload_hash=payload_hash).first()
    if legacy is not None:
        return legacy, False
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


def webhook_event_id(raw_body: bytes) -> str:
    """Content-addressed event id (the DB unique constraint then dedupes replays)."""
    return f"sha256:{hashlib.sha256(raw_body).hexdigest()[:40]}"


def _check_event_age(payload: dict) -> str:
    """Judge the *signed* ``created_at`` field of a webhook body.

    * ``"ok"``: fresh, or no timestamp supplied.
    * ``"stale"``: older than ``PAYMENT_WEBHOOK_MAX_AGE_SECONDS``.  Razorpay retries
      for roughly a day, so the window is days, not minutes; a long-dead signed
      body replayed by an attacker is dropped without being processed.
    * raises ``invalid_timestamp`` when present but malformed or in the future by
      more than ``PAYMENT_WEBHOOK_TOLERANCE_SECONDS`` (clock skew).
    """
    from django.conf import settings

    raw = payload.get("created_at") if isinstance(payload, dict) else None
    if raw is None:
        return "ok"
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or raw < 0:
        raise PaymentError(
            {"detail": "Malformed webhook timestamp."}, code="invalid_timestamp"
        )
    age = timezone.now().timestamp() - float(raw)
    if age < -settings.PAYMENT_WEBHOOK_TOLERANCE_SECONDS:
        raise PaymentError(
            {"detail": "Webhook timestamp is in the future."}, code="invalid_timestamp"
        )
    if age > settings.PAYMENT_WEBHOOK_MAX_AGE_SECONDS:
        logger.warning("Stale webhook ignored", extra={"age_seconds": int(age)})
        return "stale"
    return "ok"


def process_webhook(
    *, raw_body: bytes, signature: str, event_id: str, event_type: str, payload: dict
) -> dict:
    """Handle a Razorpay webhook end to end.

    Order of operations matters:

    1. Verify the signature over the *raw* body -- an unsigned request writes
       nothing, otherwise anyone could pre-claim a real event id (making the
       genuine delivery look like a duplicate) or fill the table.
    2. Record the event for idempotency.
    3. Apply the state change idempotently.  Only a *processed* event counts as
       a duplicate: a delivery whose handler failed is retried by Razorpay and
       must be processed again, not acknowledged and dropped.
    """
    # Verify *before* persisting anything: an unsigned request must neither write
    # to the database nor claim an event id that Razorpay's genuine delivery needs.
    if not gateway.verify_webhook_signature(raw_body=raw_body, signature=signature):
        logger.error(
            "Webhook signature verification failed", extra={"event_id": event_id}
        )
        raise PaymentError(
            {"detail": "Invalid webhook signature."}, code="invalid_signature"
        )

    # The signature covers the body only, so the X-Razorpay-Event-Id header is
    # attacker-controlled even on a genuine captured request.  Identity is
    # therefore derived from the signed body itself: a replay with a fresh header
    # id hashes to the same id and is a duplicate.
    event_id = webhook_event_id(raw_body)
    window = _check_event_age(payload)
    if window == "stale":
        return {"status": "ignored", "reason": "stale", "event_id": event_id}

    event, created = record_webhook_event(
        event_id=event_id,
        event_type=event_type,
        payload=payload,
        raw_body=raw_body,
        signature_valid=True,
    )

    if not created and event.processed:
        logger.info(
            "Duplicate webhook ignored",
            extra={"event_id": event_id, "event_type": event_type},
        )
        return {"status": "duplicate", "event_id": event_id, "processed": True}
    # ``not created`` and unprocessed means an earlier attempt failed (we returned
    # non-2xx so Razorpay is retrying): fall through and run the handler again.
    # Handlers are idempotent, so a concurrent redelivery cannot double-apply.

    handler = _WEBHOOK_HANDLERS.get(event_type)
    if handler is None:
        # Unknown/unused events are acknowledged so Razorpay stops retrying.
        event.processed = True
        event.processed_at = timezone.now()
        event.processing_error = ""
        event.save(update_fields=["processed", "processed_at", "processing_error"])
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
    event.processing_error = ""
    event.save(update_fields=["processed", "processed_at", "processing_error"])
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
    if payment.status == PaymentStatus.REFUNDED:
        # A late or replayed capture must never undo a refund.
        return {"matched": True, "ignored": "already refunded"}

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

    # _settle_payment locks the row and re-checks, so a concurrent capture wins once.
    try:
        _settle_payment(
            payment=payment,
            payment_id=entity.get("id", payment.provider_payment_id),
            signature="",
        )
    except PaymentError as exc:
        if code_for(exc) == "payment_refunded":  # refund won the race for the lock
            return {"matched": True, "ignored": "already refunded"}
        raise
    return {"matched": True, "activated": True}


def handle_payment_failed(payload: dict) -> dict:
    """``payment.failed`` -- record the decline so the UI can explain it."""
    entity = _payment_entity(payload)
    payment = _find_payment(entity)
    if payment is None:
        return {"matched": False}
    error = (
        entity.get("error_description")
        or entity.get("error_reason")
        or "Payment failed."
    )
    # A capture/refund that already won (or wins while this event is in flight)
    # must not be undone by a late failure -- re-checked under the row lock.
    failed = _record_failure(
        payment.pk,
        failure_reason=str(error)[:1000],
        provider_payment_id=entity.get("id", payment.provider_payment_id),
        failure_entity=entity,
    )
    if failed is None:
        payment.refresh_from_db(fields=["status"])
        return {"matched": True, "ignored": f"already {payment.status}"}
    payment = failed
    try:
        from apps.notifications.services import notify_user

        notify_user(
            user=payment.user,
            kind="payment_failed",
            context={"plan_name": payment.plan.name, "reason": str(error)},
            whatsapp_key=f"payment_failed:{payment.pk}",
        )
    except Exception:  # pragma: no cover
        logger.exception("Failed to queue payment-failure notification")
    return {"matched": True, "failed": True}


def handle_payment_refunded(payload: dict) -> dict:
    """``refund.processed`` -- record the refund; end the term once fully refunded.

    Refunds are accumulated per refund id (so a redelivered event is not counted
    twice): several partial refunds that add up to the full amount count as a
    full refund.  A full refund removes *this payment's* term from the
    subscription.  Renewals stack onto one subscription row, so cancelling the
    row outright would also take away terms paid for by other payments.
    """
    refund_entity = ((payload.get("payload") or {}).get("refund") or {}).get(
        "entity"
    ) or {}
    payment_id = refund_entity.get("payment_id")
    if not payment_id:
        return {"matched": False}

    with transaction.atomic():
        payment = (
            Payment.objects.select_for_update(of=("self",))
            .select_related("user", "plan", "subscription")
            .filter(provider_payment_id=payment_id)
            .first()
        )
        if payment is None:
            return {"matched": False}
        if payment.status == PaymentStatus.REFUNDED:
            return {"matched": True, "already_refunded": True}

        refund_id = refund_entity.get("id", "")
        provider_payload = payment.provider_payload or {}
        refunds = dict(provider_payload.get("refunds") or {})
        refund_amount = refund_entity.get("amount")
        refunds[refund_id] = (
            int(refund_amount) if refund_amount is not None else payment.amount_paise
        )
        payment.provider_refund_id = refund_id
        payment.provider_payload = {**provider_payload, "refunds": refunds}

        if sum(refunds.values()) < payment.amount_paise:
            payment.save(
                update_fields=["provider_refund_id", "provider_payload", "updated_at"]
            )
            return {"matched": True, "partial_refund": True}

        payment.status = PaymentStatus.REFUNDED
        payment.save(
            update_fields=[
                "status",
                "provider_refund_id",
                "provider_payload",
                "updated_at",
            ]
        )
        _revoke_refunded_term(payment)
    return {"matched": True, "refunded": True}


def _revoke_refunded_term(payment: Payment) -> None:
    """Take the refunded payment's term off its subscription (inside a transaction)."""
    if not payment.subscription_id:
        return
    subscription = Subscription.objects.select_for_update().get(
        pk=payment.subscription_id
    )
    if subscription.status != SubscriptionStatus.ACTIVE:
        return

    now = timezone.now()
    remaining_end = None
    if subscription.end_date:
        remaining_end = subscription.end_date - timedelta(
            days=payment.plan.duration_days
        )
    if remaining_end is not None and remaining_end > now:
        # Other paid terms remain on this row: shorten it, keep it active.
        subscription.end_date = remaining_end
        subscription.save(update_fields=["end_date", "updated_at"])
    else:
        subscription.status = SubscriptionStatus.CANCELLED
        subscription.end_date = now
        subscription.save(update_fields=["status", "end_date", "updated_at"])
    invalidate_entitlement_cache(payment.user)


def handle_subscription_charged(payload: dict) -> dict:
    """``subscription.charged`` -- recurring charge for an existing subscription.

    Mapped onto the same activation path so a renewal extends the term instead of
    creating a parallel subscription.
    """
    entity = ((payload.get("payload") or {}).get("payment") or {}).get("entity") or {}
    return handle_payment_captured({"payload": {"payment": {"entity": entity}}})


_WEBHOOK_HANDLERS = {
    "payment.captured": handle_payment_captured,
    "payment.failed": handle_payment_failed,
    "refund.processed": handle_payment_refunded,
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
    cutoff = timezone.now() - timedelta(minutes=older_than_minutes)
    stale = Payment.objects.filter(
        status__in=[PaymentStatus.CREATED, PaymentStatus.AUTHORIZED],
        created_at__lt=cutoff,
    ).select_related("user", "plan")

    resolved = 0
    for payment in stale.iterator():
        try:
            # A payment still in CREATED has no provider_payment_id (that is only
            # learned from the callback/webhook we missed), so ask the gateway for
            # the payments made against the *order*.
            entities = gateway.fetch_order_payments(payment.provider_order_id)
            captured = next((e for e in entities if e.get("status") == "captured"), None)
            if captured is not None:
                handle_payment_captured({"payload": {"payment": {"entity": captured}}})
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
