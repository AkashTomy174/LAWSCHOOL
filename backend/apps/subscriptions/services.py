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

from dataclasses import dataclass, field
from datetime import datetime

from django.core.cache import cache

from apps.core.cache import cache_delete_many, cache_set, report_cache_failure
from django.db import transaction
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
    # When a subscription grant runs out (None: open-ended or not subscription-based).
    # Excluded from equality so ``decision == ALLOW_SUBSCRIPTION`` keeps working.
    expires_at: datetime | None = field(default=None, compare=False)

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
    subscriptions = active_subscriptions(user)
    return subscriptions[0] if subscriptions else None


def active_subscriptions(user) -> list:
    """Every subscription granting access right now, latest-ending first.

    Access is the *union* of these: a user may hold several at once (All Access
    plus a single-course plan bought later), and none may hide another.
    """
    if not (user and user.is_authenticated):
        return []
    now = timezone.now()
    return list(
        user.subscriptions.select_related("plan")
        .filter(status=SubscriptionStatus.ACTIVE, start_date__lte=now)
        .filter(Q(end_date__isnull=True) | Q(end_date__gt=now))
        .order_by("-end_date")
    )


def _earliest_end(subscriptions) -> datetime | None:
    ends = [s.end_date for s in subscriptions if s.end_date is not None]
    return min(ends) if ends else None


def _cache_ttl(ends_at: datetime | None) -> int:
    """Cache lifetime for an answer that stops being true at ``ends_at``.

    Never outlives the subscription it came from: natural expiry fires no event
    to invalidate on, so the TTL itself is the guard.
    """
    if ends_at is None:
        return _ENTITLEMENT_CACHE_TTL
    remaining = int((ends_at - timezone.now()).total_seconds())
    return max(1, min(_ENTITLEMENT_CACHE_TTL, remaining))


def has_active_subscription(user) -> bool:
    if not (user and user.is_authenticated):
        return False
    cache_key = f"entitlement:has_sub:{user.pk}"
    cached = _cached(lambda: cache.get(cache_key))
    if cached is not None:
        return bool(cached)
    subscriptions = active_subscriptions(user)
    cache_set(cache_key, bool(subscriptions), _cache_ttl(_earliest_end(subscriptions)))
    return bool(subscriptions)


# The entitlement cache is only an optimisation: if Redis is unreachable every
# answer is computed from the database, and a cache failure can never turn a
# denial into an allow.  Any failure building a key (the generation counters
# live in the cache too) or reading it skips the cache for that request.
_UNAVAILABLE = object()


def _cached(read):
    """Run a cache read; ``None`` on a miss *or* when the cache is down."""
    try:
        return read()
    except Exception as exc:
        report_cache_failure("get", exc)
        return None


def _key_or_unavailable(build):
    try:
        return build()
    except Exception as exc:
        report_cache_failure("get", exc)
        return _UNAVAILABLE


def invalidate_entitlement_cache(user, *, course=None) -> None:
    """Drop cached entitlement answers for a user.

    Called whenever a subscription changes state (activation, expiry, cancel) so
    the change is visible immediately rather than after the TTL.

    * ``entitlement:has_sub:<user>``  -- the coarse "has any subscription" flag
    * ``entitlement:courses:<plans>:<user>`` -- the bulk id set used by list pages
    * ``entitlement:dec:<plans>:<generation>:<user>:<course>`` -- per-course decision

    ``<plans>`` is the global plans generation (see ``bump_plans_generation``):
    a plan change orphans every user's cached answers at once.

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
    _now_and_after_commit(lambda: _invalidate(user_id, course))


def _now_and_after_commit(invalidate) -> None:
    """Run a cache invalidation now, and again once the transaction commits.

    Now: so reads later in the same transaction (and tests) see the change.
    After commit: a concurrent request that read the *pre-commit* rows between the
    first invalidation and the commit may have cached that stale answer under the
    new key; the second pass orphans it.  Outside a transaction ``on_commit`` runs
    immediately, so this is just a harmless double invalidation.
    """
    invalidate()
    transaction.on_commit(invalidate)


def _invalidate(user_id, course) -> None:
    # Never raises: a failed invalidation must not roll back the subscription
    # change that triggered it.  While the cache is down nothing is cached, and
    # anything written just before the outage expires within the TTL.
    try:
        keys = [f"entitlement:has_sub:{user_id}", _courses_key(user_id)]
        if course is not None:
            # Targeted invalidation for a single course.
            keys.append(
                _course_decision_key(user_id, course.pk, entitlement_generation(user_id))
            )
    except Exception as exc:
        report_cache_failure("delete_many", exc)
        return
    cache_delete_many(keys)

    if course is None:
        # Bump the generation, orphaning every per-course entry for this user.
        _incr_forever(_generation_key(user_id))


def _incr_forever(key) -> None:
    """Increment a never-expiring counter, creating it at 1; never raises."""
    try:
        cache.incr(key)
    except ValueError:
        # Key absent (first increment, or evicted): start at 1.
        cache_set(key, 1, None)
    except Exception as exc:
        report_cache_failure("incr", exc)


def _generation_key(user_id) -> str:
    """Cache key holding the entitlement generation for a user."""
    return f"entitlement:generation:{user_id}"


def entitlement_generation(user_id) -> int:
    """Current generation for a user (0 when never invalidated)."""
    return cache.get(_generation_key(user_id), 0)


def _course_decision_key(user_id, course_id, generation: int) -> str:
    """Cache key for a single (user, course) entitlement decision."""
    return f"entitlement:dec:{plans_generation()}:{generation}:{user_id}:{course_id}"


def _courses_key(user_id) -> str:
    """Cache key for a user's bulk accessible-course id set."""
    return f"entitlement:courses:{plans_generation()}:{user_id}"


