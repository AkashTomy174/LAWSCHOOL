"""Notification serializers."""

from __future__ import annotations

from rest_framework import serializers

from apps.notifications.models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    is_read = serializers.BooleanField(read_only=True)

    class Meta:
        model = Notification
        fields = (
            "id",
            "kind",
            "kind_display",
            "channel",
            "title",
            "body",
            "action_url",
            "is_read",
            "read_at",
            "created_at",
        )
        read_only_fields = fields


class MarkReadSerializer(serializers.Serializer):
    """Optional body: mark one notification read, or all of them."""

    notification_id = serializers.UUIDField(required=False)
    all = serializers.BooleanField(default=False)

    def validate(self, attrs: dict) -> dict:
        if not attrs.get("all") and not attrs.get("notification_id"):
            raise serializers.ValidationError(
                "Provide 'notification_id' or set 'all' to true."
            )
        return attrs
