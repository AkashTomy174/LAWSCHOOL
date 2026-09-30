"""Payment API views.

Security notes that shape this file:

* ``PaymentWebhookView`` reads ``request.body`` (the **raw** bytes) because the
  HMAC is computed over exactly what Razorpay sent.  Any JSON re-serialisation
  would change the bytes and break verification, which is why this view does
  **not** use a DRF parser for the signature check.
* ``authentication_classes`` is emptied on the webhook: authentication is the
  signature, and Razorpay cannot send a JWT.
* ``VerifyPaymentView`` never accepts an amount or a status from the client --
  only the three Razorpay identifiers that are then verified server-side.
"""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.core.exceptions import PaymentError, code_for, message_for
from apps.core.logging import get_logger
from apps.core.permissions import IsAdminRole, is_schema_generation
from apps.payments import services
from apps.payments.models import Payment, WebhookEvent
from apps.payments.serializers import (
    CheckoutSerializer,
    CreateOrderSerializer,
    PaymentAdminSerializer,
    PaymentSerializer,
    VerifyPaymentSerializer,
    WebhookEventSerializer,
)
from apps.subscriptions.models import Plan

logger = get_logger(__name__)


class CreateOrderView(APIView):
    """POST /api/v1/payments/orders/ -- create a Razorpay order for a plan."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "payment"

    @extend_schema(request=CreateOrderSerializer, responses={201: CheckoutSerializer})
    def post(self, request):
        serializer = CreateOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        plan = get_object_or_404(
            Plan, slug=serializer.validated_data["plan_slug"], is_active=True
        )
        payment = services.create_plan_order(
            user=request.user,
            plan=plan,
            idempotency_key=serializer.validated_data.get("idempotency_key", ""),
        )
        payload = services.checkout_payload(payment)
        return Response(
            {"payment": PaymentSerializer(payment).data, "checkout": payload},
            status=status.HTTP_201_CREATED,
        )


class VerifyPaymentView(APIView):
    """POST /api/v1/payments/verify/ -- verify the checkout signature and activate.

    This is the *client-triggered* path.  It only ever triggers a server-side
    verification; the request body cannot assert success.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "payment"

    @extend_schema(request=VerifyPaymentSerializer, responses={200: PaymentSerializer})
    def post(self, request):
        serializer = VerifyPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        payment = services.verify_payment(
            user=request.user,
            order_id=data["razorpay_order_id"],
            payment_id=data["razorpay_payment_id"],
            signature=data["razorpay_signature"],
        )
        return Response(
            {
                "detail": "Payment verified. Your subscription is active.",
                "payment": PaymentSerializer(payment).data,
            }
        )


@method_decorator(csrf_exempt, name="dispatch")
class PaymentWebhookView(APIView):
    """POST /api/v1/payments/webhook/ -- Razorpay server-to-server notifications.

    Verification is signature-based over the raw body, so this endpoint is
    authentication-free but *not* authorization-free: an unsigned or mis-signed
    request is rejected before any state change.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    parser_classes = [JSONParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "webhook"

    @extend_schema(
        request=None,
        responses={200: None, 400: None},
        description="Raw Razorpay webhook. Verified via the X-Razorpay-Signature HMAC.",
    )
    def post(self, request):
        raw_body = request.body
        signature = request.headers.get("X-Razorpay-Signature", "")
        event_id = request.headers.get("X-Razorpay-Event-Id", "")

        try:
            payload = request.data if isinstance(request.data, dict) else {}
        except Exception:
            payload = {}

        if not event_id:
            # Razorpay always sends this header; without it we cannot deduplicate.
            # Fall back to a hash so the event is still logged exactly once.
            import hashlib

            event_id = f"sha256:{hashlib.sha256(raw_body).hexdigest()[:40]}"

        event_type = payload.get("event") or request.headers.get(
            "X-Razorpay-Event-Type", ""
        )

        try:
            result = services.process_webhook(
                raw_body=raw_body,
                signature=signature,
                event_id=event_id,
                event_type=event_type,
                payload=payload,
            )
        except PaymentError as exc:
            # Reuse the shared resolver so webhook errors carry the same codes and
            # messages as everywhere else.  Reading ``detail.get("code")`` here
            # would always be None: DRF puts the code on the nested ErrorDetail,
            # so every webhook failure would wrongly surface as a 500.
            code = code_for(exc)
            http_status = (
                status.HTTP_400_BAD_REQUEST
                if code in {"invalid_signature", "unknown_order", "forbidden"}
                else status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            return Response(
                {
                    "error": {
                        "code": code or "webhook_error",
                        "message": message_for(exc),
                        "details": None,
                    }
                },
                status=http_status,
            )

        return Response(result, status=status.HTTP_200_OK)


class MyPaymentsView(generics.ListAPIView):
    """GET /api/v1/payments/ -- the caller's own payment history."""

    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Schema generation resolves this with an AnonymousUser, which is not a
        # valid UUID filter value; ``none()`` keeps the endpoint documented.
        if is_schema_generation(self):
            return Payment.objects.none()
        return (
            Payment.objects.filter(user=self.request.user)
            .select_related("plan")
            .order_by("-created_at")
        )


class AdminPaymentListView(generics.ListAPIView):
    """GET /api/v1/payments/all/ -- admin listing with filters."""

    serializer_class = PaymentAdminSerializer
    permission_classes = [IsAdminRole]

    def get_queryset(self):
        queryset = Payment.objects.select_related("user", "plan").order_by(
            "-created_at"
        )
        params = self.request.query_params
        if params.get("status"):
            queryset = queryset.filter(status=params["status"])
        if params.get("user"):
            queryset = queryset.filter(user_id=params["user"])
        if params.get("order_id"):
            queryset = queryset.filter(provider_order_id=params["order_id"])
        return queryset


class AdminWebhookEventListView(generics.ListAPIView):
    """GET /api/v1/payments/webhook-events/ -- admin webhook audit trail."""

    serializer_class = WebhookEventSerializer
    permission_classes = [IsAdminRole]

    def get_queryset(self):
        queryset = WebhookEvent.objects.order_by("-received_at")
        if self.request.query_params.get("processed") is not None:
            queryset = queryset.filter(
                processed=self.request.query_params["processed"] == "true"
            )
        return queryset
