"""Subscription selectors -- prefetched querysets for the pricing and account pages."""

from __future__ import annotations

from django.db.models import Prefetch, QuerySet

from apps.subscriptions.models import Plan, Subscription


def active_plans() -> QuerySet[Plan]:
    """Public pricing list.  ``courses`` is prefetched so ``course_slugs`` is free."""
    from apps.courses.models import Course

    return (
        Plan.objects.filter(is_active=True)
        .prefetch_related(
            Prefetch(
                "courses", queryset=Course.objects.only("id", "slug", "title", "status")
            )
        )
        .order_by("ordering", "price")
    )


def all_plans() -> QuerySet[Plan]:
    return Plan.objects.all().order_by("ordering", "price")


def user_subscriptions(user, *, status: str | None = None) -> QuerySet[Subscription]:
    queryset = (
        Subscription.objects.filter(user=user)
        .select_related("plan")
        .prefetch_related("plan__courses")
        .order_by("-created_at")
    )
    if status:
        queryset = queryset.filter(status=status)
    return queryset


def current_subscription(user) -> Subscription | None:
    """Most relevant subscription for the dashboard.

    Prefers an active one; otherwise the most recent attempt so the UI can show
    "your last payment failed" rather than an empty state.
    """
    from apps.subscriptions.services import get_active_subscription

    active = get_active_subscription(user)
    if active is not None:
        return active
    return (
        Subscription.objects.filter(user=user)
        .select_related("plan")
        .order_by("-created_at")
        .first()
    )


def all_subscriptions(
    *, status: str | None = None, user_id=None
) -> QuerySet[Subscription]:
    queryset = Subscription.objects.select_related("user", "plan").order_by(
        "-created_at"
    )
    if status:
        queryset = queryset.filter(status=status)
    if user_id:
        queryset = queryset.filter(user_id=user_id)
    return queryset
