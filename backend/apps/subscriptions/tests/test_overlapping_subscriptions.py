"""Access is the union of every subscription that currently grants it.

Entitlement rules (unchanged, only now applied to *every* qualifying row):

* A subscription grants access while it is ACTIVE and ``start_date <= now <
  end_date`` (no ``end_date`` = open-ended).  PENDING / FAILED / EXPIRED /
  CANCELLED rows never grant access.
* A user cancellation keeps the row ACTIVE until ``end_date`` (paid term runs
  out); an immediate cancellation or a full refund ends it now.
* A plan covers a course if it is all-access (published courses) or lists it.

Regression: only the subscription ending *last* was consulted, so buying a
180-day single-course plan while 30 days of All Access remained revoked every
other course immediately.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from freezegun import freeze_time

from apps.core.constants import CourseStatus, PaymentStatus, SubscriptionStatus
from apps.courses.models import Course
from apps.subscriptions.services import accessible_course_ids, can_user_access_course
from apps.subscriptions.services_lifecycle import activate_subscription, cancel_subscription
from conftest import make_plan, make_student, make_subscription


@pytest.fixture
def course_b(db, instructor):
    return Course.objects.create(
        title="Course B", slug="course-b", instructor=instructor,
        status=CourseStatus.PUBLISHED, published_at=timezone.now(),
    )


@pytest.fixture
def course_c(db, instructor):
    return Course.objects.create(
        title="Course C", slug="course-c", instructor=instructor,
        status=CourseStatus.PUBLISHED, published_at=timezone.now(),
    )


@pytest.fixture
def all_access(db):
    return make_plan(name="All Access", slug="aa", is_all_access=True, duration_days=365)


@pytest.fixture
def single_a(db, course):
    return make_plan(name="Only A", slug="only-a", courses=[course], duration_days=180)


@pytest.fixture
def single_b(db, course_b):
    return make_plan(name="Only B", slug="only-b", courses=[course_b], duration_days=180)


def allowed(user, course) -> bool:
    return can_user_access_course(user, course).allowed


# --------------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------------- #
def test_all_access_plus_single_course_both_count(student, course, course_b, all_access, single_a):
    make_subscription(student, all_access, ends_in_days=30, payment_reference="aa")
    make_subscription(student, single_a, ends_in_days=180, payment_reference="a")
    assert allowed(student, course) and allowed(student, course_b)
    assert {course.id, course_b.id} <= accessible_course_ids(student)


def test_buying_single_after_all_access_keeps_all_access(student, course, course_b, all_access, single_a):
    """The reported bug: the newer, longer single-course plan hid All Access."""
    make_subscription(student, all_access, ends_in_days=30, payment_reference="aa")
    assert allowed(student, course_b)
    activate_subscription(user=student, plan=single_a, payment_reference="a")
    assert allowed(student, course_b), "All Access still has 30 paid days"
    assert allowed(student, course)
    assert course_b.id in accessible_course_ids(student)


def test_buying_all_access_after_single(student, course, course_b, all_access, single_a):
    activate_subscription(user=student, plan=single_a, payment_reference="a")
    assert not allowed(student, course_b)
    activate_subscription(user=student, plan=all_access, payment_reference="aa")
    assert allowed(student, course) and allowed(student, course_b)


def test_multiple_single_course_subscriptions(student, course, course_b, course_c, single_a, single_b):
    make_subscription(student, single_a, payment_reference="a")
    make_subscription(student, single_b, payment_reference="b")
    assert allowed(student, course) and allowed(student, course_b)
    assert not allowed(student, course_c)
    assert can_user_access_course(student, course_c).reason == "not_in_plan"
    assert accessible_course_ids(student) >= {course.id, course_b.id}
    assert course_c.id not in accessible_course_ids(student)


def test_one_expires_while_another_remains(student, course, course_b, single_a, single_b):
    make_subscription(student, single_a, ends_in_days=10, payment_reference="a")
    make_subscription(student, single_b, ends_in_days=30, payment_reference="b")
    with freeze_time(timezone.now() + timedelta(days=11)):
        assert not allowed(student, course)
        assert allowed(student, course_b)


def test_all_access_expires_but_single_course_remains(student, course, course_b, all_access, single_a):
    make_subscription(student, all_access, ends_in_days=30, payment_reference="aa")
    make_subscription(student, single_a, ends_in_days=180, payment_reference="a")
    with freeze_time(timezone.now() + timedelta(days=31)):
        assert allowed(student, course)
        assert not allowed(student, course_b)
        assert accessible_course_ids(student) & {course.id, course_b.id} == {course.id}


def test_overlapping_coverage_lasts_until_the_later_end(student, course, all_access, single_a):
    make_subscription(student, single_a, ends_in_days=10, payment_reference="a")
    make_subscription(student, all_access, ends_in_days=40, payment_reference="aa")
    decision = can_user_access_course(student, course)
    assert decision.allowed
    assert decision.expires_at > timezone.now() + timedelta(days=39)


# --------------------------------------------------------------------------- #
# Refunds and cancellations revoke only the affected subscription
# --------------------------------------------------------------------------- #
def _captured(user, plan, subscription, suffix):
    from apps.payments.models import Payment

    return Payment.objects.create(
        user=user, plan=plan, subscription=subscription,
        provider_order_id=f"order_{suffix}", provider_payment_id=f"pay_{suffix}",
        amount=plan.price, status=PaymentStatus.CAPTURED,
    )


def test_full_refund_revokes_only_that_subscription(student, course, course_b, all_access, single_a):
    from apps.payments.services import handle_payment_refunded

    aa = make_subscription(student, all_access, ends_in_days=365, payment_reference="aa")
    make_subscription(student, single_a, ends_in_days=180, payment_reference="a")
    payment = _captured(student, all_access, aa, "aa")
    assert allowed(student, course_b)  # warm the cache

    handle_payment_refunded({"payload": {"refund": {"entity": {
        "id": "rfnd_aa", "payment_id": payment.provider_payment_id,
        "amount": payment.amount_paise,
    }}}})

    assert not allowed(student, course_b)
    assert allowed(student, course)


def test_user_cancellation_keeps_access_until_term_end(student, course, single_a):
    sub = make_subscription(student, single_a, ends_in_days=30, payment_reference="a")
    cancel_subscription(subscription=sub)
    assert allowed(student, course)
    with freeze_time(timezone.now() + timedelta(days=31)):
        assert not allowed(student, course)


def test_immediate_cancellation_revokes_only_that_subscription(student, course, course_b, all_access, single_a):
    aa = make_subscription(student, all_access, ends_in_days=365, payment_reference="aa")
    make_subscription(student, single_a, ends_in_days=180, payment_reference="a")
    assert allowed(student, course_b)  # warm the cache
    cancel_subscription(subscription=aa, immediate=True)
    assert not allowed(student, course_b)
    assert allowed(student, course)


@pytest.mark.parametrize(
    "status", [SubscriptionStatus.PENDING, SubscriptionStatus.FAILED,
               SubscriptionStatus.EXPIRED, SubscriptionStatus.CANCELLED],
)
def test_non_active_rows_never_grant_access(student, course, single_a, status):
    make_subscription(student, single_a, status=status, payment_reference="x")
    assert not allowed(student, course)


def test_future_dated_subscription_does_not_grant_access_yet(student, course, single_a):
    make_subscription(student, single_a, starts_in_days=5, ends_in_days=40, payment_reference="x")
    assert not allowed(student, course)


# --------------------------------------------------------------------------- #
# Baselines that must not change
# --------------------------------------------------------------------------- #
def test_no_subscription_denies_paid_course(student, course):
    decision = can_user_access_course(student, course)
    assert not decision.allowed and decision.reason == "subscription_required"


def test_lapsed_only_reports_expired(student, course, single_a):
    make_subscription(student, single_a, starts_in_days=-40, ends_in_days=-1, payment_reference="x")
    assert can_user_access_course(student, course).reason == "subscription_expired"


def test_free_course_needs_no_subscription(student, free_course):
    assert allowed(student, free_course)


def test_instructor_owner_keeps_access(instructor, course):
    assert allowed(instructor, course)


def test_one_users_subscriptions_never_leak_to_another(student, course_b, all_access):
    make_subscription(student, all_access, payment_reference="aa")
    other = make_student(email="other-user@test.local")
    assert allowed(student, course_b)
    assert not allowed(other, course_b)
    assert course_b.id not in accessible_course_ids(other)


# --------------------------------------------------------------------------- #
# Cache behaviour
# --------------------------------------------------------------------------- #
def test_activation_is_visible_immediately(student, course_b, all_access):
    assert not allowed(student, course_b)  # warm a cached deny
    activate_subscription(user=student, plan=all_access, payment_reference="aa")
    assert allowed(student, course_b)


def test_cached_allow_ends_with_the_covering_subscription(student, course, course_b, single_a, single_b):
    """A long subscription that does not cover the course must not stretch the
    cache lifetime of an answer granted by a short one."""
    make_subscription(student, single_b, ends_in_days=300, payment_reference="b")
    sub_a = make_subscription(student, single_a, payment_reference="a")
    now = timezone.now()
    sub_a.end_date = now + timedelta(seconds=10)
    sub_a.save(update_fields=["end_date"])
    with freeze_time(now) as clock:
        assert allowed(student, course)
        clock.tick(timedelta(seconds=11))
        assert not allowed(student, course)
        assert allowed(student, course_b)


# --------------------------------------------------------------------------- #
# Through the API
# --------------------------------------------------------------------------- #
def test_api_access_and_catalogue_reflect_all_subscriptions(
    auth_client, student, course, course_b, all_access, single_a, section, lesson
):
    make_subscription(student, all_access, ends_in_days=30, payment_reference="aa")
    activate_subscription(user=student, plan=single_a, payment_reference="a")
    client = auth_client(student)

    assert client.get(f"/api/v1/courses/{course_b.slug}/access/").json()["allowed"] is True
    assert client.get(f"/api/v1/courses/{course.slug}/access/").json()["allowed"] is True
    watch = client.get(f"/api/v1/lessons/{lesson.id}/watch/")
    assert watch.status_code == 200 and watch.json()["access"]["allowed"] is True

    rows = {row["slug"]: row for row in client.get("/api/v1/courses/").json()["results"]}
    assert rows[course_b.slug]["is_accessible"] is True
    assert rows[course.slug]["is_accessible"] is True


def test_reads_cache_entries_written_before_expires_at_existed(student, course, single_a):
    """Entries cached by the previous release (3-tuples) live up to 60s after a
    deploy; reading one must not crash."""
    from django.core.cache import cache

    from apps.subscriptions.services import _course_decision_key, entitlement_generation

    make_subscription(student, single_a, payment_reference="a")
    key = _course_decision_key(student.pk, course.pk, entitlement_generation(student.pk))
    cache.set(key, (True, "active_subscription", "old entry"), 60)
    decision = can_user_access_course(student, course)
    assert decision.allowed and decision.expires_at is None
