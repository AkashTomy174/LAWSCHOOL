"""Payment tests: order creation, signature verification, webhooks, idempotency.

Nothing here talks to Razorpay.  The gateway module is the only seam, and it is
patched so the tests assert on *our* logic -- signature maths, transaction
handling and idempotency -- rather than on a third party's behaviour.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from decimal import Decimal

import pytest
from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from apps.core.constants import PaymentStatus, SubscriptionStatus
from apps.payments import gateway
from apps.payments.models import Payment, WebhookEvent
from apps.subscriptions.models import Subscription

pytestmark = pytest.mark.django_db

CREATE_ORDER_URL = "/api/v1/payments/orders/"
VERIFY_URL = "/api/v1/payments/verify/"
WEBHOOK_URL = "/api/v1/payments/webhook/"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def sign_checkout(order_id: str, payment_id: str, secret: str | None = None) -> str:
    """Reproduce Razorpay's checkout signature."""
    secret = secret or settings.RAZORPAY_KEY_SECRET
    return hmac.new(
        secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256
    ).hexdigest()


def sign_webhook(body: bytes, secret: str | None = None) -> str:
    secret = secret or settings.RAZORPAY_WEBHOOK_SECRET
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def make_payment(
    student, plan, *, status=PaymentStatus.CREATED, order_id="order_test_1", **kwargs
):
    return Payment.objects.create(
        user=student,
        plan=plan,
        provider_order_id=order_id,
        provider_payment_id=kwargs.pop("provider_payment_id", ""),
        amount=plan.price,
        currency=plan.currency,
        status=status,
        **kwargs,
    )


def webhook_payload(*, order_id, payment_id, amount_paise, event="payment.captured"):
    return {
        "event": event,
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "order_id": order_id,
                    "amount": amount_paise,
                    "currency": "INR",
                    "status": "captured",
                }
            }
        },
    }


@pytest.fixture
def fake_razorpay_order(monkeypatch):
    """Patch order creation so no network call happens."""
    calls = []

    def _create_order(*, amount_paise, currency, receipt, notes=None):
        calls.append(
            {"amount_paise": amount_paise, "currency": currency, "receipt": receipt}
        )
        return {
            "id": f"order_{uuid.uuid4().hex[:14]}",
            "amount": amount_paise,
            "currency": currency,
            "status": "created",
        }

    monkeypatch.setattr(gateway, "create_order", _create_order)
    return calls


