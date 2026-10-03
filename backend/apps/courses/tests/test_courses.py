"""Course / section / lesson API tests.

These cover the *authoring* and *presentation* surfaces:

* the public catalogue never exposes drafts,
* a locked lesson never leaks playback data,
* instructors are confined to their own courses (object-level authorization),
* ordering and hierarchy invariants are enforced,
* list endpoints do not degrade into N+1 queries.

The entitlement rule itself is tested in ``apps/subscriptions/tests``.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.core.constants import CourseStatus, LessonStatus
from apps.courses.models import Course, Lesson, Section

pytestmark = pytest.mark.django_db


def detail_url(slug: str) -> str:
    return f"/api/v1/courses/{slug}/"


def lessons_url(slug: str) -> str:
    return f"/api/v1/courses/{slug}/lessons/"


def access_url(slug: str) -> str:
    return f"/api/v1/courses/{slug}/access/"


# --------------------------------------------------------------------------- #
# Catalogue
# --------------------------------------------------------------------------- #
class TestCourseCatalogue:
    def test_list_is_public(self, api_client, course):
        response = api_client.get("/api/v1/courses/")
        assert response.status_code == 200
        # Paginated envelope: {"count": n, "results": [...]}.
        assert response.data["count"] >= 1

    def test_drafts_are_hidden_from_the_catalogue(
        self, api_client, course, draft_course
    ):
        response = api_client.get("/api/v1/courses/")
        slugs = [item["slug"] for item in response.data["results"]]
        assert course.slug in slugs
        assert draft_course.slug not in slugs

    def test_anonymous_detail_of_a_published_course_is_readable(
        self, api_client, course
    ):
        response = api_client.get(detail_url(course.slug))
        assert response.status_code == 200
        # Browsable, but not accessible: the lock is what protects content.
        assert response.data["is_accessible"] is False

    def test_owner_can_see_draft_detail(self, auth_client, draft_course):
        response = auth_client(draft_course.instructor).get(
            detail_url(draft_course.slug)
        )
        assert response.status_code == 200
        assert response.data["slug"] == draft_course.slug

    def test_unknown_slug_returns_404(self, api_client):
        response = api_client.get(detail_url("does-not-exist"))
        assert response.status_code == 404
        assert response.data["error"]["code"] == "not_found"

    def test_search_filters_results(self, api_client, course, free_course):
        response = api_client.get("/api/v1/courses/", {"search": "Constitutional"})
        assert response.status_code == 200
        titles = [item["title"] for item in response.data["results"]]
        assert "Constitutional Law" in titles
        assert "Free Legal Reasoning" not in titles

    def test_results_are_paginated(self, api_client, instructor):
        for index in range(25):
            Course.objects.create(
                title=f"Bulk Course {index}",
                slug=f"bulk-course-{index}",
                description="Generated for the pagination test.",
                instructor=instructor,
                status=CourseStatus.PUBLISHED,
            )
        response = api_client.get("/api/v1/courses/")
        assert response.status_code == 200
        assert response.data["count"] == 25
        # Default PAGE_SIZE is 20.
        assert len(response.data["results"]) == 20
        assert response.data["next"] is not None


# --------------------------------------------------------------------------- #
# Course detail & lesson list -- no video leakage
# --------------------------------------------------------------------------- #
class TestCourseDetailPayload:
    def test_detail_includes_sections_and_lessons(self, api_client, course, lesson):
        response = api_client.get(detail_url(course.slug))
        assert response.status_code == 200
        sections = response.data["sections"]
        assert len(sections) == 1
        assert sections[0]["lessons"][0]["title"] == lesson.title

    def test_detail_never_exposes_cloudflare_identifiers(
        self, api_client, course, lesson
    ):
        """The whole point of the video architecture: metadata only."""
        body = api_client.get(detail_url(course.slug)).content.decode()
        assert lesson.video.cloudflare_video_id not in body
        assert "cloudflarestream.com" not in body
        assert "manifest/video.m3u8" not in body

    def test_lesson_list_never_exposes_playback_data(
        self, auth_client, student, course, lesson
    ):
        """Even the authorized lesson list carries flags, not playback credentials."""
        response = auth_client(student).get(lessons_url(course.slug))
        body = response.content.decode()
        assert lesson.video.cloudflare_video_id not in body
        assert "token" not in response.data["lessons"][0]

    def test_draft_lessons_are_omitted_from_the_syllabus(
        self, api_client, course, section
    ):
        from apps.videos.models import Video

        video = Video.objects.create(
            title="Unpublished",
            cloudflare_video_id="cf-hidden-0001",
            status="ready",
            duration_seconds=100,
        )
        Lesson.objects.create(
            section=section,
            title="Secret lesson",
            video=video,
            ordering=9,
            status=LessonStatus.DRAFT,
        )
        response = api_client.get(detail_url(course.slug))
        titles = [
            lesson["title"]
            for sec in response.data["sections"]
            for lesson in sec["lessons"]
        ]
        assert "Secret lesson" not in titles

    def test_course_aggregates_are_recomputed_on_lesson_save(self, course, section):
        from apps.videos.models import Video

        video = Video.objects.create(
            title="Aggregate",
            cloudflare_video_id="cf-agg-0001",
            status="ready",
            duration_seconds=120,
        )
        Lesson.objects.create(
            section=section,
            title="Counted",
            video=video,
            duration_seconds=120,
            ordering=3,
            status=LessonStatus.PUBLISHED,
        )
        course.refresh_from_db()
        assert course.lesson_count == 1
        assert course.duration_minutes == 2


# --------------------------------------------------------------------------- #
# Locking behaviour
# --------------------------------------------------------------------------- #
class TestLessonLocking:
    def test_unsubscribed_student_sees_paid_lessons_locked(
        self, auth_client, student, course, lesson
    ):
        response = auth_client(student).get(lessons_url(course.slug))
        assert response.status_code == 200
        assert response.data["access"]["allowed"] is False
        assert response.data["access"]["reason"] == "subscription_required"
        assert response.data["lessons"][0]["is_locked"] is True

    def test_subscribed_student_sees_lessons_unlocked(
        self, auth_client, student, course, lesson, active_subscription
    ):
        response = auth_client(student).get(lessons_url(course.slug))
        assert response.status_code == 200
        assert response.data["access"]["allowed"] is True
        assert response.data["lessons"][0]["is_locked"] is False
        assert response.data["lessons"][0]["has_video"] is True

    def test_preview_lesson_is_never_locked(
        self, auth_client, student, course, preview_lesson
    ):
        response = auth_client(student).get(lessons_url(course.slug))
        previews = [item for item in response.data["lessons"] if item["is_preview"]]
        assert previews, "the fixture should provide a preview lesson"
        assert all(item["is_locked"] is False for item in previews)

    def test_expired_subscription_still_locks_the_course(
        self, auth_client, student, course, lesson, expired_subscription
    ):
        response = auth_client(student).get(lessons_url(course.slug))
        assert response.status_code == 200
        assert response.data["access"]["allowed"] is False
        # Distinguished from "never subscribed" so the UI can say "renew".
        assert response.data["access"]["reason"] == "subscription_expired"
        assert response.data["lessons"][0]["is_locked"] is True

    def test_lesson_list_requires_authentication(self, api_client, course):
        response = api_client.get(lessons_url(course.slug))
        assert response.status_code == 401

    def test_access_endpoint_answers_for_anonymous(self, api_client, course):
        response = api_client.get(access_url(course.slug))
        assert response.status_code == 200
        assert response.data["allowed"] is False
        assert response.data["reason"] == "authentication_required"

    def test_free_course_is_accessible_to_any_student(
        self, auth_client, student, free_course
    ):
        response = auth_client(student).get(access_url(free_course.slug))
        assert response.status_code == 200
        assert response.data["allowed"] is True
        assert response.data["reason"] == "free_course"

    def test_plan_that_excludes_the_course_denies_access(
        self, auth_client, other_student, course
    ):
        """A subscription to *some* plan is not a subscription to *this* course."""
        from apps.subscriptions.models import Plan
        from conftest import make_subscription

        # A course deliberately left out of the plan.
        excluded = Course.objects.create(
            title="Advanced Torts",
            slug="advanced-torts",
            description="Not included in the narrow plan.",
            instructor=course.instructor,
            status=CourseStatus.PUBLISHED,
        )
        plan = Plan.objects.create(
            name="Narrow",
            slug="narrow",
            description="Covers nothing on its own.",
            price=Decimal("99.00"),
            duration_days=30,
        )
        make_subscription(other_student, plan)

        response = auth_client(other_student).get(access_url(excluded.slug))
        assert response.status_code == 200
        assert response.data["allowed"] is False
        assert response.data["reason"] == "not_in_plan"


# --------------------------------------------------------------------------- #
# Authoring authorization
# --------------------------------------------------------------------------- #
class TestCourseAuthoring:
    def test_student_cannot_create_a_course(self, auth_client, student):
        response = auth_client(student).post(
            "/api/v1/courses/",
            {"title": "Hacked", "description": "nope"},
            format="json",
        )
        assert response.status_code == 403

    def test_instructor_cannot_create_a_course(self, auth_client, instructor):
        """Course ownership is admin-only; instructors can only view."""
        response = auth_client(instructor).post(
            "/api/v1/courses/",
            {"title": "New Course", "description": "Self-made.", "status": "draft"},
            format="json",
        )
        assert response.status_code == 403
        assert not Course.objects.filter(title="New Course").exists()

    def test_instructor_cannot_take_over_another_instructors_course(
        self, auth_client, course
    ):
        """Regression: PATCHing ``instructor`` to yourself transferred ownership."""
        from apps.users.models import User

        outsider = User.objects.create_instructor(
            email="outsider@test.local", password="Instructor123!", name="Outsider"
        )
        response = auth_client(outsider).patch(
            f"/api/v1/courses/{course.slug}/",
            {"instructor": str(outsider.pk), "unlock_rule": "free"},
            format="json",
        )
        assert response.status_code == 403
        course.refresh_from_db()
        assert course.instructor_id != outsider.pk
        assert course.unlock_rule != "free"

    def test_owner_cannot_edit_their_own_course(self, auth_client, course):
        response = auth_client(course.instructor).patch(
            f"/api/v1/courses/{course.slug}/", {"title": "Renamed"}, format="json"
        )
        assert response.status_code == 403

    def test_admin_can_edit_a_course(self, auth_client, admin_user, course):
        response = auth_client(admin_user).patch(
            f"/api/v1/courses/{course.slug}/", {"title": "Renamed"}, format="json"
        )
        assert response.status_code == 200, response.data
        course.refresh_from_db()
        assert course.title == "Renamed"

    def test_section_cannot_be_moved_into_another_instructors_course(
        self, auth_client, course, section
    ):
        """Regression: PATCHing ``course`` reparented content without a check."""
        from apps.users.models import User

        outsider = User.objects.create_instructor(
            email="outsider@test.local", password="Instructor123!", name="Outsider"
        )
        own_course = Course.objects.create(
            title="Outsider Course", description="x", instructor=outsider
        )
        own_section = own_course.sections.create(title="Mine", ordering=1)
        response = auth_client(outsider).patch(
            f"/api/v1/sections/{own_section.pk}/",
            {"course": str(course.pk), "ordering": 99},
            format="json",
        )
        assert response.status_code == 403
        own_section.refresh_from_db()
        assert own_section.course_id == own_course.pk

    def test_admin_may_assign_another_instructor(
        self, auth_client, admin_user, instructor
    ):
        response = auth_client(admin_user).post(
            "/api/v1/courses/",
            {
                "title": "Admin Assigned",
                "description": "Assigned by an admin.",
                "instructor": str(instructor.pk),
                "status": "draft",
            },
            format="json",
        )
        assert response.status_code == 201, response.data
        assert Course.objects.get(pk=response.data["id"]).instructor_id == instructor.pk

    def test_instructor_cannot_add_a_section_to_another_instructors_course(
        self, auth_client, course
    ):
        """Object-level permission, not just a role check."""
        from apps.users.models import User

        outsider = User.objects.create_instructor(
            email="outsider@test.local", password="Instructor123!", name="Outsider"
        )
        response = auth_client(outsider).post(
            "/api/v1/sections/",
            {"course": str(course.id), "title": "Sneaky", "ordering": 5},
            format="json",
        )
        assert response.status_code == 403

    def test_owner_can_add_a_section(self, auth_client, course):
        response = auth_client(course.instructor).post(
            "/api/v1/sections/",
            {"course": str(course.id), "title": "Second Section", "ordering": 2},
            format="json",
        )
        assert response.status_code == 201, response.data

    def test_student_cannot_create_a_section(self, auth_client, student, course):
        response = auth_client(student).post(
            "/api/v1/sections/",
            {"course": str(course.id), "title": "Nope", "ordering": 4},
            format="json",
        )
        assert response.status_code == 403

    def test_duplicate_section_ordering_is_rejected(self, auth_client, course, section):
        """Rejected cleanly with a 400, never a 500 IntegrityError.

        DRF's auto-generated ``UniqueTogetherValidator`` (from the model's
        ``unique_section_ordering_per_course`` constraint) runs before the custom
        ``validate`` hook, so the error arrives as ``non_field_errors`` rather than
        keyed on ``ordering``.  We assert the status and that *some* error is
        reported; pinning the exact key would make this test brittle to a DRF
        validator-ordering change that is harmless.
        """
        response = auth_client(course.instructor).post(
            "/api/v1/sections/",
            {"course": str(course.id), "title": "Clash", "ordering": section.ordering},
            format="json",
        )
        assert response.status_code == 400
        # DRF surfaces the model constraint as the specific code ``unique``, which
        # is more useful to a client than a generic ``validation_error``.
        assert response.data["error"]["code"] == "unique"
        assert response.data["error"]["details"], "an error must be reported"

    def test_negative_price_is_rejected(self, auth_client, admin_user):
        response = auth_client(admin_user).post(
            "/api/v1/courses/",
            {"title": "Negative", "description": "x", "price": "-1.00"},
            format="json",
        )
        assert response.status_code == 400

    def test_unknown_status_is_rejected(self, auth_client, admin_user):
        response = auth_client(admin_user).post(
            "/api/v1/courses/",
            {"title": "Bad Status", "description": "x", "status": "banana"},
            format="json",
        )
        assert response.status_code == 400

    def test_publishing_stamps_published_at_only_once(self, course):
        from django.utils import timezone

        course.status = CourseStatus.DRAFT
        course.published_at = None
        course.save()

        course.publish()
        first_stamp = course.published_at
        assert first_stamp is not None

        course.publish()
        course.refresh_from_db()
        # Re-publishing must not move the original publication date.
        assert course.published_at == first_stamp
        assert course.published_at <= timezone.now()


# --------------------------------------------------------------------------- #
# Hierarchy integrity
# --------------------------------------------------------------------------- #
class TestHierarchyIntegrity:
    def test_lesson_ordering_is_unique_within_a_section(
        self, auth_client, course, section, lesson
    ):
        from apps.videos.models import Video

        video = Video.objects.create(
            title="Clashing",
            cloudflare_video_id="cf-clash-0001",
            status="ready",
            duration_seconds=10,
        )
        response = auth_client(course.instructor).post(
            "/api/v1/lessons/",
            {
                "section": str(section.id),
                "title": "Clashing lesson",
                "video": str(video.id),
                "ordering": lesson.ordering,
            },
            format="json",
        )
        assert response.status_code == 400
        assert response.data["error"]["code"] == "unique"
        assert response.data["error"]["details"]

    def test_a_lesson_cannot_exist_without_a_video_or_quiz(self, section):
        """DB-level constraint: an empty lesson is a data-integrity bug."""
        from django.db import IntegrityError, transaction

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Lesson.objects.create(section=section, title="Empty", ordering=42)

    def test_sections_order_by_their_ordering_field(self, section):
        course = section.course
        Section.objects.create(course=course, title="Third", ordering=3)
        Section.objects.create(course=course, title="Second", ordering=2)
        # Query the model explicitly: ``course.sections.all()`` with Meta.ordering
        # applied is what every list endpoint actually uses.
        titles = list(
            Section.objects.filter(course=course).values_list("title", flat=True)
        )
        assert titles == ["Foundations", "Second", "Third"]

    def test_slug_is_generated_and_deconflicted(self, instructor):
        Course.objects.create(
            title="Duplicate Title", description="first", instructor=instructor
        )
        second = Course.objects.create(
            title="Duplicate Title", description="second", instructor=instructor
        )
        assert second.slug == "duplicate-title-2"

    def test_lesson_touches_its_course_property_correctly(self, lesson, course):
        assert lesson.course.pk == course.pk


# --------------------------------------------------------------------------- #
# Query efficiency (N+1 guard)
# --------------------------------------------------------------------------- #
class TestQueryEfficiency:
    def test_course_list_query_count_is_constant(self, api_client, instructor):
        """Adding courses must not add queries."""
        for index in range(12):
            Course.objects.create(
                title=f"Scale {index}",
                slug=f"scale-{index}",
                description="x",
                instructor=instructor,
                status=CourseStatus.PUBLISHED,
            )

        with CaptureQueriesContext(connection) as captured:
            response = api_client.get("/api/v1/courses/")
        assert response.status_code == 200

        # 1 count + 1 page of rows + auth lookups.  The property that matters is
        # that it is bounded and small: 12 courses must not mean 12 extra queries.
        assert len(captured) <= 8, f"possible N+1: {len(captured)} queries"

    def test_course_detail_query_count_is_constant(self, api_client, course, section):
        from apps.videos.models import Video

        for index in range(10):
            video = Video.objects.create(
                title=f"V{index}",
                cloudflare_video_id=f"cf-n1-{index:04d}",
                status="ready",
                duration_seconds=60,
            )
            Lesson.objects.create(
                section=section,
                title=f"L{index}",
                video=video,
                duration_seconds=60,
                ordering=index + 20,
                status=LessonStatus.PUBLISHED,
            )

        with CaptureQueriesContext(connection) as captured:
            response = api_client.get(detail_url(course.slug))
        assert response.status_code == 200
        assert len(response.data["sections"][0]["lessons"]) == 10

        # 1 course + 1 sections + 1 lessons + 1 quizzes + auth, regardless of how
        # many lessons the course has.
        assert len(captured) <= 10, f"possible N+1: {len(captured)} queries"
