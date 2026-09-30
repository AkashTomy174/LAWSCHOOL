"""Subscription + plan admin."""

from django.contrib import admin, messages

from apps.subscriptions.models import Plan, Subscription


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "price",
        "currency",
        "duration_days",
        "is_all_access",
        "is_active",
        "is_featured",
        "ordering",
    )
    list_filter = ("is_active", "is_all_access", "is_featured", "currency")
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}
    filter_horizontal = ("courses",)
    ordering = ("ordering", "price")


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "plan",
        "status",
        "start_date",
        "end_date",
        "days_remaining_display",
        "payment_reference",
    )
    list_filter = ("status", "plan", "created_at")
    search_fields = ("user__email", "user__name", "payment_reference")
    list_select_related = ("user", "plan")
    date_hierarchy = "created_at"
    readonly_fields = ("created_at", "updated_at", "payment_reference")
    actions = ["activate_selected", "expire_selected"]
    autocomplete_fields = ()

    @admin.display(description="Days left")
    def days_remaining_display(self, obj):
        return obj.days_remaining

    @admin.action(description="Activate selected subscriptions")
    def activate_selected(self, request, queryset):
        from apps.subscriptions.services_lifecycle import activate_subscription

        count = 0
        for subscription in queryset.select_related("user", "plan"):
            activate_subscription(user=subscription.user, plan=subscription.plan)
            count += 1
        self.message_user(
            request, f"Activated {count} subscription(s).", messages.SUCCESS
        )

    @admin.action(description="Mark selected subscriptions expired")
    def expire_selected(self, request, queryset):
        from django.utils import timezone

        from apps.subscriptions.services import invalidate_entitlement_cache

        for subscription in queryset:
            subscription.status = "expired"
            subscription.end_date = timezone.now()
            subscription.save(update_fields=["status", "end_date", "updated_at"])
            invalidate_entitlement_cache(subscription.user)
        self.message_user(request, "Subscriptions expired.", messages.SUCCESS)
