"""Regression tests for the October 2026 audit findings.

Each test pins one fixed bug; the docstring names what used to go wrong.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.core.constants import (
    CourseStatus,
    LessonStatus,
    PaymentStatus,
    SubscriptionStatus,
)
from conftest import make_subscription


# --------------------------------------------------------------------------- #
# Draft content visibility
# --------------------------------------------------------------------------- #
class TestDraftVisibility:
    def test_anonymous_cannot_read_draft_course(self, api_client, draft_course):
        """course_detail() had no status filter, so drafts were public."""
        response = api_client.get(f"/api/v1/courses/{draft_course.slug}/")
        assert response.status_code == 404

    def test_student_cannot_probe_draft_course_endpoints(
        self, auth_client, student, draft_course
    ):
        client = auth_client(student)
        slug = draft_course.slug
        for url in (
            f"/api/v1/courses/{slug}/lessons/",
            f"/api/v1/courses/{slug}/access/",
            f"/api/v1/progress/course/{slug}/",
        ):
            assert client.get(url).status_code == 404, url

    def test_instructor_still_sees_drafts(self, auth_client, instructor, draft_course):
        response = auth_client(instructor).get(f"/api/v1/courses/{draft_course.slug}/")
        assert response.status_code == 200
        assert response.data["title"] == draft_course.title

    def test_section_of_only_draft_lessons_lists_nothing(
        self, auth_client, student, course
    ):
        """An empty prefetched list fell back to section.lessons.all() (drafts)."""
        from apps.courses.models import Lesson, Section

        section = Section.objects.create(
            course=course, title="Coming soon", ordering=5, is_published=True
        )
        from apps.videos.models import Video

        Lesson.objects.create(
            section=section,
            title="Secret draft",
            ordering=1,
            status=LessonStatus.DRAFT,
            video=Video.objects.create(title="Draft", cloudflare_video_id="cf-draft"),
        )
        response = auth_client(student).get(f"/api/v1/courses/{course.slug}/lessons/")
        assert response.status_code == 200
        titles = [lesson["title"] for lesson in response.data["lessons"]]
        assert "Secret draft" not in titles

    def test_preview_lesson_of_draft_course_is_not_watchable(
        self, api_client, auth_client, student, course, preview_lesson
    ):
        from apps.subscriptions.services import can_user_access_lesson

        course.status = CourseStatus.DRAFT
        course.save(update_fields=["status"])
        preview_lesson.refresh_from_db()

        from django.contrib.auth.models import AnonymousUser

        assert not can_user_access_lesson(AnonymousUser(), preview_lesson)
        assert not can_user_access_lesson(student, preview_lesson)
        response = auth_client(student).get(
            f"/api/v1/lessons/{preview_lesson.id}/watch/"
        )
        assert response.status_code == 404

    def test_unpublished_quiz_progress_is_404(self, auth_client, student, quiz):
        quiz.is_published = False
        quiz.save(update_fields=["is_published"])
        response = auth_client(student).get(f"/api/v1/quizzes/{quiz.id}/progress/")
        assert response.status_code == 404

    def test_live_classes_of_draft_course_are_not_listed(
        self, auth_client, student, draft_course, instructor
    ):
        from apps.live.models import LiveClass

        LiveClass.objects.create(
            course=draft_course,
            title="Hidden session",
            scheduled_start=timezone.now() + timedelta(days=1),
            duration_minutes=60,
            meeting_url="https://meet.example.com/x",
            instructor=instructor,
            is_published=True,
        )
        response = auth_client(student).get("/api/v1/live-classes/")
        assert response.status_code == 200
        rows = response.data if isinstance(response.data, list) else response.data["results"]
        assert all(row["title"] != "Hidden session" for row in rows)


# --------------------------------------------------------------------------- #
# Watch endpoint no longer mints tokens
# --------------------------------------------------------------------------- #
class TestWatchEndpoint:
    def test_watch_returns_video_uid_without_minting(
        self, jwt_client, student, lesson, active_subscription
    ):
        from apps.videos.models import PlaybackSession

        response = jwt_client(student).get(f"/api/v1/lessons/{lesson.id}/watch/")
        assert response.status_code == 200
        assert response.data["playback"]["video_uid"] == str(lesson.video.playback_uid)
        assert "token" not in response.data["playback"]
        assert "hls_url" not in response.data["playback"]
        assert not PlaybackSession.objects.exists()


# --------------------------------------------------------------------------- #
# Refunds
# --------------------------------------------------------------------------- #
def _captured_payment(user, plan, subscription, suffix):
    from apps.payments.models import Payment

    return Payment.objects.create(
        user=user,
        plan=plan,
        subscription=subscription,
        provider_order_id=f"order_{suffix}",
        provider_payment_id=f"pay_{suffix}",
        amount=plan.price,
        status=PaymentStatus.CAPTURED,
    )


def _refund(payment_id, refund_id, amount):
    from apps.payments.services import handle_payment_refunded

    return handle_payment_refunded(
        {
            "payload": {
                "refund": {
                    "entity": {"id": refund_id, "payment_id": payment_id, "amount": amount}
                }
            }
        }
    )


class TestRefunds:
    def test_refunding_a_renewal_keeps_the_other_paid_term(self, student, plan):
        """Refunding one stacked payment used to cancel the whole subscription."""
        subscription = make_subscription(student, plan, ends_in_days=2 * 180)
        _captured_payment(student, plan, subscription, "first")
        second = _captured_payment(student, plan, subscription, "second")

        _refund(second.provider_payment_id, "rfnd_a", second.amount_paise)

        subscription.refresh_from_db()
        assert subscription.status == SubscriptionStatus.ACTIVE
        remaining = subscription.end_date - timezone.now()
        assert timedelta(days=179) < remaining <= timedelta(days=180)

    def test_partial_refunds_adding_up_count_as_full(self, student, plan):
        subscription = make_subscription(student, plan)
        payment = _captured_payment(student, plan, subscription, "parts")
        half = payment.amount_paise // 2

        assert _refund(payment.provider_payment_id, "rfnd_1", half)["partial_refund"]
        # A redelivery of the same refund must not be double-counted.
        assert _refund(payment.provider_payment_id, "rfnd_1", half)["partial_refund"]
        _refund(payment.provider_payment_id, "rfnd_2", payment.amount_paise - half)

        payment.refresh_from_db()
        subscription.refresh_from_db()
        assert payment.status == PaymentStatus.REFUNDED
        assert subscription.status == SubscriptionStatus.CANCELLED


# --------------------------------------------------------------------------- #
# Admin endpoints
# --------------------------------------------------------------------------- #
class TestAdminEndpoints:
    def test_admin_can_correct_a_subscription(self, auth_client, admin_user, student, plan):
        """Every field was read-only, so PATCH silently changed nothing."""
        subscription = make_subscription(student, plan)
        response = auth_client(admin_user).patch(
            f"/api/v1/subscriptions/{subscription.id}/",
            {"status": SubscriptionStatus.CANCELLED},
            format="json",
        )
        assert response.status_code == 200
        assert response.data["status"] == SubscriptionStatus.CANCELLED
        assert "user_email" in response.data
        subscription.refresh_from_db()
        assert subscription.status == SubscriptionStatus.CANCELLED

    def test_deleting_a_plan_in_use_is_409(self, auth_client, admin_user, student, plan):
        make_subscription(student, plan)
        response = auth_client(admin_user).delete(
            f"/api/v1/subscriptions/plans/{plan.slug}/"
        )
        assert response.status_code == 409
        assert response.data["error"]["code"] == "plan_in_use"


# --------------------------------------------------------------------------- #
# Rate limits & leaderboard
# --------------------------------------------------------------------------- #
class TestRateLimitsAndRanking:
    def test_playback_budget_exhaustion_is_429(self, student):
        from apps.core.exceptions import RateLimitedError
        from apps.videos.services import _enforce_rate_limit

        _enforce_rate_limit(student, scope="t", budget=1, window=600)
        with pytest.raises(RateLimitedError) as exc:
            _enforce_rate_limit(student, scope="t", budget=1, window=600)
        assert exc.value.status_code == 429

    def test_rank_ignores_instructors_and_inactive_users(
        self, student, other_student, instructor
    ):
        from apps.leaderboard.models import LeaderboardEntry, user_rank

        LeaderboardEntry.objects.create(user=student, total_score=10)
        LeaderboardEntry.objects.create(user=instructor, total_score=999)
        other_student.is_active = False
        other_student.save(update_fields=["is_active"])
        LeaderboardEntry.objects.create(user=other_student, total_score=500)

        student.refresh_from_db()
        assert user_rank(student) == 1

    def test_refresh_has_its_own_throttle_scope(self):
        from apps.users.views import LoginView, RefreshView

        assert RefreshView.throttle_scope == "token_refresh"
        assert LoginView.throttle_scope == "auth"

    def test_single_num_proxies_setting(self, settings):
        assert settings.REST_FRAMEWORK["NUM_PROXIES"] == settings.NUM_PROXIES