# --------------------------------------------------------------------------- #
# Order creation
# --------------------------------------------------------------------------- #
class TestOrderCreation:
    def test_creates_order_from_server_side_price(
        self, jwt_client, student, plan, fake_razorpay_order
    ):
        response = jwt_client(student).post(
            CREATE_ORDER_URL, {"plan_slug": plan.slug}, format="json"
        )
        assert response.status_code == 201, response.data
        assert response.data["checkout"]["amount"] == plan.price_paise
        # The amount charged came from the plan row, not from the request.
        assert fake_razorpay_order[0]["amount_paise"] == plan.price_paise

    def test_client_supplied_amount_is_ignored(
        self, jwt_client, student, plan, fake_razorpay_order
    ):
        """A tampered amount must not reduce what is charged."""
        response = jwt_client(student).post(
            CREATE_ORDER_URL,
            {"plan_slug": plan.slug, "amount": 1, "amount_paise": 1},
            format="json",
        )
        assert response.status_code == 201
        assert fake_razorpay_order[0]["amount_paise"] == plan.price_paise
        assert (
            Payment.objects.get(
                provider_order_id=response.data["checkout"]["order_id"]
            ).amount
            == plan.price
        )

    def test_checkout_payload_never_exposes_the_key_secret(
        self, jwt_client, student, plan, fake_razorpay_order
    ):
        response = jwt_client(student).post(
            CREATE_ORDER_URL, {"plan_slug": plan.slug}, format="json"
        )
        body = json.dumps(response.data)
        assert settings.RAZORPAY_KEY_SECRET not in body
        assert settings.RAZORPAY_WEBHOOK_SECRET not in body
        # Only the public key id may be exposed.
        assert response.data["checkout"]["key_id"] == settings.RAZORPAY_KEY_ID

    def test_idempotency_key_reuses_existing_order(
        self, jwt_client, student, plan, fake_razorpay_order
    ):
        first = jwt_client(student).post(
            CREATE_ORDER_URL,
            {"plan_slug": plan.slug, "idempotency_key": "abc-123"},
            format="json",
        )
        second = jwt_client(student).post(
            CREATE_ORDER_URL,
            {"plan_slug": plan.slug, "idempotency_key": "abc-123"},
            format="json",
        )
        assert first.data["checkout"]["order_id"] == second.data["checkout"]["order_id"]
        assert len(fake_razorpay_order) == 1  # only one gateway call
        assert Payment.objects.count() == 1

    def test_different_idempotency_keys_create_different_orders(
        self, jwt_client, student, plan, fake_razorpay_order
    ):
        first = jwt_client(student).post(
            CREATE_ORDER_URL,
            {"plan_slug": plan.slug, "idempotency_key": "k1"},
            format="json",
        )
        second = jwt_client(student).post(
            CREATE_ORDER_URL,
            {"plan_slug": plan.slug, "idempotency_key": "k2"},
            format="json",
        )
        assert first.data["checkout"]["order_id"] != second.data["checkout"]["order_id"]

    def test_inactive_plan_cannot_be_ordered(
        self, jwt_client, student, plan, fake_razorpay_order
    ):
        plan.is_active = False
        plan.save(update_fields=["is_active"])
        response = jwt_client(student).post(
            CREATE_ORDER_URL, {"plan_slug": plan.slug}, format="json"
        )
        assert response.status_code == 404

    def test_order_requires_authentication(self, api_client, plan):
        assert (
            api_client.post(
                CREATE_ORDER_URL, {"plan_slug": plan.slug}, format="json"
            ).status_code
            == 401
        )


