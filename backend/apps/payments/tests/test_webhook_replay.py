"""W1: webhook replay protection.

Security assumptions
--------------------
* Razorpay signs the raw body only.  ``X-Razorpay-Event-Id`` is *not* signed, so it
  is never used as identity; the event id is a hash of the signed body.
* Razorpay retries for about a day, so signed ``created_at`` is checked against a
  days-long window (replay of ancient bodies) plus a clock-skew bound for future
  timestamps -- not a 5-minute window, which would drop legitimate retries.
"""

import json
import time

import pytest

from apps.core.constants import PaymentStatus
from apps.payments import services
from apps.payments.models import WebhookEvent
from apps.payments.tests.test_payments import (
    WEBHOOK_URL,
    make_payment,
    sign_webhook,
    webhook_payload,
)
from apps.subscriptions.models import Subscription

pytestmark = pytest.mark.django_db


def _post(api_client, body: bytes, *, event_id="evt", signature=None):
    return api_client.post(
        WEBHOOK_URL,
        data=body,
        content_type="application/json",
        HTTP_X_RAZORPAY_SIGNATURE=signature or sign_webhook(body),
        HTTP_X_RAZORPAY_EVENT_ID=event_id,
    )


def _body(order, pay, plan, **extra):
    payload = webhook_payload(order_id=order, payment_id=pay, amount_paise=plan.price_paise)
    payload.update(extra)
    return json.dumps(payload).encode()


def test_invalid_signature_rejected_and_nothing_written(api_client, student, plan):
    make_payment(student, plan, order_id="o1")
    body = _body("o1", "p1", plan)
    r = _post(api_client, body, signature="0" * 64)
    assert r.status_code == 400
    assert not WebhookEvent.objects.exists() and not Subscription.objects.exists()


def test_altered_body_rejected(api_client, student, plan):
    make_payment(student, plan, order_id="o2")
    body = _body("o2", "p2", plan)
    r = _post(api_client, body.replace(b"captured", b"refunded!"), signature=sign_webhook(body))
    assert r.status_code == 400


def test_replayed_valid_body_with_fresh_event_id_is_a_duplicate(api_client, student, plan):
    make_payment(student, plan, order_id="o3")
    body = _body("o3", "p3", plan)
    first = _post(api_client, body, event_id="evt-A")
    second = _post(api_client, body, event_id="evt-B")  # attacker swaps the header
    assert first.data["status"] == "processed"
    assert second.data["status"] == "duplicate"
    assert WebhookEvent.objects.count() == 1
    assert Subscription.objects.filter(user=student).count() == 1


def test_legitimate_retry_with_same_id_is_a_duplicate(api_client, student, plan):
    make_payment(student, plan, order_id="o4")
    body = _body("o4", "p4", plan)
    assert _post(api_client, body).data["status"] == "processed"
    assert _post(api_client, body).data["status"] == "duplicate"


def test_failed_handler_is_retried_not_dropped(api_client, student, plan, monkeypatch):
    make_payment(student, plan, order_id="o5")
    body = _body("o5", "p5", plan)
    real = services._WEBHOOK_HANDLERS["payment.captured"]

    def boom(_payload):
        raise RuntimeError("transient")

    monkeypatch.setitem(services._WEBHOOK_HANDLERS, "payment.captured", boom)
    assert _post(api_client, body).status_code >= 500
    monkeypatch.setitem(services._WEBHOOK_HANDLERS, "payment.captured", real)
    retry = _post(api_client, body)
    assert retry.status_code == 200 and retry.data["status"] == "processed"
    assert Subscription.objects.filter(user=student).count() == 1


def test_concurrent_duplicate_delivery_converges(student, plan):
    """Second delivery arrives while the first row exists but is unprocessed."""
    make_payment(student, plan, order_id="o6")
    body = _body("o6", "p6", plan)
    payload = json.loads(body)
    kwargs = dict(raw_body=body, signature=sign_webhook(body), event_id="x",
                  event_type="payment.captured", payload=payload)
    services.record_webhook_event(
        event_id=services.webhook_event_id(body), event_type="payment.captured",
        payload=payload, raw_body=body, signature_valid=True,
    )
    results = [services.process_webhook(**kwargs), services.process_webhook(**kwargs)]
    assert results[0]["status"] == "processed" and results[1]["status"] == "duplicate"
    assert Subscription.objects.filter(user=student).count() == 1
    assert WebhookEvent.objects.count() == 1


def test_stale_signed_timestamp_is_ignored_without_processing(api_client, student, plan, settings):
    make_payment(student, plan, order_id="o7")
    old = int(time.time()) - settings.PAYMENT_WEBHOOK_MAX_AGE_SECONDS - 60
    r = _post(api_client, _body("o7", "p7", plan, created_at=old))
    assert r.status_code == 200 and r.data["status"] == "ignored"
    assert not Subscription.objects.exists() and not WebhookEvent.objects.exists()


