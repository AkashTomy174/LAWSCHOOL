"""Regression tests for the payment/subscription audit findings (P1, A2)."""

from __future__ import annotations

import json

import pytest

from apps.core.constants import PaymentStatus, SubscriptionStatus
from apps.core.exceptions import PaymentError
from apps.payments import services
from apps.payments.models import Payment
from apps.payments.tests.test_payments import (
    VERIFY_URL,
    WEBHOOK_URL,
    make_payment,
    sign_checkout,
    sign_webhook,
    webhook_payload,
)
from apps.subscriptions.models import Subscription
from apps.subscriptions.services import can_user_access_course

pytestmark = pytest.mark.django_db


def _verify_body(order, pay):
    return {
        "razorpay_order_id": order,
        "razorpay_payment_id": pay,
        "razorpay_signature": sign_checkout(order, pay),
    }


def _bad_body(order):
    return {
        "razorpay_order_id": order,
        "razorpay_payment_id": "p",
        "razorpay_signature": "bad",
    }


def _active(user):
    return Subscription.objects.filter(user=user, status=SubscriptionStatus.ACTIVE)


def _post_webhook(api_client, payload, event_id="evt_1"):
    body = json.dumps(payload).encode()
    return api_client.post(
        WEBHOOK_URL,
        data=body,
        content_type="application/json",
        HTTP_X_RAZORPAY_SIGNATURE=sign_webhook(body),
        HTTP_X_RAZORPAY_EVENT_ID=event_id,
    )


def _status(order):
    return Payment.objects.get(provider_order_id=order).status


class TestRefundedPaymentIsTerminal:
    def test_verify_cannot_recapture_refunded_payment(self, jwt_client, student, plan):
        make_payment(
            student, plan, status=PaymentStatus.REFUNDED,
            order_id="order_r1", provider_payment_id="pay_r1",
        )
        response = jwt_client(student).post(
            VERIFY_URL, _verify_body("order_r1", "pay_r1"), format="json"
        )
        assert response.status_code == 400
        assert response.data["error"]["code"] == "payment_refunded"
        assert _status("order_r1") == PaymentStatus.REFUNDED
        assert not _active(student).exists()

    def test_repeated_verify_never_reactivates(self, jwt_client, student, plan):
        make_payment(
            student, plan, status=PaymentStatus.REFUNDED,
            order_id="order_r2", provider_payment_id="pay_r2",
        )
        for _ in range(3):
            jwt_client(student).post(
                VERIFY_URL, _verify_body("order_r2", "pay_r2"), format="json"
            )
        assert not Subscription.objects.filter(user=student).exists()

    def test_bad_signature_does_not_overwrite_refunded(self, jwt_client, student, plan):
        make_payment(student, plan, status=PaymentStatus.REFUNDED, order_id="order_r3")
        jwt_client(student).post(VERIFY_URL, _bad_body("order_r3"), format="json")
        assert _status("order_r3") == PaymentStatus.REFUNDED

    def test_capture_webhook_cannot_reactivate_refunded(self, api_client, student, plan):
        make_payment(
            student, plan, status=PaymentStatus.REFUNDED,
            order_id="order_r4", provider_payment_id="pay_r4",
        )
        payload = webhook_payload(
            order_id="order_r4", payment_id="pay_r4", amount_paise=plan.price_paise
        )
        assert _post_webhook(api_client, payload).status_code == 200
        assert _status("order_r4") == PaymentStatus.REFUNDED
        assert not _active(student).exists()

    def test_late_failed_event_does_not_overwrite_refunded(self, api_client, student, plan):
        make_payment(
            student, plan, status=PaymentStatus.REFUNDED,
            order_id="order_r5", provider_payment_id="pay_r5",
        )
        payload = webhook_payload(
            order_id="order_r5", payment_id="pay_r5",
            amount_paise=plan.price_paise, event="payment.failed",
        )
        _post_webhook(api_client, payload, event_id="evt_failed")
        assert _status("order_r5") == PaymentStatus.REFUNDED

    def test_settle_rechecks_status_under_lock(self, student, plan):
        """A refund committed after the caller read the row must still win."""
        stale = make_payment(student, plan, order_id="order_r6")
        Payment.objects.filter(pk=stale.pk).update(status=PaymentStatus.REFUNDED)
        with pytest.raises(PaymentError):
            services._settle_payment(payment=stale, payment_id="pay_r6")
        assert not _active(student).exists()


class TestNormalSettlementStillWorks:
    def test_verify_activates_and_is_idempotent(self, jwt_client, student, plan):
        make_payment(student, plan, order_id="order_ok")
        for _ in range(2):
            r = jwt_client(student).post(
                VERIFY_URL, _verify_body("order_ok", "pay_ok"), format="json"
            )
            assert r.status_code == 200
        assert _active(student).count() == 1

    def test_duplicate_capture_events_are_safe(self, api_client, student, plan):
        make_payment(student, plan, order_id="order_dup")
        payload = webhook_payload(
            order_id="order_dup", payment_id="pay_dup", amount_paise=plan.price_paise
        )
        _post_webhook(api_client, payload, event_id="e1")
        _post_webhook(api_client, payload, event_id="e2")  # replayed body, new id
        assert Subscription.objects.filter(user=student).count() == 1
        assert _active(student).count() == 1

    def test_failed_payment_can_still_be_settled_on_retry(self, jwt_client, student, plan):
        make_payment(student, plan, status=PaymentStatus.FAILED, order_id="order_retry")
        r = jwt_client(student).post(
            VERIFY_URL, _verify_body("order_retry", "pay_retry"), format="json"
        )
        assert r.status_code == 200 and _active(student).count() == 1


