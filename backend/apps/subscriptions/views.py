"""Subscription API views: plans (public), my subscription, cancel, admin list."""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsAdminRole, is_schema_generation
from apps.subscriptions import selectors
from apps.subscriptions.models import Plan, Subscription
from apps.subscriptions.serializers import (
    CancelSubscriptionSerializer,
    PlanSerializer,
    PlanWriteSerializer,
    SubscriptionAdminSerializer,
    SubscriptionSerializer,
)
from apps.subscriptions.services import get_active_subscription
from apps.subscriptions.services_lifecycle import cancel_subscription


class PlanListView(generics.ListCreateAPIView):
    """GET /api/v1/subscriptions/plans/ public · POST admin-only."""

    permission_classes = [AllowAny]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAdminRole()]
        return super().get_permissions()

    def get_serializer_class(self):
        return PlanWriteSerializer if self.request.method == "POST" else PlanSerializer

    def get_queryset(self):
        if self.request.method == "POST":
            return selectors.all_plans()
        return selectors.active_plans()


class PlanDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET /api/v1/subscriptions/plans/<slug>/ -- public read, admin write."""

    lookup_field = "slug"
    permission_classes = [AllowAny]

    def get_permissions(self):
        if self.request.method in {"PATCH", "PUT", "DELETE"}:
            return [IsAdminRole()]
        return super().get_permissions()

    def get_serializer_class(self):
        if self.request.method in {"PATCH", "PUT"}:
            return PlanWriteSerializer
        return PlanSerializer

    def get_queryset(self):
        if self.request.method in {"PATCH", "PUT"}:
            return selectors.all_plans()
        return selectors.active_plans() | selectors.all_plans().filter(is_active=False)


class MySubscriptionView(APIView):
    """GET /api/v1/subscriptions/me/ -- the caller's current + past subscriptions.

    Entitlement is *not* trusted from this payload by other endpoints; it is a
    presentation convenience that mirrors what the server will enforce.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: SubscriptionSerializer})
    def get(self, request):
        active = get_active_subscription(request.user)
        history = selectors.user_subscriptions(request.user)[:10]
        return Response(
            {
                "active": SubscriptionSerializer(active).data if active else None,
                "has_active_subscription": active is not None,
                "history": SubscriptionSerializer(history, many=True).data,
            }
        )


class SubscriptionHistoryView(generics.ListAPIView):
    """GET /api/v1/subscriptions/history/ -- paginated history for the caller."""

    serializer_class = SubscriptionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # See apps.core.permissions.is_schema_generation: an AnonymousUser cannot be
        # used as a UUID filter during OpenAPI generation.
        if is_schema_generation(self):
            return Subscription.objects.none()
        return selectors.user_subscriptions(
            self.request.user, status=self.request.query_params.get("status")
        )


class CancelMySubscriptionView(APIView):
    """POST /api/v1/subscriptions/me/cancel/ -- cancel the active subscription."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CancelSubscriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        subscription = get_active_subscription(request.user)
        if subscription is None:
            return Response(
                {
                    "error": {
                        "code": "no_active_subscription",
                        "message": "You do not have an active subscription to cancel.",
                        "details": None,
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        cancel_subscription(
            subscription=subscription, immediate=serializer.validated_data["immediate"]
        )
        return Response(
            {
                "detail": "Subscription cancelled.",
                "access_ends": subscription.end_date,
                "subscription": SubscriptionSerializer(subscription).data,
            }
        )


class AdminSubscriptionListView(generics.ListAPIView):
    """GET /api/v1/subscriptions/ -- admin listing with status filter + pagination."""

    serializer_class = SubscriptionAdminSerializer
    permission_classes = [IsAdminRole]

    def get_queryset(self):
        return selectors.all_subscriptions(
            status=self.request.query_params.get("status"),
            user_id=self.request.query_params.get("user"),
        )


class AdminSubscriptionDetailView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/v1/subscriptions/<uuid>/ -- admin record (status corrections)."""

    serializer_class = SubscriptionAdminSerializer
    permission_classes = [IsAdminRole]
    queryset = Subscription.objects.select_related("user", "plan")
    http_method_names = ["get", "patch", "head", "options"]
