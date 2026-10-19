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


from apps.notifications.models import (  # noqa: E402
    NotificationAuditLog,
    NotificationPreference,
    NotificationSettings,
    NotificationTemplate,
)


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    list_display = ("internal_name", "provider_template_name", "meta_category", "approval_status", "active")
    list_filter = ("approval_status", "meta_category", "active")


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "consent_status", "whatsapp_enabled", "whatsapp_verified_at")
    list_filter = ("consent_status", "whatsapp_enabled")
    search_fields = ("user__email",)
    # Phone numbers are personal data: shown, never editable here, so consent
    # cannot be forged from the admin.
    readonly_fields = [f.name for f in NotificationPreference._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(NotificationSettings)
class NotificationSettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not NotificationSettings.objects.exists()


@admin.register(NotificationAuditLog)
class NotificationAuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "subject_user_id")
    readonly_fields = [f.name for f in NotificationAuditLog._meta.fields]

    def has_add_permission(self, request):
        return False
