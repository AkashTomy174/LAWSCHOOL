"""Notification admin."""

from django.contrib import admin

from apps.notifications.models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "user",
        "kind",
        "channel",
        "title",
        "read_at",
        "sent_at",
    )
    list_filter = ("kind", "channel", "read_at", "created_at")
    search_fields = ("user__email", "user__name", "title", "body")
    list_select_related = ("user",)
    date_hierarchy = "created_at"
    readonly_fields = ("created_at", "sent_at", "delivery_error", "attempts")

    def has_add_permission(self, request):
        # Notifications are produced by domain events, not by hand.
        return False
