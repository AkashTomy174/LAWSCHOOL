"""Shared pytest fixtures.

Fixtures build the *minimal* object graph each test needs, and every factory is
explicit about the fields that matter for authorization (role, subscription
window, course unlock rule) so the security tests are easy to read.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.constants import CourseStatus, LessonStatus, SubscriptionStatus

User = get_user_model()


# --------------------------------------------------------------------------- #
# Clients
# --------------------------------------------------------------------------- #
@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def auth_client():
    """Factory: ``auth_client(user)`` -> an APIClient authenticated as that user."""

    def _make(user) -> APIClient:
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    return _make


@pytest.fixture
def jwt_client():
    """Factory returning a client with a real JWT (exercises the auth stack)."""

    def _make(user) -> APIClient:
        from rest_framework_simplejwt.tokens import RefreshToken

        client = APIClient()
        token = RefreshToken.for_user(user)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
        return client

    return _make


# --------------------------------------------------------------------------- #
# Users
# --------------------------------------------------------------------------- #
@pytest.fixture
def student(db):
    return User.objects.create_user(
        email="student@test.local", password="StudentPass123!", name="Test Student"
    )


@pytest.fixture
def other_student(db):
    return User.objects.create_user(
        email="other@test.local", password="StudentPass123!", name="Other Student"
    )


@pytest.fixture
def instructor(db):
    return User.objects.create_instructor(
        email="instructor@test.local", password="Instructor123!", name="Test Instructor"
    )


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(
        email="admin@test.local", password="AdminPass123!", name="Test Admin"
    )


# --------------------------------------------------------------------------- #
# Courses
# --------------------------------------------------------------------------- #
@pytest.fixture
def course(db, instructor):
    from apps.courses.models import Course

    return Course.objects.create(
        title="Constitutional Law",
        slug="constitutional-law",
        description="A comprehensive course on the Indian Constitution.",
        summary="Master the Constitution.",
        instructor=instructor,
        price=Decimal("1999.00"),
        status=CourseStatus.PUBLISHED,
        published_at=timezone.now(),
    )


@pytest.fixture
def free_course(db, instructor):
    from apps.courses.models import Course

    return Course.objects.create(
        title="Free Legal Reasoning",
        slug="free-legal-reasoning",
        description="An open introductory course.",
        instructor=instructor,
        status=CourseStatus.PUBLISHED,
        unlock_rule="free",
        published_at=timezone.now(),
    )


@pytest.fixture
def draft_course(db, instructor):
    from apps.courses.models import Course

    return Course.objects.create(
        title="Draft Course",
        slug="draft-course",
        description="Not published yet.",
        instructor=instructor,
        status=CourseStatus.DRAFT,
    )


@pytest.fixture
def section(db, course):
    from apps.courses.models import Section

    return Section.objects.create(course=course, title="Foundations", ordering=1)


# --------------------------------------------------------------------------- #
# Videos & lessons
# --------------------------------------------------------------------------- #
@pytest.fixture
def video(db):
    from apps.videos.models import Video

    return Video.objects.create(
        title="The Preamble",
        cloudflare_video_id="cf-test-video-0001",
        status="ready",
        duration_seconds=600,
        require_signed_urls=True,
    )


@pytest.fixture
def lesson(db, section, video):
    from apps.courses.models import Lesson

    lesson = Lesson.objects.create(
        section=section,
        title="The Preamble",
        video=video,
        duration_seconds=600,
        ordering=1,
        status=LessonStatus.PUBLISHED,
    )
    return lesson


@pytest.fixture
def preview_lesson(db, section):
    """Publicly watchable lesson (no subscription needed)."""
    from apps.courses.models import Lesson
    from apps.videos.models import Video

    video = Video.objects.create(
        title="Preview: What is Law?",
        cloudflare_video_id="cf-test-preview-0001",
        status="ready",
        duration_seconds=300,
    )
    return Lesson.objects.create(
        section=section,
        title="What is Law?",
        video=video,
        duration_seconds=300,
        ordering=2,
        is_preview=True,
        status=LessonStatus.PUBLISHED,
    )


# --------------------------------------------------------------------------- #
# Plans & subscriptions
# --------------------------------------------------------------------------- #
# These helpers create rows directly, without going through other fixtures.  That
# matters: several tests mutate a student's subscription, and indirect fixture
# dependencies could silently build a *second* subscription and mask the bug.
def make_student(email: str = "student@test.local", name: str = "Test Student"):
    """Create a student account directly (no fixtures, no indirection)."""
    return User.objects.create_user(email=email, password="StudentPass123!", name=name)


def make_plan(
    *, name: str = "Foundations", slug: str = "foundations", courses=(), **kwargs
):
    """Create a plan, optionally scoped to specific courses."""
    from apps.subscriptions.models import Plan

    plan = Plan.objects.create(
        name=name,
        slug=slug,
        description="Test plan.",
        price=kwargs.pop("price", Decimal("1999.00")),
        duration_days=kwargs.pop("duration_days", 180),
        **kwargs,
    )
    if courses:
        plan.courses.set(courses)
    return plan


def make_subscription(
    user,
    plan,
    *,
    status: str = SubscriptionStatus.ACTIVE,
    starts_in_days: int = -1,
    ends_in_days: int = 180,
    payment_reference: str = "pay_test",
):
    """Create a subscription with an explicit, readable validity window."""
    from apps.subscriptions.models import Subscription
    from apps.subscriptions.services import invalidate_entitlement_cache

    now = timezone.now()
    subscription = Subscription.objects.create(
        user=user,
        plan=plan,
        status=status,
        start_date=now + timedelta(days=starts_in_days),
        end_date=now + timedelta(days=ends_in_days),
        payment_reference=payment_reference,
    )
    # Entitlement answers are cached per user; make fresh state immediately visible.
    invalidate_entitlement_cache(user)
    return subscription


@pytest.fixture
def plan(db, course):
    from apps.subscriptions.models import Plan

    plan = Plan.objects.create(
        name="Foundations",
        slug="foundations",
        description="Access to foundational courses.",
        price=Decimal("1999.00"),
        duration_days=180,
    )
    plan.courses.add(course)
    return plan


@pytest.fixture
def all_access_plan(db, course):
    from apps.subscriptions.models import Plan

    return Plan.objects.create(
        name="All Access",
        slug="all-access",
        description="Everything.",
        price=Decimal("4999.00"),
        duration_days=365,
        is_all_access=True,
    )


@pytest.fixture
def active_subscription(db, student, plan):
    return make_subscription(student, plan, payment_reference="pay_test_active")


@pytest.fixture
def expired_subscription(db, student, plan):
    """Status reads ACTIVE but the dates are in the past -- the stale-data case."""
    return make_subscription(
        student,
        plan,
        status=SubscriptionStatus.ACTIVE,
        starts_in_days=-200,
        ends_in_days=-20,
        payment_reference="pay_test_expired",
    )


# --------------------------------------------------------------------------- #
# Quiz
# --------------------------------------------------------------------------- #
@pytest.fixture
def subject(db):
    from apps.quizzes.models import Subject

    return Subject.objects.create(name="Constitutional Law", slug="constitutional-law")


@pytest.fixture
def quiz(db, course, subject):
    from apps.quizzes.models import Option, Question, Quiz, QuizSectionRule

    quiz = Quiz.objects.create(
        course=course,
        title="Module 1 Quiz",
        pass_percentage=60,
        max_attempts=3,
        is_published=True,
    )
    question = Question.objects.create(text="Article 32 deals with?", marks=2)
    question.subjects.add(subject)
    Option.objects.create(question=question, text="Writs", is_correct=True, ordering=1)
    Option.objects.create(question=question, text="Taxes", is_correct=False, ordering=2)
    QuizSectionRule.objects.create(
        quiz=quiz, subject=subject, question_count=1, marks_per_question=2
    )
    return quiz