# --------------------------------------------------------------------------- #
# Signature verification
# --------------------------------------------------------------------------- #
class TestCheckoutVerification:
    def test_valid_signature_activates_subscription(self, jwt_client, student, plan):
        payment = make_payment(student, plan)
        signature = sign_checkout(payment.provider_order_id, "pay_valid_1")

        response = jwt_client(student).post(
            VERIFY_URL,
            {
                "razorpay_order_id": payment.provider_order_id,
                "razorpay_payment_id": "pay_valid_1",
                "razorpay_signature": signature,
            },
            format="json",
        )
        assert response.status_code == 200, response.data
        payment.refresh_from_db()
        assert payment.status == PaymentStatus.CAPTURED
        assert payment.provider_payment_id == "pay_valid_1"

        subscription = Subscription.objects.get(user=student)
        assert subscription.status == SubscriptionStatus.ACTIVE
        assert subscription.end_date > timezone.now()

    def test_invalid_signature_is_rejected_and_never_activates(
        self, jwt_client, student, plan
    ):
        payment = make_payment(student, plan)

        response = jwt_client(student).post(
            VERIFY_URL,
            {
                "razorpay_order_id": payment.provider_order_id,
                "razorpay_payment_id": "pay_forged",
                "razorpay_signature": "0" * 64,
            },
            format="json",
        )
        assert response.status_code == 400
        assert response.data["error"]["code"] == "invalid_signature"

        payment.refresh_from_db()
        assert payment.status == PaymentStatus.FAILED
        assert payment.failure_reason
        # No subscription may exist in an active state.
        assert not Subscription.objects.filter(
            user=student, status=SubscriptionStatus.ACTIVE
        ).exists()

    def test_signature_from_wrong_secret_is_rejected(self, jwt_client, student, plan):
        payment = make_payment(student, plan)
        forged = sign_checkout(
            payment.provider_order_id, "pay_x", secret="attacker-secret"
        )

        response = jwt_client(student).post(
            VERIFY_URL,
            {
                "razorpay_order_id": payment.provider_order_id,
                "razorpay_payment_id": "pay_x",
                "razorpay_signature": forged,
            },
            format="json",
        )
        assert response.status_code == 400

    def test_signature_for_a_different_order_is_rejected(
        self, jwt_client, student, plan
    ):
        payment = make_payment(student, plan)
        # Correct secret, wrong order/payment pair.
        signature = sign_checkout("order_someone_else", "pay_someone_else")

        response = jwt_client(student).post(
            VERIFY_URL,
            {
                "razorpay_order_id": payment.provider_order_id,
                "razorpay_payment_id": "pay_someone_else",
                "razorpay_signature": signature,
            },
            format="json",
        )
        assert response.status_code == 400

    def test_user_cannot_verify_another_users_order(
        self, jwt_client, student, other_student, plan
    ):
        """Critical: a student must not activate a subscription on someone else's payment."""
        payment = make_payment(student, plan)
        signature = sign_checkout(payment.provider_order_id, "pay_theirs")

        response = jwt_client(other_student).post(
            VERIFY_URL,
            {
                "razorpay_order_id": payment.provider_order_id,
                "razorpay_payment_id": "pay_theirs",
                "razorpay_signature": signature,
            },
            format="json",
        )
        assert response.status_code == 400
        assert response.data["error"]["code"] == "forbidden"
        payment.refresh_from_db()
        assert payment.status == PaymentStatus.CREATED  # untouched
        assert not Subscription.objects.filter(user=other_student).exists()

    def test_unknown_order_is_rejected(self, jwt_client, student):
        response = jwt_client(student).post(
            VERIFY_URL,
            {
                "razorpay_order_id": "order_does_not_exist",
                "razorpay_payment_id": "pay_x",
                "razorpay_signature": sign_checkout("order_does_not_exist", "pay_x"),
            },
            format="json",
        )
        assert response.status_code == 400
        assert response.data["error"]["code"] == "unknown_order"

    def test_duplicate_verification_does_not_double_extend(
        self, jwt_client, student, plan
    ):
        """Repeating a successful callback must not stack subscription periods."""
        payment = make_payment(student, plan)
        signature = sign_checkout(payment.provider_order_id, "pay_once")
        payload = {
            "razorpay_order_id": payment.provider_order_id,
            "razorpay_payment_id": "pay_once",
            "razorpay_signature": signature,
        }

        assert (
            jwt_client(student).post(VERIFY_URL, payload, format="json").status_code
            == 200
        )
        first_end = Subscription.objects.get(user=student).end_date

        assert (
            jwt_client(student).post(VERIFY_URL, payload, format="json").status_code
            == 200
        )
        assert Subscription.objects.get(user=student).end_date == first_end
        assert Subscription.objects.filter(user=student).count() == 1

    def test_missing_fields_are_rejected(self, jwt_client, student):
        assert (
            jwt_client(student).post(VERIFY_URL, {}, format="json").status_code == 400
        )


