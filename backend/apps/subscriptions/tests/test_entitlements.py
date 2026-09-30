"""Subscription + entitlement tests.

These are the tests that matter most: they prove that access is decided by the
server from database state, that an expired-but-ACTIVE row grants nothing, and
that the same rule applies on every content endpoint.
"""

from __future__ import annotations

import pytest
from django.utils import timezone

from apps.subscriptions.services import (
    AccessDecision,
    accessible_course_ids,
    can_user_access_course,
    can_user_access_lesson,
    can_user_access_video,
    get_active_subscription,
    invalidate_entitlement_cache,
    has_active_subscription,
)

pytestmark = pytest.mark.django_db


class TestActiveSubscription:
    def test_active_subscription_is_found(self, student, active_subscription):
        assert get_active_subscription(student) == active_subscription
        assert has_active_subscription(student) is True

    def test_active_subscription_grants_course_access(
        self, student, course, active_subscription
    ):
        decision = can_user_access_course(student, course)
        assert decision.allowed is True
        assert decision.reason == "active_subscription"

    def test_course_not_in_plan_is_denied(
        self, student, active_subscription, instructor
    ):
        """An active subscription only unlocks its plan's courses."""
        from decimal import Decimal

        from apps.courses.models import Course

        other = Course.objects.create(
            title="Unlisted Course",
            slug="unlisted-course",
            description="Not in the plan.",
            instructor=instructor,
            price=Decimal("999.00"),
            status="published",
            published_at=timezone.now(),
        )
        decision = can_user_access_course(student, other)
        assert decision.allowed is False
        assert decision.reason == "not_in_plan"

    def test_all_access_plan_unlocks_any_published_course(
        self, student, course, all_access_plan, instructor
    ):
        from datetime import timedelta

        from apps.subscriptions.models import Subscription

        Subscription.objects.create(
            user=student,
            plan=all_access_plan,
            status="active",
            start_date=timezone.now() - timedelta(days=1),
            end_date=timezone.now() + timedelta(days=30),
        )
        invalidate_entitlement_cache(student)
        assert can_user_access_course(student, course).allowed is True


class TestExpiredSubscription:
    def test_expired_dates_deny_access_even_when_status_is_active(
        self, student, course, expired_subscription
    ):
        """The core invariant: a stale ``status`` column must never grant access."""
        assert expired_subscription.status == "active"
        assert expired_subscription.is_currently_active is False

        decision = can_user_access_course(student, course)
        assert decision.allowed is False
        assert decision.reason == "subscription_expired"

    def test_expired_subscription_denies_lesson_and_video(
        self, student, lesson, expired_subscription
    ):
        assert can_user_access_lesson(student, lesson).allowed is False
        assert can_user_access_video(student, lesson.video).allowed is False

    def test_get_active_subscription_ignores_lapsed_rows(
        self, student, expired_subscription
    ):
        assert get_active_subscription(student) is None

    def test_future_dated_subscription_grants_nothing(self, student, course, plan):
        from datetime import timedelta

        from apps.subscriptions.models import Subscription

        Subscription.objects.create(
            user=student,
            plan=plan,
            status="active",
            start_date=timezone.now() + timedelta(days=5),
            end_date=timezone.now() + timedelta(days=40),
        )
        invalidate_entitlement_cache(student)
        assert can_user_access_course(student, course).allowed is False


class TestCancelledAndPending:
    def test_cancelled_subscription_denies_access(self, student, course, plan):
        from datetime import timedelta

        from apps.subscriptions.models import Subscription

        Subscription.objects.create(
            user=student,
            plan=plan,
            status="cancelled",
            start_date=timezone.now() - timedelta(days=1),
            end_date=timezone.now() + timedelta(days=30),
        )
        invalidate_entitlement_cache(student)
        assert can_user_access_course(student, course).allowed is False

    def test_pending_subscription_denies_access(self, student, course, plan):
        from apps.subscriptions.models import Subscription

        Subscription.objects.create(user=student, plan=plan, status="pending")
        invalidate_entitlement_cache(student)
        decision = can_user_access_course(student, course)
        assert decision.allowed is False
        assert decision.reason == "subscription_expired"  # has history -> "renew"

    def test_failed_subscription_denies_access(self, student, course, plan):
        from apps.subscriptions.models import Subscription

        Subscription.objects.create(user=student, plan=plan, status="failed")
        invalidate_entitlement_cache(student)
        assert can_user_access_course(student, course).allowed is False


