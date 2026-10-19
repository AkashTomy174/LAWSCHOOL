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
    # Every field is read-only: a payment's status/amount/ownership may only change
    # through apps.payments.services (verification, webhooks, refunds), which hold
    # the row lock and keep the subscription in step.  Editing them here would
    # bypass that state machine (e.g. flipping REFUNDED back to CAPTURED).
    readonly_fields = tuple(f.name for f in Payment._meta.fields)

    def has_add_permission(self, request):
        # Payments are only ever created by the order service.
        return False

    def has_delete_permission(self, request, obj=None):
        # Financial records are kept for audit and dispute handling.
        return False


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
