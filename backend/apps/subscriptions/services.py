"""Entitlement / access-control service.

**This is the one place that decides whether a user may consume content.** Every
protected course, lesson and video endpoint calls into this module -- no view,
serializer or frontend check is allowed to reimplement the rule.

Resolution order for ``can_user_access_course``:

1. Unauthenticated -> deny.
2. Instructor who owns the course, or admin -> allow (authoring rights).
3. Course is ``FREE`` and published -> allow.
4. An ACTIVE, in-window subscription whose plan covers the course -> allow.
5. Otherwise -> deny with a machine-readable reason.

The returned :class:`AccessDecision` carries *why* access was granted or denied
so the API can tell the UI "subscribe", "renew", "not included in your plan"
instead of a bare 403.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone

from apps.core.constants import (
    CourseStatus,
    LessonStatus,
    SubscriptionStatus,
    UnlockRule,
    UserRole,
)

# Short cache TTL: long enough to absorb the burst of playback/progress calls a
# single page view makes, short enough that a cancellation takes effect quickly.
_ENTITLEMENT_CACHE_TTL = 60


@dataclass(frozen=True)
class AccessDecision:
    """Result of an entitlement check.

    ``allowed`` drives the HTTP status; ``reason`` and ``detail`` drive the UX.
    """

    allowed: bool
    reason: str
    detail: str = ""

    def __bool__(self) -> bool:  # allows `if decision:`
        return self.allowed


ALLOW_ADMIN = AccessDecision(True, "admin", "Administrator access.")
ALLOW_INSTRUCTOR = AccessDecision(True, "instructor", "You own this course.")
ALLOW_FREE = AccessDecision(True, "free_course", "This course is free.")
ALLOW_PREVIEW = AccessDecision(True, "preview_lesson", "This lesson is a free preview.")
ALLOW_SUBSCRIPTION = AccessDecision(
    True, "active_subscription", "Your subscription covers this course."
)

DENY_ANONYMOUS = AccessDecision(
    False, "authentication_required", "Sign in to access this content."
)
DENY_NOT_PUBLISHED = AccessDecision(
    False, "not_published", "This content is not published yet."
)
DENY_NO_SUBSCRIPTION = AccessDecision(
    False,
    "subscription_required",
    "An active subscription is required for this course.",
)
DENY_SUBSCRIPTION_EXPIRED = AccessDecision(
    False, "subscription_expired", "Your subscription has expired. Renew to continue."
)
DENY_PLAN_EXCLUDES_COURSE = AccessDecision(
    False, "not_in_plan", "Your current plan does not include this course."
)
DENY_LESSON_UNAVAILABLE = AccessDecision(
    False, "lesson_unavailable", "This lesson is not available."
)


# --------------------------------------------------------------------------- #
# Subscription lookups
# --------------------------------------------------------------------------- #
def get_active_subscription(user):
    """Return the user's usable subscription, or ``None``.

    Filters in SQL on ``(status, start_date, end_date)`` so the expiry window is
    enforced by the database rather than by trusting a possibly-stale status
    column.
    """
    if not (user and user.is_authenticated):
        return None
    now = timezone.now()
    return (
        user.subscriptions.select_related("plan")
        .filter(status=SubscriptionStatus.ACTIVE, start_date__lte=now)
        .filter(Q(end_date__isnull=True) | Q(end_date__gt=now))
        .order_by("-end_date")
        .first()
    )


def has_active_subscription(user) -> bool:
    if not (user and user.is_authenticated):
        return False
    cache_key = f"entitlement:has_sub:{user.pk}"
    cached = cache.get(cache_key)
    if cached is not None:
        return bool(cached)
    result = get_active_subscription(user) is not None
    cache.set(cache_key, result, _ENTITLEMENT_CACHE_TTL)
    return result


def invalidate_entitlement_cache(user, *, course=None) -> None:
    """Drop cached entitlement answers for a user.

    Called whenever a subscription changes state (activation, expiry, cancel) so
    the change is visible immediately rather than after the TTL.

    * ``entitlement:has_sub:<user>``  -- the coarse "has any subscription" flag
    * ``entitlement:courses:<user>``  -- the bulk id set used by list pages
    * ``entitlement:dec:<generation>:<user>:<course>`` -- per-course decision

    The per-course key embeds a **generation counter** bumped here.  That is what
    makes invalidation complete without enumerating an unknown set of course
    keys: bumping the generation orphans every previously written entry at once,
    so a stale "allowed" answer cannot survive.

    Missing the per-course entry was a real bug found by the test suite: the bulk
    set refreshed while the per-course answer stayed stale, which would have let a
    lapsed student keep watching for up to the TTL.
    """
    if user is None:
        return
    user_id = getattr(user, "pk", user)

    keys = [f"entitlement:has_sub:{user_id}", f"entitlement:courses:{user_id}"]
    if course is not None:
        # Targeted invalidation for a single course.
        keys.append(
            _course_decision_key(user_id, course.pk, entitlement_generation(user_id))
        )
    cache.delete_many(keys)

    if course is None:
        # Bump the generation, orphaning every per-course entry for this user.
        try:
            cache.incr(_generation_key(user_id))
        except ValueError:
            # Key absent (first invalidation, or it expired): start at 1.
            cache.set(_generation_key(user_id), 1, timeout=None)


def _generation_key(user_id) -> str:
    """Cache key holding the entitlement generation for a user."""
    return f"entitlement:generation:{user_id}"


def entitlement_generation(user_id) -> int:
    """Current generation for a user (0 when never invalidated)."""
    return cache.get(_generation_key(user_id), 0)


def _course_decision_key(user_id, course_id, generation: int) -> str:
    """Cache key for a single (user, course) entitlement decision."""
    return f"entitlement:dec:{generation}:{user_id}:{course_id}"


# --------------------------------------------------------------------------- #
# Core checks
# --------------------------------------------------------------------------- #
def can_user_access_course(user, course) -> AccessDecision:
    """Decide whether ``user`` may consume ``course``.

    Cheap, cached per user, and safe to call on every request.
    """
    if course is None:
        return DENY_LESSON_UNAVAILABLE

    if not (user and user.is_authenticated):
        return DENY_ANONYMOUS

    if user.role == UserRole.ADMIN or user.is_staff:
        return ALLOW_ADMIN
    if user.role == UserRole.INSTRUCTOR and course.instructor_id == user.pk:
        return ALLOW_INSTRUCTOR

    # Students must not reach draft/archived material.
    if course.status != CourseStatus.PUBLISHED:
        return DENY_NOT_PUBLISHED

    if course.unlock_rule == UnlockRule.FREE:
        return ALLOW_FREE

    return _subscription_decision(user, course)


def _subscription_decision(user, course) -> AccessDecision:
    """Evaluate subscription coverage, distinguishing 'none' from 'expired'."""
    # The generation counter is read on every call so an invalidation performed by
    # another process immediately stops this key from being written or honoured.
    cache_key = _course_decision_key(
        user.pk, course.pk, entitlement_generation(user.pk)
    )
    cached = cache.get(cache_key)
    if cached is not None:
        allowed, reason, detail = cached
        return AccessDecision(allowed, reason, detail)

    active = get_active_subscription(user)
    if active is not None:
        if (
            active.plan.is_all_access
            or active.plan.courses.filter(pk=course.pk).exists()
        ):
            decision = ALLOW_SUBSCRIPTION
        else:
            decision = DENY_PLAN_EXCLUDES_COURSE
    else:
        # Differentiate "never subscribed" from "lapsed" so the UI can show the
        # right call to action (Buy vs Renew).
        decision = (
            DENY_SUBSCRIPTION_EXPIRED
            if user.subscriptions.exists()
            else DENY_NO_SUBSCRIPTION
        )

    cache.set(
        cache_key,
        (decision.allowed, decision.reason, decision.detail),
        _ENTITLEMENT_CACHE_TTL,
    )
    return decision


def can_user_access_lesson(user, lesson) -> AccessDecision:
    """Lesson-level gate: previews are open, everything else inherits the course rule."""
    if lesson is None:
        return DENY_LESSON_UNAVAILABLE

    if not (user and user.is_authenticated):
        # Preview lessons are the one thing an anonymous visitor may see, so the
        # course details page can advertise content without leaking video data.
        if lesson.is_preview and lesson.status == LessonStatus.PUBLISHED:
            return ALLOW_PREVIEW
        return DENY_ANONYMOUS

    if user.role == UserRole.ADMIN or user.is_staff:
        return ALLOW_ADMIN

    course = lesson.section.course
    if user.role == UserRole.INSTRUCTOR and course.instructor_id == user.pk:
        return ALLOW_INSTRUCTOR

    if lesson.status != LessonStatus.PUBLISHED:
        return DENY_LESSON_UNAVAILABLE

    if lesson.is_preview:
        return ALLOW_PREVIEW

    return can_user_access_course(user, course)


def can_user_access_video(user, video) -> AccessDecision:
    """Video gate. Delegates to the owning lesson so there is exactly one rule."""
    lesson = getattr(video, "lesson", None)
    if lesson is None:
        # An orphaned video row has no course context -> staff only.
        if (
            user
            and user.is_authenticated
            and (user.role == UserRole.ADMIN or user.is_staff)
        ):
            return ALLOW_ADMIN
        return DENY_LESSON_UNAVAILABLE
    return can_user_access_lesson(user, lesson)


# --------------------------------------------------------------------------- #
# Bulk helpers (used by list endpoints to avoid N+1 entitlement calls)
# --------------------------------------------------------------------------- #
def accessible_course_ids(user) -> set:
    """Course ids the user may access, in a constant number of queries.

    Course *list* pages need this to render lock badges without one entitlement
    check per row.  Cached briefly because it only changes when a subscription or
    purchase changes.
    """
    from apps.courses.models import Course

    if not (user and user.is_authenticated):
        return set(
            Course.objects.filter(
                status=CourseStatus.PUBLISHED, unlock_rule=UnlockRule.FREE
            ).values_list("id", flat=True)
        )

    cache_key = f"entitlement:courses:{user.pk}"
    cached = cache.get(cache_key)
    if cached is not None:
        return set(cached)

    if user.role == UserRole.ADMIN or user.is_staff:
        ids = set(Course.objects.values_list("id", flat=True))
    else:
        free_ids = set(
            Course.objects.filter(
                status=CourseStatus.PUBLISHED, unlock_rule=UnlockRule.FREE
            ).values_list("id", flat=True)
        )
        owned_ids = set(
            Course.objects.filter(
                instructor=user, status=CourseStatus.PUBLISHED
            ).values_list("id", flat=True)
        )

        active = get_active_subscription(user)
        subscription_ids: set = set()
        if active is not None:
            if active.plan.is_all_access:
                subscription_ids = set(
                    Course.objects.filter(status=CourseStatus.PUBLISHED).values_list(
                        "id", flat=True
                    )
                )
            else:
                subscription_ids = set(
                    Course.objects.filter(
                        status=CourseStatus.PUBLISHED, plans=active.plan
                    ).values_list("id", flat=True)
                )

        ids = free_ids | owned_ids | subscription_ids

    cache.set(cache_key, list(ids), _ENTITLEMENT_CACHE_TTL)
    return ids


def user_can_watch_any_paid_course(user) -> bool:
    return has_active_subscription(user)