class TestNoSubscription:
    def test_student_without_subscription_is_denied(self, student, course):
        decision = can_user_access_course(student, course)
        assert decision.allowed is False
        assert decision.reason == "subscription_required"

    def test_anonymous_user_is_denied(self, course):
        from django.contrib.auth.models import AnonymousUser

        decision = can_user_access_course(AnonymousUser(), course)
        assert decision.allowed is False
        assert decision.reason == "authentication_required"

    def test_none_user_is_denied(self, course):
        assert can_user_access_course(None, course).allowed is False

    def test_denied_decision_is_falsy(self, student, course):
        """``if decision:`` must behave like a boolean for defensive callers."""
        assert bool(can_user_access_course(student, course)) is False
        assert bool(AccessDecision(True, "x")) is True


class TestFreeAndPreview:
    def test_free_course_is_open_to_any_student(self, student, free_course):
        decision = can_user_access_course(student, free_course)
        assert decision.allowed is True
        assert decision.reason == "free_course"

    def test_free_course_is_listed_for_anonymous_users(self, db, free_course):
        assert free_course.id in accessible_course_ids(None)

    def test_preview_lesson_is_open_without_subscription(self, student, preview_lesson):
        decision = can_user_access_lesson(student, preview_lesson)
        assert decision.allowed is True
        assert decision.reason == "preview_lesson"

    def test_preview_lesson_visible_to_anonymous(self, preview_lesson):
        from django.contrib.auth.models import AnonymousUser

        assert can_user_access_lesson(AnonymousUser(), preview_lesson).allowed is True

    def test_non_preview_lesson_is_not_visible_to_anonymous(self, lesson):
        from django.contrib.auth.models import AnonymousUser

        decision = can_user_access_lesson(AnonymousUser(), lesson)
        assert decision.allowed is False
        assert decision.reason == "authentication_required"


class TestDraftContent:
    def test_draft_course_denies_students_even_with_subscription(
        self, student, draft_course, all_access_plan
    ):
        from datetime import timedelta

        from apps.subscriptions.models import Subscription

        Subscription.objects.create(
            user=student,
            plan=all_access_plan,
            status="active",
            start_date=timezone.now() - timedelta(days=1),
            end_date=timezone.now() + timedelta(days=30),
        )
        invalidate_entitlement_cache(student)
        decision = can_user_access_course(student, draft_course)
        assert decision.allowed is False
        assert decision.reason == "not_published"

    def test_draft_course_visible_to_admin(self, admin_user, draft_course):
        assert can_user_access_course(admin_user, draft_course).allowed is True


class TestInstructorOwnership:
    def test_owning_instructor_can_access_draft(self, instructor, draft_course):
        decision = can_user_access_course(instructor, draft_course)
        assert decision.allowed is True
        assert decision.reason == "instructor"

    def test_other_instructor_cannot_access_draft(self, draft_course, db):
        from django.contrib.auth import get_user_model

        other = get_user_model().objects.create_instructor(
            email="other-instructor@test.local", password="Pass123456!", name="Other"
        )
        decision = can_user_access_course(other, draft_course)
        assert decision.allowed is False


class TestBulkAccessHelper:
    def test_accessible_course_ids_includes_free_and_subscribed(
        self, student, course, free_course, active_subscription
    ):
        ids = accessible_course_ids(student)
        assert course.id in ids
        assert free_course.id in ids

    def test_accessible_course_ids_excludes_unsubscribed(
        self, student, course, free_course
    ):
        ids = accessible_course_ids(student)
        assert course.id not in ids
        assert free_course.id in ids

    def test_accessible_course_ids_for_admin_covers_everything(
        self, admin_user, course, draft_course
    ):
        ids = accessible_course_ids(admin_user)
        assert course.id in ids and draft_course.id in ids

    def test_cache_invalidation_reflects_immediate_change(
        self, student, course, active_subscription
    ):
        """An entitlement decision must never outlive the data it was based on."""
        from apps.subscriptions.models import Subscription
        from apps.subscriptions.services import get_active_subscription

        assert can_user_access_course(student, course).allowed is True

        # Delete the subscription outright, then clear the cache.  The second
        # call must re-query rather than serve the cached "allowed" answer.
        Subscription.objects.filter(pk=active_subscription.pk).delete()
        invalidate_entitlement_cache(student)

        assert get_active_subscription(student) is None
        assert can_user_access_course(student, course).allowed is False


