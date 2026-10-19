"""A lesson must carry a quiz or a video; the API says so with a 400, not a DB 500."""

import pytest

pytestmark = pytest.mark.django_db


def _payload(section, **extra):
    return {"section": str(section.pk), "title": "New lesson", "ordering": 9, "status": "draft", **extra}


def test_lesson_without_quiz_or_video_is_a_400(auth_client, instructor, section):
    r = auth_client(instructor).post("/api/v1/lessons/", _payload(section), format="json")
    assert r.status_code == 400
    assert "quiz" in str(r.json()).lower()


def test_lesson_with_a_quiz_from_the_same_course_is_created(auth_client, instructor, section, quiz):
    r = auth_client(instructor).post("/api/v1/lessons/", _payload(section, quiz=str(quiz.pk)), format="json")
    assert r.status_code == 201


def test_publishing_an_existing_video_lesson_still_works(auth_client, instructor, lesson):
    r = auth_client(instructor).patch(f"/api/v1/lessons/{lesson.pk}/", {"status": "draft"}, format="json")
    assert r.status_code == 200


def test_lesson_list_filters_by_course(auth_client, instructor, lesson, free_course):
    """The course editor asks for one course's lessons, so a large catalogue cannot
    push them past the page cap."""
    from apps.courses.models import Section

    Section.objects.create(course=free_course, title="Other", ordering=1)
    r = auth_client(instructor).get("/api/v1/lessons/", {"course": free_course.slug})
    assert r.status_code == 200
    assert r.data["results"] == []
    r = auth_client(instructor).get("/api/v1/lessons/", {"course": lesson.section.course.slug})
    assert [row["id"] for row in r.data["results"]] == [str(lesson.pk)]


def _bulk_lessons(section, count, prefix="L"):
    """``count`` quiz-only lessons (each lesson needs its own one-to-one quiz)."""
    from apps.courses.models import Lesson
    from apps.quizzes.models import Quiz

    quizzes = Quiz.objects.bulk_create(
        Quiz(course=section.course, title=f"{prefix}{i} quiz") for i in range(count)
    )
    return Lesson.objects.bulk_create(
        Lesson(section=section, title=f"{prefix}{i:03d}", quiz=q, ordering=i + 1)
        for i, q in enumerate(quizzes)
    )


class TestVideoLessonPicker:
    """The Videos tab pages through every lesson that still needs a video."""

    URL = "/api/v1/lessons/"

    def test_pages_reach_lessons_beyond_the_first_hundred(self, auth_client, instructor, section):
        lessons = _bulk_lessons(section, 105)
        client = auth_client(instructor)
        first = client.get(self.URL, {"without_video": "true", "page_size": 100})
        assert first.data["count"] == 105
        assert len(first.data["results"]) == 100
        second = client.get(self.URL, {"without_video": "true", "page_size": 100, "page": 2})
        assert len(second.data["results"]) == 5
        ids = [r["id"] for r in first.data["results"] + second.data["results"]]
        assert len(set(ids)) == 105  # no lesson skipped or repeated at the boundary
        assert str(lessons[-1].pk) in ids[100:]

    def test_without_video_and_course_filters(self, auth_client, instructor, lesson, free_course):
        from apps.courses.models import Section

        other = _bulk_lessons(Section.objects.create(course=free_course, title="S", ordering=1), 2)
        client = auth_client(instructor)
        ids = [r["id"] for r in client.get(self.URL, {"without_video": "true"}).data["results"]]
        assert str(lesson.pk) not in ids  # already has a video
        assert set(ids) == {str(x.pk) for x in other}
        scoped = client.get(self.URL, {"without_video": "true", "course": lesson.section.course.slug})
        assert scoped.data["results"] == []

    def test_search_matches_lesson_or_course_title(self, auth_client, instructor, section):
        _bulk_lessons(section, 3, prefix="Bail")
        _bulk_lessons(section.course.sections.create(title="T", ordering=2), 2, prefix="Writ")
        client = auth_client(instructor)
        assert client.get(self.URL, {"search": "writ"}).data["count"] == 2
        by_course = client.get(self.URL, {"search": section.course.title[:6]})
        assert by_course.data["count"] == 5
        assert client.get(self.URL, {"search": "no-such-lesson"}).data["results"] == []

    def test_other_instructors_and_students_see_nothing(
        self, auth_client, api_client, section, student
    ):
        from django.contrib.auth import get_user_model

        _bulk_lessons(section, 3)
        stranger = get_user_model().objects.create_user(
            email="other-instructor@test.local", password="x-Pass-12345", name="O", role="instructor"
        )
        assert auth_client(stranger).get(self.URL, {"without_video": "true"}).data["count"] == 0
        assert auth_client(student).get(self.URL).status_code == 403
        assert api_client.get(self.URL).status_code == 401

    def test_admin_sees_every_course(self, auth_client, admin_user, section):
        _bulk_lessons(section, 2)
        assert auth_client(admin_user).get(self.URL, {"without_video": "true"}).data["count"] == 2
