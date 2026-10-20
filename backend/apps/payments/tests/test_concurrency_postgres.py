"""Real row-lock behaviour, so PostgreSQL only.

SQLite ignores ``select_for_update`` and serialises writers anyway, so these
tests would prove nothing there; CI runs them via ``TEST_DATABASE_URL``.  Each
thread uses its own connection and its own transaction, like two web workers
handling a checkout callback and a duplicate callback (or the webhook) at once.
"""

from __future__ import annotations

import threading
from datetime import timedelta

import pytest
from django.db import connection, connections

from apps.core.constants import PaymentStatus, SubscriptionStatus
from apps.payments import services
from apps.payments.models import Payment
from apps.payments.tests.test_payments import make_payment, sign_checkout
from apps.subscriptions.models import Subscription

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(
        connection.vendor != "postgresql",
        reason="needs PostgreSQL row locks; run with TEST_DATABASE_URL",
    ),
]


def _race(n, work):
    """Run ``work`` in ``n`` threads released at the same instant."""
    barrier = threading.Barrier(n)
    errors: list[BaseException] = []

    def run():
        try:
            barrier.wait()
            work()
        except BaseException as exc:  # surfaced below, never swallowed
            errors.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=run) for _ in range(n)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    return errors


def test_simultaneous_verifications_extend_the_term_exactly_once(student, plan):
    payment = make_payment(student, plan, order_id="order_race_1")
    signature = sign_checkout("order_race_1", "pay_race_1")

    errors = _race(
        6,
        lambda: services.verify_payment(
            user=student, order_id="order_race_1", payment_id="pay_race_1", signature=signature
        ),
    )

    assert errors == []
    payment.refresh_from_db()
    assert payment.status == PaymentStatus.CAPTURED
    subs = list(Subscription.objects.filter(user=student))
    assert len(subs) == 1
    (sub,) = subs
    assert sub.status == SubscriptionStatus.ACTIVE
    assert payment.subscription_id == sub.pk
    # One paid term, not six stacked renewals.
    assert sub.end_date - sub.start_date == timedelta(days=plan.duration_days)


@pytest.mark.parametrize("round_", range(15))
def test_a_forged_signature_racing_a_valid_one_cannot_undo_the_capture(student, plan, round_):
    order = f"order_race_2_{round_}"
    make_payment(student, plan, order_id=order)
    good = sign_checkout(order, "pay_race_2")
    signatures = iter([good, "0" * 64, "0" * 64, "0" * 64])
    lock = threading.Lock()

    def work():
        with lock:
            signature = next(signatures)
        try:
            services.verify_payment(
                user=student, order_id=order, payment_id="pay_race_2", signature=signature
            )
        except services.PaymentError:
            pass  # forged attempts are refused -- that part is expected

    assert _race(4, work) == []
    payment = Payment.objects.get(provider_order_id=order)
    sub = Subscription.objects.get(user=student)
    # A valid signature was presented, so whatever the interleaving the payment
    # must end CAPTURED and linked -- a forged attempt must never overwrite it.
    assert payment.status == PaymentStatus.CAPTURED, payment.failure_reason
    assert payment.subscription_id == sub.pk
    assert sub.status == SubscriptionStatus.ACTIVE
    assert sub.end_date - sub.start_date == timedelta(days=plan.duration_days)


@pytest.mark.parametrize("round_", range(10))
def test_full_refund_racing_its_capture_never_leaves_access(student, plan, monkeypatch, round_):
    """LS-01: refund (early, unlinked path) and capture webhooks processed at once."""
    order, pay = f"order_race_3_{round_}", f"pay_race_3_{round_}"
    make_payment(student, plan, order_id=order)
    monkeypatch.setattr(services.gateway, "fetch_payment",
                        lambda pid: {"id": pid, "order_id": order})
    capture = {"payload": {"payment": {"entity": {
        "id": pay, "order_id": order, "amount": plan.price_paise, "status": "captured"}}}}
    refund = {"payload": {"refund": {"entity": {
        "id": f"rfnd_{round_}", "payment_id": pay, "amount": plan.price_paise}}}}
    jobs = iter([lambda: services.handle_payment_captured(capture),
                 lambda: services.handle_payment_refunded(refund)])
    lock = threading.Lock()

    def work():
        with lock:
            job = next(jobs)
        job()

    assert _race(2, work) == []
    payment = Payment.objects.get(provider_order_id=order)
    assert payment.status == PaymentStatus.REFUNDED
    assert payment.provider_payment_id == pay
    assert not Subscription.objects.filter(
        user=student, status=SubscriptionStatus.ACTIVE
    ).exists()
