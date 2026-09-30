"""Payment + webhook admin."""

from django.contrib import admin
from django.utils.html import format_html

from apps.payments.models import Payment, WebhookEvent


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "provider_order_id",
        "user",
        "plan",
        "amount",
        "currency",
        "status",
        "created_at",
    )
    list_filter = ("status", "provider", "currency", "created_at")
    search_fields = (
        "provider_order_id",
        "provider_payment_id",
        "user__email",
        "user__name",
        "idempotency_key",
    )
    list_select_related = ("user", "plan")
    date_hierarchy = "created_at"
    readonly_fields = (
        "id",
        "provider_order_id",
        "provider_payment_id",
        "provider_signature",
        "provider_payload",
        "created_at",
        "updated_at",
        "captured_at",
    )

    def has_add_permission(self, request):
        # Payments are only ever created by the order service.
        return False

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return self.readonly_fields
        return self.readonly_fields


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = (
        "event_type",
        "event_id",
        "signature_valid",
        "processed",
        "received_at",
        "processing_error_short",
    )
    list_filter = (
        "provider",
        "event_type",
        "signature_valid",
        "processed",
        "received_at",
    )
    search_fields = ("event_id", "event_type")
    date_hierarchy = "received_at"
    readonly_fields = tuple(field.name for field in WebhookEvent._meta.fields)

    @admin.display(description="Error")
    def processing_error_short(self, obj):
        if not obj.processing_error:
            return format_html('<span style="color:#999">--</span>')
        return format_html(
            '<span style="color:#b00">{}</span>', obj.processing_error[:80]
        )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
