"""Course read visibility: who may look up which course.

    Admin       -> every course
    Instructor  -> published courses + courses they teach
    Student     -> published only
    Anonymous   -> published only

Regression: instructors used to see *every* draft because the rule checked the
role ("is an instructor") instead of ownership ("teaches this course").  Any
instructor could read another instructor's unpublished course description and
lesson titles through five read endpoints.
"""

from __future__ import annotations

import pytest

from apps.core.constants import CourseStatus, LessonStatus
from apps.courses.models import Course, Lesson, Section
from apps.users.models import User
from apps.videos.models import Video

SECRET_DESCRIPTION = "Unreleased syllabus for instructor A only."
SECRET_LESSON = "Unreleased lesson title"


@pytest.fixture
def other_instructor(db):
    return User.objects.create_instructor(
        email="instructor-b@test.local", password="Instructor123!", name="Instructor B"
    )


@pytest.fixture
def a_draft(db, instructor):
    """Instructor A's draft, with a published section and lesson inside it."""
    draft = Course.objects.create(
        title="A Draft",
        slug="a-draft",
        description=SECRET_DESCRIPTION,
        instructor=instructor,
        status=CourseStatus.DRAFT,
    )
    section = Section.objects.create(course=draft, title="S1", ordering=1)
    video = Video.objects.create(
        title="v", cloudflare_video_id="cf-a-draft", status="ready", duration_seconds=60
    )
    Lesson.objects.create(
        section=section,
        title=SECRET_LESSON,
        video=video,
        ordering=1,
        status=LessonStatus.PUBLISHED,
    )
    return draft


@pytest.fixture
def b_draft(db, other_instructor):
    return Course.objects.create(
        title="B Draft",
        slug="b-draft",
        description="B's own draft.",
        instructor=other_instructor,
        status=CourseStatus.DRAFT,
    )


def _client(name, request, api_client, auth_client):
    """An API client for a role name; ``anon`` is unauthenticated."""
    if name == "anon":
        return api_client
    fixture = {
        "admin": "admin_user",
        "owner": "instructor",
        "other_instructor": "other_instructor",
        "student": "student",
    }[name]
    return auth_client(request.getfixturevalue(fixture))


def _slugs(response) -> set[str]:
    body = response.json()
    rows = body["results"] if isinstance(body, dict) else body
    return {row["slug"] for row in rows}


class TestCrossInstructorLeak:
    """The exact reported issue: instructor B probing instructor A's draft."""

    def test_other_instructor_cannot_read_a_draft_anywhere(
        self, auth_client, other_instructor, a_draft, b_draft, course
    ):
        client = auth_client(other_instructor)

        listing = client.get("/api/v1/courses/?scope=all")
        assert listing.status_code == 200
        assert _slugs(listing) == {course.slug, b_draft.slug}  # not a-draft

        for url in (
            f"/api/v1/courses/{a_draft.slug}/",
            f"/api/v1/courses/{a_draft.slug}/lessons/",
            f"/api/v1/courses/{a_draft.slug}/access/",
            f"/api/v1/progress/course/{a_draft.slug}/",
        ):
            response = client.get(url)
            assert response.status_code == 404, url
            body = response.content.decode()
            assert SECRET_DESCRIPTION not in body, url
            assert SECRET_LESSON not in body, url

    def test_other_instructor_still_cannot_modify_the_draft(
        self, auth_client, other_instructor, a_draft
    ):
        client = auth_client(other_instructor)
        assert (
            client.patch(
                f"/api/v1/courses/{a_draft.slug}/", {"title": "x"}, format="json"
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/v1/sections/",
                {"course": str(a_draft.id), "title": "x", "ordering": 2},
                format="json",
            ).status_code
            == 403
        )


# (role, can see published, can see A's draft)
MATRIX = [
    ("admin", True, True),
    ("owner", True, True),
    ("other_instructor", True, False),
    ("student", True, False),
    ("anon", True, False),
]


@pytest.mark.parametrize("role,sees_published,sees_draft", MATRIX)
class TestVisibilityMatrix:
    def test_detail(
        self, request, api_client, auth_client, other_instructor, course, a_draft,
        role, sees_published, sees_draft,
    ):
        client = _client(role, request, api_client, auth_client)
        assert client.get(f"/api/v1/courses/{course.slug}/").status_code == (
            200 if sees_published else 404
        )
        draft = client.get(f"/api/v1/courses/{a_draft.slug}/")
        assert draft.status_code == (200 if sees_draft else 404)
        if sees_draft:
            assert draft.json()["description"] == SECRET_DESCRIPTION

    def test_access_check(
        self, request, api_client, auth_client, other_instructor, course, a_draft,
        role, sees_published, sees_draft,
    ):
        client = _client(role, request, api_client, auth_client)
        assert client.get(f"/api/v1/courses/{course.slug}/access/").status_code == 200
        assert client.get(f"/api/v1/courses/{a_draft.slug}/access/").status_code == (
            200 if sees_draft else 404
        )

    def test_lessons(
        self, request, api_client, auth_client, other_instructor, course, a_draft,
        role, sees_published, sees_draft,
    ):
        if role == "anon":
            pytest.skip("the lesson list requires sign-in for every course")
        client = _client(role, request, api_client, auth_client)
        assert client.get(f"/api/v1/courses/{course.slug}/lessons/").status_code == 200
        draft = client.get(f"/api/v1/courses/{a_draft.slug}/lessons/")
        assert draft.status_code == (200 if sees_draft else 404)
        assert (SECRET_LESSON in draft.content.decode()) is sees_draft

    def test_progress(
        self, request, api_client, auth_client, other_instructor, course, a_draft,
        role, sees_published, sees_draft,
    ):
        if role == "anon":
            pytest.skip("progress requires sign-in")
        client = _client(role, request, api_client, auth_client)
        assert client.get(f"/api/v1/progress/course/{course.slug}/").status_code == 200
        assert client.get(f"/api/v1/progress/course/{a_draft.slug}/").status_code == (
            200 if sees_draft else 404
        )

    def test_scope_all_listing(
        self, request, api_client, auth_client, other_instructor, course, a_draft,
        b_draft, role, sees_published, sees_draft,
    ):
        client = _client(role, request, api_client, auth_client)
        listed = _slugs(client.get("/api/v1/courses/?scope=all"))
        assert (course.slug in listed) is sees_published
        assert (a_draft.slug in listed) is sees_draft
        # B's draft is visible to B and admins only.
        assert (b_draft.slug in listed) is (role in {"admin", "other_instructor"})


def test_default_catalogue_stays_published_only(auth_client, instructor, course, a_draft):
    """Without ?scope=all even the owner gets the public catalogue."""
    assert _slugs(auth_client(instructor).get("/api/v1/courses/")) == {course.slug}


def test_draft_lesson_in_a_visible_course_stays_hidden(
    auth_client, other_instructor, course, section, lesson
):
    """Seeing a published course must not reveal its unpublished lessons."""
    Lesson.objects.create(
        section=section,
        title="Draft lesson inside a published course",
        video=Video.objects.create(
            title="d", cloudflare_video_id="cf-draft-lesson", status="ready"
        ),
        ordering=2,
        status=LessonStatus.DRAFT,
    )
    body = (
        auth_client(other_instructor)
        .get(f"/api/v1/courses/{course.slug}/lessons/")
        .content.decode()
    )
    assert lesson.title in body
    assert "Draft lesson inside a published course" not in body