# --------------------------------------------------------------------------- #
# Webhooks
# --------------------------------------------------------------------------- #
class TestWebhookSignature:
    def test_valid_webhook_activates_subscription(self, api_client, student, plan):
        payment = make_payment(student, plan, order_id="order_hook_1")
        payload = webhook_payload(
            order_id="order_hook_1",
            payment_id="pay_hook_1",
            amount_paise=plan.price_paise,
        )
        body = json.dumps(payload).encode()

        response = api_client.post(
            WEBHOOK_URL,
            data=body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=sign_webhook(body),
            HTTP_X_RAZORPAY_EVENT_ID="evt_hook_1",
        )
        assert response.status_code == 200, response.data
        assert response.data["status"] == "processed"

        payment.refresh_from_db()
        assert payment.status == PaymentStatus.CAPTURED
        assert Subscription.objects.filter(
            user=student, status=SubscriptionStatus.ACTIVE
        ).exists()

    def test_invalid_webhook_signature_is_rejected(self, api_client, student, plan):
        payment = make_payment(student, plan, order_id="order_hook_bad")
        payload = webhook_payload(
            order_id="order_hook_bad",
            payment_id="pay_bad",
            amount_paise=plan.price_paise,
        )
        body = json.dumps(payload).encode()

        response = api_client.post(
            WEBHOOK_URL,
            data=body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE="deadbeef",
            HTTP_X_RAZORPAY_EVENT_ID="evt_bad_sig",
        )
        assert response.status_code == 400
        assert response.data["error"]["code"] == "invalid_signature"

        payment.refresh_from_db()
        assert payment.status == PaymentStatus.CREATED
        assert not Subscription.objects.filter(user=student).exists()

    def test_webhook_from_wrong_secret_is_rejected(self, api_client, student, plan):
        make_payment(student, plan, order_id="order_hook_wrong_secret")
        payload = webhook_payload(
            order_id="order_hook_wrong_secret",
            payment_id="pay_w",
            amount_paise=plan.price_paise,
        )
        body = json.dumps(payload).encode()

        response = api_client.post(
            WEBHOOK_URL,
            data=body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=sign_webhook(body, secret="wrong-secret"),
            HTTP_X_RAZORPAY_EVENT_ID="evt_wrong_secret",
        )
        assert response.status_code == 400

    def test_signature_over_modified_body_is_rejected(self, api_client, student, plan):
        """The HMAC covers the raw bytes; altering them must invalidate it."""
        make_payment(student, plan, order_id="order_tamper")
        payload = webhook_payload(
            order_id="order_tamper", payment_id="pay_t", amount_paise=plan.price_paise
        )
        body = json.dumps(payload).encode()
        signature = sign_webhook(body)

        tampered = json.dumps(
            webhook_payload(order_id="order_tamper", payment_id="pay_t", amount_paise=1)
        ).encode()
        response = api_client.post(
            WEBHOOK_URL,
            data=tampered,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=signature,
            HTTP_X_RAZORPAY_EVENT_ID="evt_tampered",
        )
        assert response.status_code == 400


