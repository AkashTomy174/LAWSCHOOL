"""Cached entitlement answers must not outlive the subscription they came from.

Regression: answers were cached for a flat 60s.  A subscription reaching its
``end_date`` fires no event to invalidate on, so a student whose access was
cached shortly before expiry kept it for up to a minute afterwards.
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone
from freezegun import freeze_time

from apps.subscriptions.services import (
    accessible_course_ids,
    can_user_access_course,
    has_active_subscription,
)


def test_cached_access_ends_with_the_subscription(student, course, active_subscription):
    now = timezone.now()
    active_subscription.end_date = now + timedelta(seconds=10)
    active_subscription.save(update_fields=["end_date"])

    with freeze_time(now) as clock:
        # Warm every cache while the subscription is still running.
        assert can_user_access_course(student, course).allowed
        assert course.id in accessible_course_ids(student)
        assert has_active_subscription(student)

        clock.tick(timedelta(seconds=11))  # past end_date, inside the old 60s TTL

        assert not can_user_access_course(student, course).allowed
        assert course.id not in accessible_course_ids(student)
        assert not has_active_subscription(student)


def test_long_running_subscriptions_still_use_the_normal_ttl(
    student, course, active_subscription
):
    """The cap only bites near expiry; mid-term answers are cached as before."""
    from django.core.cache import cache

    with freeze_time(timezone.now()) as clock:
        assert can_user_access_course(student, course).allowed
        active_subscription.delete()  # no invalidation: the cache is all that answers
        clock.tick(timedelta(seconds=30))
        assert can_user_access_course(student, course).allowed  # still cached
        clock.tick(timedelta(seconds=31))
        assert not can_user_access_course(student, course).allowed  # TTL elapsed
    cache.clear()
