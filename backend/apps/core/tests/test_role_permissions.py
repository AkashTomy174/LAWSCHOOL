"""Role boundaries as the API enforces them, independent of what the SPA shows.

Instructors are staff but not admins: they may manage *their own* courses' content
and nothing platform-wide. These tests pin both halves -- the admin-only surfaces
refuse instructors, and the instructor surfaces never leak another instructor's rows.
"""

import pytest
from decimal import Decimal

from apps.core.constants import CourseStatus
from apps.courses.models import Course, Lesson, Section
from apps.live.models import LiveClass
from apps.quizzes.models import Quiz, QuizAttempt
from apps.users.models import User
from apps.videos.models import Video

pytestmark = pytest.mark.django_db

ADMIN_ONLY_GET = [
    "/api/v1/users/",
    "/api/v1/subscriptions/",
    "/api/v1/payments/all/",
    "/api/v1/payments/webhook-events/",
]


@pytest.fixture
def rival(db):
    return User.objects.create_instructor(
        email="rival@test.local", password="Instructor123!", name="Rival Instructor"
    )


@pytest.fixture
def rival_course(rival):
    return Course.objects.create(
        title="Rival Course", slug="rival-course", description="x",
        instructor=rival, status=CourseStatus.PUBLISHED,
        price=Decimal("999.00"),
    )


@pytest.fixture
def rival_content(rival_course, db):
    """A section, lesson, video, quiz, live class and a graded attempt owned by the rival."""
    section = Section.objects.create(course=rival_course, title="S", ordering=1)
    video = Video.objects.create(
        title="Rival video", cloudflare_video_id="cf-rival-1", status="ready", duration_seconds=60
    )
    lesson = Lesson.objects.create(section=section, title="L", video=video, ordering=1, status="published")
    quiz = Quiz.objects.create(course=rival_course, title="Rival quiz", is_published=True)
    live = LiveClass.objects.create(
        course=rival_course, title="Rival live", scheduled_start="2030-01-01T10:00:00Z",
        meeting_url="https://zoom.example.com/j/1",
    )
    learner = User.objects.create_user(email="l@test.local", password="StudentPass123!", name="L")
    attempt = QuizAttempt.objects.create(quiz=quiz, user=learner, submitted_at="2030-01-01T10:00:00Z")
    return {"section": section, "lesson": lesson, "video": video, "quiz": quiz, "live": live, "attempt": attempt}


class TestAdminOnlySurfaces:
    @pytest.mark.parametrize("url", ADMIN_ONLY_GET)
    def test_instructor_is_refused(self, auth_client, instructor, url):
        assert auth_client(instructor).get(url).status_code == 403

    @pytest.mark.parametrize("url", ADMIN_ONLY_GET)
    def test_student_is_refused(self, auth_client, student, url):
        assert auth_client(student).get(url).status_code == 403

    @pytest.mark.parametrize("url", ADMIN_ONLY_GET)
    def test_admin_is_allowed(self, auth_client, admin_user, url):
        assert auth_client(admin_user).get(url).status_code == 200

    def test_instructor_cannot_create_plan_or_recalculate(self, auth_client, instructor):
        client = auth_client(instructor)
        assert client.post("/api/v1/subscriptions/plans/", {"name": "x"}, format="json").status_code == 403
        assert client.post("/api/v1/leaderboard/recalculate/").status_code == 403

    def test_instructor_cannot_edit_own_course_metadata(self, auth_client, instructor, course):
        r = auth_client(instructor).patch(f"/api/v1/courses/{course.slug}/", {"price": "1.00"}, format="json")
        assert r.status_code == 403


class TestInstructorOwnsOnlyTheirResources:
    def test_scope_mine_lists_only_own_courses(self, auth_client, instructor, course, rival_course):
        slugs = {c["slug"] for c in auth_client(instructor).get("/api/v1/courses/?scope=mine").json()["results"]}
        assert slugs == {course.slug}

    def test_scope_mine_includes_own_drafts(self, auth_client, instructor, course, draft_course):
        slugs = {c["slug"] for c in auth_client(instructor).get("/api/v1/courses/?scope=mine").json()["results"]}
        assert slugs == {course.slug, draft_course.slug}

    def test_scope_mine_is_empty_for_anonymous_and_students(self, api_client, auth_client, student, course):
        assert api_client.get("/api/v1/courses/?scope=mine").json()["results"] == []
        assert auth_client(student).get("/api/v1/courses/?scope=mine").json()["results"] == []

    def test_lists_never_include_a_rivals_rows(self, auth_client, instructor, rival_content):
        client = auth_client(instructor)
        assert client.get("/api/v1/videos/").json() == []
        assert client.get("/api/v1/quizzes/").json() == []
        assert client.get("/api/v1/sections/").json() == [] or client.get("/api/v1/sections/").json()["results"] == []
        assert client.get("/api/v1/quiz-attempts/all/").json()["results"] == []
        assert client.get("/api/v1/live-classes/manage/").json() == []

    def test_detail_and_write_on_a_rivals_rows_is_404(self, auth_client, instructor, rival_content):
        client = auth_client(instructor)
        r = rival_content
        assert client.patch(f"/api/v1/sections/{r['section'].pk}/", {"title": "hacked"}, format="json").status_code == 404
        assert client.patch(f"/api/v1/lessons/{r['lesson'].pk}/", {"title": "hacked"}, format="json").status_code == 404
        assert client.patch(f"/api/v1/quizzes/{r['quiz'].pk}/", {"title": "hacked"}, format="json").status_code == 404
        assert client.delete(f"/api/v1/quizzes/{r['quiz'].pk}/").status_code == 404
        assert client.patch(f"/api/v1/live-classes/manage/{r['live'].pk}/", {"title": "hacked"}, format="json").status_code == 404
        assert client.delete(f"/api/v1/live-classes/manage/{r['live'].pk}/").status_code == 404

    def test_cannot_author_into_a_rivals_course(self, auth_client, instructor, rival_course):
        client = auth_client(instructor)
        assert client.post("/api/v1/sections/", {"course": str(rival_course.pk), "title": "x", "ordering": 1}, format="json").status_code == 403
        assert client.post("/api/v1/quizzes/", {"course": str(rival_course.pk), "title": "x"}, format="json").status_code == 403
        assert client.post(
            "/api/v1/live-classes/manage/",
            {"course": str(rival_course.pk), "title": "x", "scheduled_start": "2030-01-01T10:00:00Z",
             "meeting_url": "https://zoom.example.com/j/2"},
            format="json",
        ).status_code == 403

    def test_admin_still_sees_everything(self, auth_client, admin_user, course, rival_content):
        client = auth_client(admin_user)
        assert len(client.get("/api/v1/videos/").json()) == 1
        assert len(client.get("/api/v1/live-classes/manage/").json()) == 1
        assert len(client.get("/api/v1/quiz-attempts/all/").json()["results"]) == 1
