"""Notification API views -- in-app feed, unread badge, mark-as-read."""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.constants import NotificationChannel
from apps.core.pagination import LargeResultsSetPagination
from apps.core.permissions import is_schema_generation
from apps.notifications import services
from apps.notifications.models import Notification
from apps.notifications.serializers import MarkReadSerializer, NotificationSerializer


class NotificationListView(generics.ListAPIView):
    """GET /api/v1/notifications/ -- the caller's in-app feed (paginated)."""

    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = LargeResultsSetPagination

    def get_queryset(self):
        # See apps.core.permissions.is_schema_generation: an AnonymousUser cannot be
        # used as a UUID filter while the OpenAPI document is being built.
        if is_schema_generation(self):
            return Notification.objects.none()
        # ``user`` + ``channel`` + ``read_at`` is a covering index, so filtering on
        # unread is cheap even with a long history.
        queryset = Notification.objects.filter(
            user=self.request.user, channel=NotificationChannel.IN_APP
        ).order_by("-created_at")
        if self.request.query_params.get("unread") == "true":
            queryset = queryset.filter(read_at__isnull=True)
        return queryset


class UnreadCountView(APIView):
    """GET /api/v1/notifications/unread-count/ -- badge number for the navbar."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"unread": services.unread_count(request.user)})


class MarkReadView(APIView):
    """POST /api/v1/notifications/read/ -- mark one or all notifications read."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=MarkReadSerializer)
    def post(self, request):
        serializer = MarkReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if serializer.validated_data.get("all"):
            updated = services.mark_all_read(request.user)
            return Response({"detail": f"Marked {updated} notification(s) as read."})

        notification = get_object_or_404(
            Notification,
            pk=serializer.validated_data["notification_id"],
            user=request.user,
        )
        notification.mark_read()
        return Response(
            NotificationSerializer(notification).data, status=status.HTTP_200_OK
        )