class TestWebhookIdempotency:
    def test_duplicate_webhook_is_ignored(self, api_client, student, plan):
        make_payment(student, plan, order_id="order_dup")
        payload = webhook_payload(
            order_id="order_dup", payment_id="pay_dup", amount_paise=plan.price_paise
        )
        body = json.dumps(payload).encode()
        headers = {
            "HTTP_X_RAZORPAY_SIGNATURE": sign_webhook(body),
            "HTTP_X_RAZORPAY_EVENT_ID": "evt_duplicate_1",
        }

        first = api_client.post(
            WEBHOOK_URL, data=body, content_type="application/json", **headers
        )
        assert first.status_code == 200
        assert first.data["status"] == "processed"

        second = api_client.post(
            WEBHOOK_URL, data=body, content_type="application/json", **headers
        )
        assert second.status_code == 200
        assert second.data["status"] == "duplicate"

        # Exactly one event row and exactly one subscription extension.
        assert WebhookEvent.objects.filter(event_id="evt_duplicate_1").count() == 1
        assert Subscription.objects.filter(user=student).count() == 1

    def test_duplicate_webhook_does_not_extend_subscription_twice(
        self, api_client, student, plan
    ):
        make_payment(student, plan, order_id="order_dup2")
        payload = webhook_payload(
            order_id="order_dup2", payment_id="pay_dup2", amount_paise=plan.price_paise
        )
        body = json.dumps(payload).encode()
        headers = {
            "HTTP_X_RAZORPAY_SIGNATURE": sign_webhook(body),
            "HTTP_X_RAZORPAY_EVENT_ID": "evt_dup_same_end",
        }

        api_client.post(
            WEBHOOK_URL, data=body, content_type="application/json", **headers
        )
        end_after_first = Subscription.objects.get(user=student).end_date
        api_client.post(
            WEBHOOK_URL, data=body, content_type="application/json", **headers
        )

        assert Subscription.objects.get(user=student).end_date == end_after_first

    def test_webhook_and_checkout_callback_do_not_double_activate(
        self, api_client, jwt_client, student, plan
    ):
        """The two settlement paths must be mutually idempotent."""
        payment = make_payment(student, plan, order_id="order_both")

        # 1) checkout callback wins
        signature = sign_checkout(payment.provider_order_id, "pay_both")
        jwt_client(student).post(
            VERIFY_URL,
            {
                "razorpay_order_id": payment.provider_order_id,
                "razorpay_payment_id": "pay_both",
                "razorpay_signature": signature,
            },
            format="json",
        )
        end_after_callback = Subscription.objects.get(user=student).end_date

        # 2) the same payment now arrives as a webhook
        payload = webhook_payload(
            order_id="order_both", payment_id="pay_both", amount_paise=plan.price_paise
        )
        body = json.dumps(payload).encode()
        api_client.post(
            WEBHOOK_URL,
            data=body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=sign_webhook(body),
            HTTP_X_RAZORPAY_EVENT_ID="evt_after_callback",
        )

        assert Subscription.objects.get(user=student).end_date == end_after_callback
        assert Subscription.objects.filter(user=student).count() == 1

    def test_webhook_without_event_id_is_still_deduplicated(
        self, api_client, student, plan
    ):
        """Razorpay always sends the header; if it is missing we hash the body."""
        make_payment(student, plan, order_id="order_nohdr")
        payload = webhook_payload(
            order_id="order_nohdr",
            payment_id="pay_nohdr",
            amount_paise=plan.price_paise,
        )
        body = json.dumps(payload).encode()
        headers = {"HTTP_X_RAZORPAY_SIGNATURE": sign_webhook(body)}

        first = api_client.post(
            WEBHOOK_URL, data=body, content_type="application/json", **headers
        )
        second = api_client.post(
            WEBHOOK_URL, data=body, content_type="application/json", **headers
        )

        assert first.status_code == 200
        assert second.data["status"] == "duplicate"
        assert Subscription.objects.filter(user=student).count() == 1