_PLANS_GENERATION_KEY = "entitlement:plans_generation"


def plans_generation() -> int:
    """Global counter bumped whenever any plan's coverage may have changed."""
    return cache.get(_PLANS_GENERATION_KEY, 0)


def bump_plans_generation(**_signal_kwargs) -> None:
    """A plan changed: orphan every cached entitlement answer, for every user.

    Which courses a plan covers (``courses``, ``is_all_access``) is baked into the
    cached decisions, and a plan has an unknown number of subscribers, so a
    per-user invalidation is not an option.  Without this, removing a course from
    a plan left it watchable for up to the cache TTL (and adding one stayed locked).
    Connected to Plan saves/deletes and ``Plan.courses`` changes in ``apps.py``,
    which covers the API, the Django admin and the ORM alike.
    """
    _now_and_after_commit(_incr_plans_generation)


def _incr_plans_generation() -> None:
    _incr_forever(_PLANS_GENERATION_KEY)


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
    cache_key = _key_or_unavailable(
        lambda: _course_decision_key(user.pk, course.pk, entitlement_generation(user.pk))
    )
    cached = None if cache_key is _UNAVAILABLE else _cached(lambda: cache.get(cache_key))
    if cached is not None:
        # ``*rest``: entries written before ``expires_at`` existed are 3-tuples.
        allowed, reason, detail, *rest = cached
        return AccessDecision(allowed, reason, detail, rest[0] if rest else None)

    subscriptions = active_subscriptions(user)
    covering = _covering(subscriptions, course)
    if covering:
        # Access lasts until the *last* covering subscription ends.
        ends = [s.end_date for s in covering]
        expires_at = None if None in ends else max(ends)
        decision = AccessDecision(
            True, ALLOW_SUBSCRIPTION.reason, ALLOW_SUBSCRIPTION.detail, expires_at
        )
    elif subscriptions:
        decision = DENY_PLAN_EXCLUDES_COURSE
    else:
        # Differentiate "never subscribed" from "lapsed" so the UI can show the
        # right call to action (Buy vs Renew).
        decision = (
            DENY_SUBSCRIPTION_EXPIRED
            if user.subscriptions.exists()
            else DENY_NO_SUBSCRIPTION
        )

    if cache_key is not _UNAVAILABLE:
        cache_set(
            cache_key,
            (decision.allowed, decision.reason, decision.detail, decision.expires_at),
            _cache_ttl(decision.expires_at),
        )
    return decision


def _covering(subscriptions, course) -> list:
    """The subscriptions whose plan covers ``course`` (one query for all of them)."""
    if not subscriptions:
        return []
    from apps.subscriptions.models import Plan

    listed = set(
        Plan.courses.through.objects.filter(
            course_id=course.pk, plan_id__in=[s.plan_id for s in subscriptions]
        ).values_list("plan_id", flat=True)
    )
    return [s for s in subscriptions if s.plan.is_all_access or s.plan_id in listed]


def can_user_access_lesson(user, lesson) -> AccessDecision:
    """Lesson-level gate: previews are open, everything else inherits the course rule."""
    if lesson is None:
        return DENY_LESSON_UNAVAILABLE

    if not (user and user.is_authenticated):
        # Preview lessons are the one thing an anonymous visitor may see, so the
        # course details page can advertise content without leaking video data.
        if (
            lesson.is_preview
            and lesson.status == LessonStatus.PUBLISHED
            and lesson.section.course.status == CourseStatus.PUBLISHED
        ):
            return ALLOW_PREVIEW
        return DENY_ANONYMOUS

    if user.role == UserRole.ADMIN or user.is_staff:
        return ALLOW_ADMIN

    course = lesson.section.course
    if user.role == UserRole.INSTRUCTOR and course.instructor_id == user.pk:
        return ALLOW_INSTRUCTOR

    if lesson.status != LessonStatus.PUBLISHED:
        return DENY_LESSON_UNAVAILABLE
    # Checked before the preview shortcut: a draft/archived course's previews
    # are as unpublished as the rest of it.
    if course.status != CourseStatus.PUBLISHED:
        return DENY_NOT_PUBLISHED

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

    cache_key = _key_or_unavailable(lambda: _courses_key(user.pk))
    cached = None if cache_key is _UNAVAILABLE else _cached(lambda: cache.get(cache_key))
    if cached is not None:
        return set(cached)

    subscriptions: list = []
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

        subscriptions = active_subscriptions(user)
        subscription_ids: set = set()
        if any(s.plan.is_all_access for s in subscriptions):
            subscription_ids = set(
                Course.objects.filter(status=CourseStatus.PUBLISHED).values_list(
                    "id", flat=True
                )
            )
        elif subscriptions:
            subscription_ids = set(
                Course.objects.filter(
                    status=CourseStatus.PUBLISHED,
                    plans__in=[s.plan_id for s in subscriptions],
                ).values_list("id", flat=True)
            )

        ids = free_ids | owned_ids | subscription_ids

    # The set shrinks as soon as *any* contributing subscription ends.
    if cache_key is not _UNAVAILABLE:
        cache_set(cache_key, list(ids), _cache_ttl(_earliest_end(subscriptions)))
    return ids


def user_can_watch_any_paid_course(user) -> bool:
    return has_active_subscription(user)
