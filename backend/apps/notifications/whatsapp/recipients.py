"""Bulk recipient selection -- a single indexed queryset, never a Python loop over users.

Entitlement mirrors ``subscriptions.services.can_user_access_course`` (free
published course -> every student; otherwise an active subscription whose plan is
all-access or lists the course), expressed in SQL so a class with thousands of
students costs one query.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from apps.core.constants import (
    CourseStatus,
    SubscriptionStatus,
    UnlockRule,
    UserRole,
)
from apps.notifications.models import ConsentStatus

CHUNK = 500


def consenting_students(category: str):
    """Active students who verified a number, opted in and enabled ``category``."""
    User = get_user_model()
    prefix = "notification_preference__"
    return User.objects.filter(
        is_active=True,
        role=UserRole.STUDENT,
        **{
            f"{prefix}whatsapp_enabled": True,
            f"{prefix}consent_status": ConsentStatus.OPTED_IN,
            f"{prefix}whatsapp_verified_at__isnull": False,
            f"{prefix}{category}_enabled": True,
        },
    ).select_related("notification_preference")


def active_subscription_user_ids(*, course=None):
    from apps.subscriptions.models import Subscription

    now = timezone.now()
    qs = Subscription.objects.filter(
        status=SubscriptionStatus.ACTIVE, start_date__lte=now
    ).filter(Q(end_date__isnull=True) | Q(end_date__gt=now))
    if course is not None:
        qs = qs.filter(Q(plan__is_all_access=True) | Q(plan__courses=course))
    return qs.values("user_id")


def students_entitled_to_course(course, category: str):
    """Consenting students allowed to attend/watch ``course``."""
    qs = consenting_students(category)
    if course.status != CourseStatus.PUBLISHED:
        return qs.none()
    if course.unlock_rule == UnlockRule.FREE:
        return qs
    return qs.filter(id__in=active_subscription_user_ids(course=course))


def iterate(queryset):
    """Stream rows in bounded chunks (never loads the whole audience)."""
    return queryset.order_by("pk").iterator(chunk_size=CHUNK)