class TestFailedVerificationCreatesNoSubscriptions:
    def test_repeated_bad_signatures_create_no_rows(self, jwt_client, student, plan):
        make_payment(student, plan, order_id="order_bad")
        for _ in range(4):
            jwt_client(student).post(VERIFY_URL, _bad_body("order_bad"), format="json")
        assert Subscription.objects.filter(user=student).count() == 0
        payment = Payment.objects.get(provider_order_id="order_bad")
        assert payment.status == PaymentStatus.FAILED and payment.failure_reason

    def test_other_user_cannot_create_rows_for_victim(
        self, jwt_client, student, instructor, plan
    ):
        make_payment(student, plan, order_id="order_vic")
        jwt_client(instructor).post(VERIFY_URL, _bad_body("order_vic"), format="json")
        assert Subscription.objects.count() == 0

    def test_never_subscribed_user_gets_subscription_required(
        self, jwt_client, student, plan, course
    ):
        make_payment(student, plan, order_id="order_n")
        jwt_client(student).post(VERIFY_URL, _bad_body("order_n"), format="json")
        course.unlock_rule = "subscription"
        course.save()
        assert can_user_access_course(student, course).reason == "subscription_required"

    def test_failed_webhook_marks_payment_not_subscription(self, api_client, student, plan):
        make_payment(student, plan, order_id="order_wf")
        payload = webhook_payload(
            order_id="order_wf", payment_id="pay_wf",
            amount_paise=plan.price_paise, event="payment.failed",
        )
        _post_webhook(api_client, payload, event_id="evt_wf")
        assert _status("order_wf") == PaymentStatus.FAILED
        assert Subscription.objects.filter(user=student).count() == 0

    def test_active_subscription_not_downgraded_by_failed_renewal(self, student, plan):
        from apps.subscriptions.services_lifecycle import (
            activate_subscription,
            mark_subscription_failed,
        )

        sub = activate_subscription(user=student, plan=plan)
        mark_subscription_failed(subscription=sub, user=student, plan=plan)
        sub.refresh_from_db()
        assert sub.status == SubscriptionStatus.ACTIVE


# --------------------------------------------------------------------------- #
# A failure must never overwrite a capture that landed after it was read.
# (Deterministic replay of the race the PostgreSQL concurrency tests provoke.)
# --------------------------------------------------------------------------- #
def _capture_now(payment):
    from apps.payments import services

    services._settle_payment(payment=payment, payment_id="pay_genuine")


def test_forged_verify_cannot_overwrite_a_capture_that_raced_it(student, plan):
    from unittest import mock

    from apps.core.constants import PaymentStatus
    from apps.payments import gateway, services
    from apps.payments.tests.test_payments import make_payment

    payment = make_payment(student, plan, order_id="order_interleave_1")

    def capture_then_reject(**_kwargs):
        _capture_now(payment)  # the genuine verification commits first...
        return False  # ...then this forged attempt's signature check fails

    with mock.patch.object(gateway, "verify_checkout_signature", side_effect=capture_then_reject):
        with pytest.raises(services.PaymentError):
            services.verify_payment(
                user=student, order_id="order_interleave_1", payment_id="pay_x", signature="0" * 64
            )

    payment.refresh_from_db()
    assert payment.status == PaymentStatus.CAPTURED
    assert payment.provider_payment_id == "pay_genuine"
    # And the capture webhook that follows does not grant a second term.
    end = payment.subscription.end_date
    services._settle_payment(payment=payment, payment_id="pay_genuine")
    payment.subscription.refresh_from_db()
    assert payment.subscription.end_date == end


def test_late_failure_webhook_cannot_overwrite_a_racing_capture(student, plan):
    from unittest import mock

    from apps.core.constants import PaymentStatus
    from apps.payments import services
    from apps.payments.models import Payment
    from apps.payments.tests.test_payments import make_payment

    payment = make_payment(student, plan, order_id="order_interleave_2")
    stale = Payment.objects.get(pk=payment.pk)  # read before the capture commits
    _capture_now(payment)

    with mock.patch.object(services, "_find_payment", return_value=stale):
        result = services.handle_payment_failed(
            {"payload": {"payment": {"entity": {"id": "pay_late", "order_id": "order_interleave_2"}}}}
        )

    payment.refresh_from_db()
    assert result["ignored"] == "already captured"
    assert payment.status == PaymentStatus.CAPTURED
    assert payment.provider_payment_id == "pay_genuine"