class TestFailedAndRefundedPayments:
    def test_payment_failed_webhook_records_failure(self, api_client, student, plan):
        payment = make_payment(student, plan, order_id="order_fail")
        payload = {
            "event": "payment.failed",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_failed_1",
                        "order_id": "order_fail",
                        "amount": plan.price_paise,
                        "error_description": "Payment declined by bank",
                    }
                }
            },
        }
        body = json.dumps(payload).encode()

        response = api_client.post(
            WEBHOOK_URL,
            data=body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=sign_webhook(body),
            HTTP_X_RAZORPAY_EVENT_ID="evt_fail_1",
        )
        assert response.status_code == 200
        payment.refresh_from_db()
        assert payment.status == PaymentStatus.FAILED
        assert "declined" in payment.failure_reason

    def test_failed_payment_creates_no_active_subscription(
        self, api_client, student, plan
    ):
        make_payment(student, plan, order_id="order_fail2")
        payload = {
            "event": "payment.failed",
            "payload": {
                "payment": {"entity": {"id": "pay_f2", "order_id": "order_fail2"}}
            },
        }
        body = json.dumps(payload).encode()
        api_client.post(
            WEBHOOK_URL,
            data=body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=sign_webhook(body),
            HTTP_X_RAZORPAY_EVENT_ID="evt_fail_2",
        )
        assert not Subscription.objects.filter(
            user=student, status=SubscriptionStatus.ACTIVE
        ).exists()

    def test_refund_ends_access_immediately(
        self, api_client, student, plan, active_subscription
    ):
        """A refund must revoke entitlement, not merely change a payment row."""
        from apps.subscriptions.services import can_user_access_course

        payment = Payment.objects.create(
            user=student,
            plan=plan,
            provider_order_id="order_refund",
            provider_payment_id="pay_refund_1",
            amount=plan.price,
            status=PaymentStatus.CAPTURED,
            subscription=active_subscription,
        )
        assert can_user_access_course(student, plan.courses.first()).allowed is True

        payload = {
            "event": "refund.processed",
            "payload": {
                "refund": {"entity": {"id": "rfnd_1", "payment_id": "pay_refund_1"}}
            },
        }
        body = json.dumps(payload).encode()
        response = api_client.post(
            WEBHOOK_URL,
            data=body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=sign_webhook(body),
            HTTP_X_RAZORPAY_EVENT_ID="evt_refund_1",
        )
        assert response.status_code == 200

        payment.refresh_from_db()
        active_subscription.refresh_from_db()
        assert payment.status == PaymentStatus.REFUNDED
        assert active_subscription.status == SubscriptionStatus.CANCELLED
        assert can_user_access_course(student, plan.courses.first()).allowed is False

    def test_amount_mismatch_does_not_activate(self, api_client, student, plan):
        """A INR 1 capture must not unlock a INR 1999 plan."""
        payment = make_payment(student, plan, order_id="order_mismatch")
        payload = webhook_payload(
            order_id="order_mismatch", payment_id="pay_cheap", amount_paise=100
        )
        body = json.dumps(payload).encode()

        response = api_client.post(
            WEBHOOK_URL,
            data=body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=sign_webhook(body),
            HTTP_X_RAZORPAY_EVENT_ID="evt_mismatch",
        )
        assert response.status_code == 200
        assert response.data["result"]["amount_mismatch"] is True

        payment.refresh_from_db()
        assert payment.status == PaymentStatus.FAILED
        assert not Subscription.objects.filter(
            user=student, status=SubscriptionStatus.ACTIVE
        ).exists()

    def test_late_failure_does_not_undo_a_capture(self, api_client, student, plan):
        """Out-of-order webhooks must not revoke an entitled student."""
        payment = make_payment(
            student,
            plan,
            order_id="order_late",
            status=PaymentStatus.CAPTURED,
            provider_payment_id="pay_late",
        )
        payload = {
            "event": "payment.failed",
            "payload": {
                "payment": {"entity": {"id": "pay_late", "order_id": "order_late"}}
            },
        }
        body = json.dumps(payload).encode()
        api_client.post(
            WEBHOOK_URL,
            data=body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=sign_webhook(body),
            HTTP_X_RAZORPAY_EVENT_ID="evt_late_fail",
        )
        payment.refresh_from_db()
        assert payment.status == PaymentStatus.CAPTURED

    def test_unknown_event_type_is_acknowledged(self, api_client):
        """Razorpay should stop retrying events we do not handle."""
        payload = {"event": "some.unknown.event", "payload": {}}
        body = json.dumps(payload).encode()
        response = api_client.post(
            WEBHOOK_URL,
            data=body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=sign_webhook(body),
            HTTP_X_RAZORPAY_EVENT_ID="evt_unknown_1",
        )
        assert response.status_code == 200
        assert response.data["status"] == "ignored"

    def test_webhook_for_unknown_order_is_recorded_not_crashed(self, api_client):
        payload = webhook_payload(
            order_id="order_ghost", payment_id="pay_ghost", amount_paise=1000
        )
        body = json.dumps(payload).encode()
        response = api_client.post(
            WEBHOOK_URL,
            data=body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=sign_webhook(body),
            HTTP_X_RAZORPAY_EVENT_ID="evt_ghost",
        )
        assert response.status_code == 200
        assert WebhookEvent.objects.filter(event_id="evt_ghost").exists()