class TestEntitlementEndpoints:
    """The HTTP layer must agree with the service layer."""

    def test_course_access_endpoint_denies_without_subscription(
        self, jwt_client, student, course
    ):
        response = jwt_client(student).get(f"/api/v1/courses/{course.slug}/access/")
        assert response.status_code == 200
        assert response.data["allowed"] is False
        assert response.data["reason"] == "subscription_required"

    def test_course_access_endpoint_allows_with_subscription(
        self, jwt_client, student, course, active_subscription
    ):
        response = jwt_client(student).get(f"/api/v1/courses/{course.slug}/access/")
        assert response.data["allowed"] is True

    def test_course_detail_marks_lessons_locked(
        self, jwt_client, student, course, lesson
    ):
        response = jwt_client(student).get(f"/api/v1/courses/{course.slug}/")
        assert response.status_code == 200
        lessons = [
            lesson_row
            for section in response.data["sections"]
            for lesson_row in section["lessons"]
        ]
        assert len(lessons) == 1
        assert lessons[0]["is_locked"] is True

    def test_course_detail_marks_lessons_unlocked_with_subscription(
        self, jwt_client, student, course, lesson, active_subscription
    ):
        response = jwt_client(student).get(f"/api/v1/courses/{course.slug}/")
        lessons = [
            row for section in response.data["sections"] for row in section["lessons"]
        ]
        assert lessons[0]["is_locked"] is False

    def test_course_detail_never_exposes_video_identifiers(
        self, jwt_client, student, course, lesson
    ):
        """Locked or not, the course payload must not carry playback data."""
        response = jwt_client(student).get(f"/api/v1/courses/{course.slug}/")
        body = str(response.data)
        assert "cloudflare_video_id" not in body
        assert lesson.video.cloudflare_video_id not in body

    def test_preview_lesson_is_not_locked_without_subscription(
        self, jwt_client, student, course, preview_lesson
    ):
        response = jwt_client(student).get(f"/api/v1/courses/{course.slug}/")
        lessons = [
            row for section in response.data["sections"] for row in section["lessons"]
        ]
        preview = next(row for row in lessons if row["is_preview"])
        assert preview["is_locked"] is False

    def test_my_subscription_endpoint_reports_no_active_subscription(
        self, jwt_client, student
    ):
        response = jwt_client(student).get("/api/v1/subscriptions/me/")
        assert response.status_code == 200
        assert response.data["has_active_subscription"] is False
        assert response.data["active"] is None

    def test_my_subscription_endpoint_reports_active_subscription(
        self, jwt_client, student, active_subscription
    ):
        response = jwt_client(student).get("/api/v1/subscriptions/me/")
        assert response.data["has_active_subscription"] is True
        assert response.data["active"]["status"] == "active"
        assert response.data["active"]["days_remaining"] > 0

    def test_cancel_subscription_ends_future_access_immediately(
        self, jwt_client, student, course, active_subscription
    ):
        response = jwt_client(student).post(
            "/api/v1/subscriptions/me/cancel/", {"immediate": True}, format="json"
        )
        assert response.status_code == 200
        active_subscription.refresh_from_db()
        assert active_subscription.status == "cancelled"
        assert can_user_access_course(student, course).allowed is False

    def test_cancel_without_subscription_returns_400(self, jwt_client, student):
        response = jwt_client(student).post(
            "/api/v1/subscriptions/me/cancel/", {}, format="json"
        )
        assert response.status_code == 400
        assert response.data["error"]["code"] == "no_active_subscription"

    def test_activated_plan_extends_rather_than_replaces(
        self, student, plan, active_subscription
    ):
        """Renewing early must not shorten the remaining term."""
        from apps.subscriptions.services_lifecycle import activate_subscription

        original_end = active_subscription.end_date
        renewed = activate_subscription(
            user=student, plan=plan, payment_reference="pay_renew"
        )

        assert renewed.pk == active_subscription.pk
        assert renewed.end_date == original_end + timezone.timedelta(
            days=plan.duration_days
        )

    def test_expire_lapsed_subscriptions_flips_status(self, expired_subscription):
        from apps.subscriptions.services_lifecycle import expire_lapsed_subscriptions

        count = expire_lapsed_subscriptions()
        expired_subscription.refresh_from_db()
        assert count == 1
        assert expired_subscription.status == "expired"
