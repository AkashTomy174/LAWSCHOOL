"""Payment serializers."""

from __future__ import annotations

from rest_framework import serializers

from apps.payments.models import Payment, WebhookEvent


class CreateOrderSerializer(serializers.Serializer):
    """Body for ``POST /api/v1/payments/orders/``.

    Note there is no ``amount`` field: the price always comes from the plan row in
    the database, so a client cannot choose what to pay.
    """

    plan_slug = serializers.SlugField()
    idempotency_key = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
        default="",
        help_text="Optional client-generated key; retrying with the same key returns the same order.",
    )


class PaymentSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source="plan.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Payment
        fields = (
            "id",
            "plan_name",
            "provider",
            "provider_order_id",
            "provider_payment_id",
            "amount",
            "currency",
            "status",
            "status_display",
            "failure_reason",
            "created_at",
            "captured_at",
        )
        read_only_fields = fields


class PaymentAdminSerializer(PaymentSerializer):
    """Admin view -- adds the payer and the raw provider payload reference."""

    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_name = serializers.CharField(source="user.name", read_only=True)

    class Meta(PaymentSerializer.Meta):
        fields = PaymentSerializer.Meta.fields + ("user_email", "user_name", "refunded")
        read_only_fields = fields

    refunded = serializers.SerializerMethodField()

    def get_refunded(self, obj: Payment) -> bool:
        return obj.status == "refunded"


class CheckoutSerializer(serializers.Serializer):
    """What the SPA needs to open Razorpay Checkout (public key only)."""

    payment_id = serializers.UUIDField()
    order_id = serializers.CharField()
    key_id = serializers.CharField()
    amount = serializers.IntegerField(help_text="Amount in paise.")
    currency = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField()
    prefill = serializers.DictField()


class VerifyPaymentSerializer(serializers.Serializer):
    """Body for ``POST /api/v1/payments/verify/`` -- the Razorpay checkout callback."""

    razorpay_order_id = serializers.CharField(max_length=100)
    razorpay_payment_id = serializers.CharField(max_length=100)
    razorpay_signature = serializers.CharField(max_length=255)

    def validate(self, attrs: dict) -> dict:
        if not all(attrs.values()):
            raise serializers.ValidationError("All three Razorpay fields are required.")
        return attrs


class WebhookEventSerializer(serializers.ModelSerializer):
    """Admin audit view of received webhooks."""

    class Meta:
        model = WebhookEvent
        fields = (
            "id",
            "provider",
            "event_id",
            "event_type",
            "signature_valid",
            "processed",
            "processing_error",
            "received_at",
            "processed_at",
        )
        read_only_fields = fields