class TestGatewaySignatureUnit:
    """Pure-function tests for the signature maths, including edge cases."""

    def test_checkout_signature_matches_reference_implementation(self):
        order_id, payment_id = "order_ABC123", "pay_XYZ789"
        expected = hmac.new(
            settings.RAZORPAY_KEY_SECRET.encode(),
            f"{order_id}|{payment_id}".encode(),
            hashlib.sha256,
        ).hexdigest()
        assert gateway.verify_checkout_signature(
            order_id=order_id, payment_id=payment_id, signature=expected
        )

    @pytest.mark.parametrize(
        "order_id,payment_id,signature",
        [
            ("", "pay_x", "abc"),
            ("order_x", "", "abc"),
            ("order_x", "pay_x", ""),
            ("order_x", "pay_x", "not-a-hex-signature"),
        ],
    )
    def test_missing_or_malformed_values_fail_closed(
        self, order_id, payment_id, signature
    ):
        assert (
            gateway.verify_checkout_signature(
                order_id=order_id, payment_id=payment_id, signature=signature
            )
            is False
        )

    def test_webhook_signature_uses_raw_bytes(self):
        body = b'{"a": 1}'
        assert (
            gateway.verify_webhook_signature(
                raw_body=body, signature=sign_webhook(body)
            )
            is True
        )
        # Whitespace differences change the HMAC -- hence raw-body verification.
        assert (
            gateway.verify_webhook_signature(
                raw_body=b'{"a":1}', signature=sign_webhook(body)
            )
            is False
        )

    def test_webhook_signature_empty_secret_fails_closed(self, settings):
        settings.RAZORPAY_WEBHOOK_SECRET = ""
        assert (
            gateway.verify_webhook_signature(raw_body=b"{}", signature="anything")
            is False
        )


class TestPaymentHistoryEndpoints:
    def test_student_sees_only_their_own_payments(
        self, jwt_client, student, other_student, plan
    ):
        make_payment(student, plan, order_id="order_mine")
        make_payment(other_student, plan, order_id="order_theirs")

        response = jwt_client(student).get("/api/v1/payments/")
        assert response.data["count"] == 1
        assert response.data["results"][0]["provider_order_id"] == "order_mine"

    def test_admin_payment_payload_never_includes_provider_payload(
        self, jwt_client, admin_user, student, plan
    ):
        make_payment(
            student,
            plan,
            order_id="order_admin_view",
            provider_payload={"secret": "nope"},
        )
        response = jwt_client(admin_user).get("/api/v1/payments/all/")
        assert "provider_payload" not in json.dumps(response.data)
        assert "provider_signature" not in json.dumps(response.data)


# --------------------------------------------------------------------------- #
# Audit regressions
# --------------------------------------------------------------------------- #
def _signed_post(api_client, body, event_id, signature=None):
    return api_client.post(
        WEBHOOK_URL,
        data=body,
        content_type="application/json",
        HTTP_X_RAZORPAY_SIGNATURE=signature or sign_webhook(body),
        HTTP_X_RAZORPAY_EVENT_ID=event_id,
    )


