"""Subscription + plan serializers."""

from __future__ import annotations

from rest_framework import serializers

from apps.courses.models import Course
from apps.subscriptions.models import Plan, Subscription


class PlanSerializer(serializers.ModelSerializer):
    """Public plan shape used by the pricing page and the checkout flow."""

    course_slugs = serializers.SerializerMethodField()
    course_count = serializers.SerializerMethodField()

    class Meta:
        model = Plan
        fields = (
            "id",
            "name",
            "slug",
            "description",
            "price",
            "currency",
            "duration_days",
            "is_all_access",
            "is_featured",
            "ordering",
            "course_slugs",
            "course_count",
        )

    def get_course_slugs(self, obj: Plan) -> list[str]:
        # The selector prefetches ``courses``; if not, Django issues one query.
        return [course.slug for course in obj.courses.all()]

    def get_course_count(self, obj: Plan) -> int:
        if obj.is_all_access:
            return Course.objects.filter(status="published").count()
        return len(obj.courses.all())


class PlanWriteSerializer(serializers.ModelSerializer):
    """Admin-only plan authoring."""

    courses = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Course.objects.all(), required=False
    )

    class Meta:
        model = Plan
        fields = (
            "id",
            "name",
            "slug",
            "description",
            "price",
            "currency",
            "duration_days",
            "courses",
            "is_all_access",
            "is_active",
            "is_featured",
            "ordering",
        )
        read_only_fields = ("id",)

    def validate_price(self, value):
        if value < 0:
            raise serializers.ValidationError("Price cannot be negative.")
        return value

    def validate_duration_days(self, value: int) -> int:
        if value < 1:
            raise serializers.ValidationError("Duration must be at least one day.")
        return value


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = PlanSerializer(read_only=True)
    days_remaining = serializers.IntegerField(read_only=True)
    is_currently_active = serializers.BooleanField(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Subscription
        fields = (
            "id",
            "plan",
            "status",
            "status_display",
            "start_date",
            "end_date",
            "payment_reference",
            "cancelled_at",
            "days_remaining",
            "is_currently_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class SubscriptionAdminSerializer(SubscriptionSerializer):
    """Admin view -- adds the owning user (never exposed to other students)."""

    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_name = serializers.CharField(source="user.name", read_only=True)

    class Meta(SubscriptionSerializer.Meta):
        fields = SubscriptionSerializer.Meta.fields + ("user_email", "user_name")
        read_only_fields = fields


class CancelSubscriptionSerializer(serializers.Serializer):
    """Body for a cancellation request."""

    immediate = serializers.BooleanField(
        default=False,
        help_text="When true, access ends now instead of at the end of the paid term.",
    )
