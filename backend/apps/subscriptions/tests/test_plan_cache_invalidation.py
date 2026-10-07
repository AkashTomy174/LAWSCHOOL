"""Plan coverage changes must reach cached entitlement answers immediately.

Regression: entitlement decisions are cached for 60s per (user, course), and
nothing invalidated them when a plan changed.  Removing a course from a plan left
every subscriber able to watch it for up to a minute (adding one stayed locked).
Each test warms the cache first, so it fails if the change is served stale.
"""

from __future__ import annotations

import pytest

from apps.subscriptions.services import accessible_course_ids, can_user_access_course
from conftest import make_subscription


@pytest.fixture
def warm(student, course):
    """Assert-and-cache the current answer, so a stale cache would be hit next."""

    def _warm(expected: bool):
        for _ in range(2):  # second call is served from the cache
            assert can_user_access_course(student, course).allowed is expected
            assert (course.id in accessible_course_ids(student)) is expected

    return _warm


def _allowed(student, course) -> bool:
    return can_user_access_course(student, course).allowed


def test_removing_a_course_from_a_plan_revokes_access_immediately(
    student, course, plan, active_subscription, warm
):
    warm(True)
    plan.courses.remove(course)
    assert not _allowed(student, course)
    assert course.id not in accessible_course_ids(student)


def test_removal_from_the_course_side_is_seen_too(
    student, course, plan, active_subscription, warm
):
    warm(True)
    course.plans.remove(plan)
    assert not _allowed(student, course)


def test_clearing_a_plans_courses_revokes_access(
    student, course, plan, active_subscription, warm
):
    warm(True)
    plan.courses.clear()
    assert not _allowed(student, course)


def test_adding_a_course_grants_access_immediately(
    student, course, plan, active_subscription, warm
):
    plan.courses.remove(course)
    warm(False)
    plan.courses.add(course)
    assert _allowed(student, course)
    assert course.id in accessible_course_ids(student)


def test_turning_off_all_access_revokes_uncovered_courses(
    student, course, all_access_plan, warm
):
    make_subscription(student, all_access_plan, payment_reference="pay_all")
    warm(True)
    all_access_plan.is_all_access = False
    all_access_plan.save()
    assert not _allowed(student, course)


def test_admin_api_plan_edit_revokes_access_immediately(
    auth_client, admin_user, student, course, plan, active_subscription, warm
):
    """The real admin path: PATCH the plan's course list over the API."""
    warm(True)
    response = auth_client(admin_user).patch(
        f"/api/v1/subscriptions/plans/{plan.slug}/", {"courses": []}, format="json"
    )
    assert response.status_code == 200, response.data
    assert not _allowed(student, course)
    access = auth_client(student).get(f"/api/v1/courses/{course.slug}/access/")
    assert access.json()["allowed"] is False
