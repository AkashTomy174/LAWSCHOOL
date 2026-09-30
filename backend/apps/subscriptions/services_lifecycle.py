"""Subscription state-machine services.

Every state transition funnels through here so the rules live in one auditable
place and callers cannot create an ACTIVE subscription by merely writing a
status string.
"""

from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.core.constants import SubscriptionStatus
from apps.core.logging import get_logger
from apps.subscriptions.models import Plan, Subscription
from apps.subscriptions.services import invalidate_entitlement_cache

logger = get_logger(__name__)


@transaction.atomic
def activate_subscription(
    *,
    user,
    plan: Plan,
    payment_reference: str = "",
    start: "timezone.datetime | None" = None,
) -> Subscription:
    """Create (or extend) an ACTIVE subscription and return it.

    Why *extend* instead of always creating: a student who renews early would
    otherwise lose the remaining days of their current term.  Renewals therefore
    stack onto the existing ``end_date``.

    The whole operation is wrapped in a transaction because it must not leave a
    half-activated state behind if notification/queueing fails.
    """
    now = start or timezone.now()

    # select_for_update: two webhook retries arriving together must not both
    # compute the same new end_date and create duplicate periods.
    existing = (
        user.subscriptions.select_for_update()
        .filter(
            status=SubscriptionStatus.ACTIVE,
            plan=plan,
        )
        .order_by("-end_date")
        .first()
    )

    if existing is not None and existing.end_date and existing.end_date > now:
        existing.end_date = existing.end_date + timedelta(days=plan.duration_days)
        if payment_reference:
            existing.payment_reference = payment_reference
        existing.save(update_fields=["end_date", "payment_reference", "updated_at"])
        subscription = existing
    else:
        subscription = Subscription.objects.create(
            user=user,
            plan=plan,
            status=SubscriptionStatus.ACTIVE,
            start_date=now,
            end_date=now + timedelta(days=plan.duration_days),
            payment_reference=payment_reference,
        )

    invalidate_entitlement_cache(user)
    logger.info(
        "Subscription activated",
        extra={
            "subscription_id": str(subscription.pk),
            "user_id": str(user.pk),
            "plan": plan.slug,
            "end_date": (
                subscription.end_date.isoformat() if subscription.end_date else None
            ),
        },
    )
    return subscription


@transaction.atomic
def mark_subscription_failed(
    *, subscription: Subscription | None, user, plan: Plan
) -> Subscription:
    """Record a failed attempt (payment declined, signature mismatch, ...).

    A FAILED row is deliberately kept: it gives support a paper trail and lets the
    UI say "your last payment failed" rather than showing nothing at all.
    """
    if subscription is None:
        subscription = Subscription.objects.create(user=user, plan=plan)
    subscription.status = SubscriptionStatus.FAILED
    subscription.save(update_fields=["status", "updated_at"])
    invalidate_entitlement_cache(user)
    logger.warning(
        "Subscription marked failed",
        extra={"subscription_id": str(subscription.pk), "user_id": str(user.pk)},
    )
    return subscription


@transaction.atomic
def cancel_subscription(
    *, subscription: Subscription, immediate: bool = False
) -> Subscription:
    """Cancel a subscription.

    Default behaviour keeps access until ``end_date`` (what users expect from a
    paid term); ``immediate=True`` is the admin/refund path.
    """
    if subscription.status != SubscriptionStatus.ACTIVE:
        return subscription

    now = timezone.now()
    subscription.cancelled_at = now
    if immediate:
        subscription.status = SubscriptionStatus.CANCELLED
        subscription.end_date = now
    # When not immediate the row stays ACTIVE (access continues to end_date) but
    # carries cancelled_at, which suppresses renewals.
    subscription.save(
        update_fields=["status", "cancelled_at", "end_date", "updated_at"]
    )
    invalidate_entitlement_cache(subscription.user)
    return subscription


def expire_lapsed_subscriptions() -> int:
    """Flip every past-due ACTIVE subscription to EXPIRED.  Returns the count.

    Run by Celery beat.  Because entitlement checks also verify the date window in
    SQL, a missed run can never hand out free access -- this job only keeps the
    stored status truthful for reporting and notifications.
    """
    now = timezone.now()
    lapsed = list(
        Subscription.objects.filter(
            status=SubscriptionStatus.ACTIVE, end_date__lt=now
        ).select_related("user", "plan")
    )
    if not lapsed:
        return 0

    Subscription.objects.filter(pk__in=[s.pk for s in lapsed]).update(
        status=SubscriptionStatus.EXPIRED, updated_at=now
    )
    for subscription in lapsed:
        invalidate_entitlement_cache(subscription.user)

    logger.info("Expired lapsed subscriptions", extra={"count": len(lapsed)})
    return len(lapsed)