def test_delayed_but_within_window_retry_still_processes(api_client, student, plan):
    make_payment(student, plan, order_id="o8")
    r = _post(api_client, _body("o8", "p8", plan, created_at=int(time.time()) - 20 * 3600))
    assert r.data["status"] == "processed"


@pytest.mark.parametrize("bad", ["yesterday", -5, True, [1]])
def test_malformed_timestamp_rejected(api_client, student, plan, bad):
    make_payment(student, plan, order_id="o9")
    r = _post(api_client, _body("o9", "p9", plan, created_at=bad))
    assert r.status_code == 400 and not Subscription.objects.exists()


def test_future_timestamp_beyond_skew_rejected(api_client, student, plan):
    make_payment(student, plan, order_id="o10")
    r = _post(api_client, _body("o10", "p10", plan, created_at=int(time.time()) + 3600))
    assert r.status_code == 400


def test_missing_timestamp_is_accepted(api_client, student, plan):
    make_payment(student, plan, order_id="o11")
    assert _post(api_client, _body("o11", "p11", plan)).data["status"] == "processed"


def test_refund_then_late_capture_ordering(api_client, student, plan):
    pay = make_payment(student, plan, order_id="o12", provider_payment_id="p12",
                       status=PaymentStatus.REFUNDED)
    r = _post(api_client, _body("o12", "p12", plan, created_at=int(time.time())))
    assert r.status_code == 200
    pay.refresh_from_db()
    assert pay.status == PaymentStatus.REFUNDED and not Subscription.objects.exists()


def _refund_body(pay, amount, refund_id=None, **extra):
    return json.dumps({"event": "refund.processed", **extra, "payload": {"refund": {
        "entity": {"id": refund_id or f"rfnd_{pay}", "payment_id": pay,
                   "amount": amount}}}}).encode()


def test_refund_before_capture_is_not_lost(api_client, student, plan, monkeypatch):
    """LS-01: the refund arrives while our row still lacks the payment id."""
    pay = make_payment(student, plan, order_id="o13")  # CREATED, no provider_payment_id
    monkeypatch.setattr(services.gateway, "fetch_payment",
                        lambda pid: {"id": pid, "order_id": "o13"})
    r = _post(api_client, _refund_body("p13", plan.price_paise))
    assert r.status_code == 200 and r.data["result"]["refunded"]
    pay.refresh_from_db()
    assert pay.status == PaymentStatus.REFUNDED and pay.provider_payment_id == "p13"

    # The delayed capture now lands and must not grant access.
    r = _post(api_client, _body("o13", "p13", plan, created_at=int(time.time())))
    assert r.status_code == 200
    pay.refresh_from_db()
    assert pay.status == PaymentStatus.REFUNDED and not Subscription.objects.exists()


def test_partial_refunds_before_capture_add_up_once(api_client, student, plan, monkeypatch):
    """Partial refund lands early, capture follows, a redelivery is not double-counted."""
    pay = make_payment(student, plan, order_id="o15")
    monkeypatch.setattr(services.gateway, "fetch_payment",
                        lambda pid: {"id": pid, "order_id": "o15"})
    half, now = plan.price_paise // 2, int(time.time())

    r = _post(api_client, _refund_body("p15", half, "rfnd_a", created_at=now))
    assert r.data["result"]["partial_refund"]
    # A partial refund leaves the purchase valid: the capture still activates it.
    _post(api_client, _body("o15", "p15", plan, created_at=now))
    pay.refresh_from_db()
    assert pay.status == PaymentStatus.CAPTURED
    assert Subscription.objects.get(user=student).status == "active"

    # Same refund re-sent in a different body (not a byte-identical duplicate).
    r = _post(api_client, _refund_body("p15", half, "rfnd_a", created_at=now + 1))
    assert r.data["result"]["partial_refund"]
    pay.refresh_from_db()
    assert pay.status == PaymentStatus.CAPTURED

    # The second, distinct refund completes the amount and ends access.
    r = _post(api_client, _refund_body("p15", plan.price_paise - half, "rfnd_b"))
    assert r.data["result"]["refunded"]
    pay.refresh_from_db()
    assert pay.status == PaymentStatus.REFUNDED
    assert Subscription.objects.get(user=student).status == "cancelled"


def test_refund_for_foreign_order_is_acknowledged(api_client, plan, monkeypatch):
    monkeypatch.setattr(services.gateway, "fetch_payment",
                        lambda pid: {"id": pid, "order_id": "order_not_ours"})
    r = _post(api_client, _refund_body("p14", plan.price_paise))
    assert r.status_code == 200 and r.data["result"] == {"matched": False}


def test_providers_use_independent_throttle_scopes():
    from apps.notifications.views_whatsapp import WebhookView
    from apps.payments.views import PaymentWebhookView

    assert PaymentWebhookView.throttle_scope != WebhookView.throttle_scope