class TestWebhookRobustness:
    def test_failed_handler_is_retried_on_redelivery(self, api_client, student, plan):
        from unittest import mock

        payment = make_payment(student, plan, order_id="order_retry")
        body = json.dumps(
            webhook_payload(
                order_id="order_retry", payment_id="pay_retry", amount_paise=plan.price_paise
            )
        ).encode()
        with mock.patch(
            "apps.payments.services._settle_payment", side_effect=RuntimeError("db")
        ):
            first = _signed_post(api_client, body, "evt_retry")
        assert first.status_code == 500

        second = _signed_post(api_client, body, "evt_retry")
        assert second.status_code == 200
        assert second.data["status"] == "processed"
        payment.refresh_from_db()
        assert payment.status == PaymentStatus.CAPTURED

    def test_unsigned_request_cannot_claim_event_id(self, api_client, student, plan):
        payment = make_payment(student, plan, order_id="order_poison")
        body = json.dumps(
            webhook_payload(
                order_id="order_poison", payment_id="pay_poison", amount_paise=plan.price_paise
            )
        ).encode()
        bad = _signed_post(api_client, body, "evt_poison", signature="deadbeef")
        assert bad.status_code == 400
        assert not WebhookEvent.objects.filter(event_id="evt_poison").exists()

        good = _signed_post(api_client, body, "evt_poison")
        assert good.data["status"] == "processed"
        payment.refresh_from_db()
        assert payment.status == PaymentStatus.CAPTURED

    def test_partial_refund_keeps_subscription(self, api_client, student, plan):
        payment = make_payment(student, plan, order_id="order_pref")
        body = json.dumps(
            webhook_payload(
                order_id="order_pref", payment_id="pay_pref", amount_paise=plan.price_paise
            )
        ).encode()
        _signed_post(api_client, body, "evt_pref_cap")

        refund = json.dumps(
            {
                "event": "refund.processed",
                "payload": {
                    "refund": {
                        "entity": {"id": "rfnd_1", "payment_id": "pay_pref", "amount": 100}
                    }
                },
            }
        ).encode()
        _signed_post(api_client, refund, "evt_pref_refund")
        payment.refresh_from_db()
        assert payment.status == PaymentStatus.CAPTURED
        assert payment.provider_refund_id == "rfnd_1"
        assert Subscription.objects.get(user=student).status == SubscriptionStatus.ACTIVE

    def test_full_refund_cancels_subscription(self, api_client, student, plan):
        payment = make_payment(student, plan, order_id="order_fref")
        body = json.dumps(
            webhook_payload(
                order_id="order_fref", payment_id="pay_fref", amount_paise=plan.price_paise
            )
        ).encode()
        _signed_post(api_client, body, "evt_fref_cap")
        refund = json.dumps(
            {
                "event": "refund.processed",
                "payload": {
                    "refund": {
                        "entity": {
                            "id": "rfnd_2",
                            "payment_id": "pay_fref",
                            "amount": plan.price_paise,
                        }
                    }
                },
            }
        ).encode()
        _signed_post(api_client, refund, "evt_fref_refund")
        payment.refresh_from_db()
        assert payment.status == PaymentStatus.REFUNDED
        assert Subscription.objects.get(user=student).status == SubscriptionStatus.CANCELLED


class TestReconciliation:
    def test_missed_webhook_is_recovered_via_order_lookup(self, student, plan):
        from unittest import mock

        from apps.payments import services

        payment = make_payment(student, plan, order_id="order_recon")
        Payment.objects.filter(pk=payment.pk).update(
            created_at=timezone.now() - timezone.timedelta(hours=2)
        )
        entity = {
            "id": "pay_recon",
            "order_id": "order_recon",
            "amount": plan.price_paise,
            "status": "captured",
        }
        with mock.patch.object(gateway, "fetch_order_payments", return_value=[entity]):
            assert services.reconcile_stale_payments() == 1
        payment.refresh_from_db()
        assert payment.status == PaymentStatus.CAPTURED
        assert Subscription.objects.filter(user=student).count() == 1


class TestIdempotencyIsDatabaseEnforced:
    def test_duplicate_key_for_same_user_and_plan_is_rejected_by_the_database(
        self, student, plan
    ):
        from django.db import IntegrityError, transaction

        make_payment(student, plan, order_id="order_idem_1", idempotency_key="k1")
        with pytest.raises(IntegrityError), transaction.atomic():
            make_payment(student, plan, order_id="order_idem_2", idempotency_key="k1")

    def test_blank_keys_are_not_constrained(self, student, plan):
        make_payment(student, plan, order_id="order_blank_1")
        make_payment(student, plan, order_id="order_blank_2")

    def test_losing_a_race_returns_the_existing_order(self, student, plan, monkeypatch):
        from apps.payments import services

        winner = make_payment(
            student, plan, order_id="order_win", idempotency_key="race-key"
        )
        # Simulate the lookup missing the winner (it committed a moment later).
        monkeypatch.setattr(
            gateway,
            "create_order",
            lambda **kw: {"id": "order_lose", "amount": plan.price_paise, "currency": "INR"},
        )
        real_filter = Payment.objects.filter
        calls = {"n": 0}

        def flaky_filter(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                return Payment.objects.none()
            return real_filter(*args, **kwargs)

        monkeypatch.setattr(Payment.objects, "filter", flaky_filter)
        result = services.create_plan_order(
            user=student, plan=plan, idempotency_key="race-key"
        )
        assert result.pk == winner.pk
