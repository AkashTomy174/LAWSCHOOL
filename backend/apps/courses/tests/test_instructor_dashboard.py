"""The instructor dashboard: scoped to the teacher's own courses, student-free of staff."""

import pytest
from django.urls import reverse

from apps.courses.models import Course
from apps.videos.models import VideoProgress

URL = "/api/v1/courses/instructor/dashboard/"


@pytest.fixture
def progress(student, lesson, course):
    return VideoProgress.objects.create(
        user=student, video=lesson.video, lesson=lesson,
        watched_seconds=600, last_position=600, completion_percentage=100, completed=True,
    )


@pytest.mark.django_db
def test_student_forbidden_anonymous_unauthorised(student, auth_client, api_client):
    assert auth_client(student).get(URL).status_code == 403
    assert api_client.get(URL).status_code in (401, 403)


@pytest.mark.django_db
def test_instructor_sees_own_course_stats(instructor, auth_client, progress, course):
    data = auth_client(instructor).get(URL).json()
    assert data["totals"]["courses"] == 1
    assert data["totals"]["students"] == 1
    row = data["courses"][0]
    assert row["student_count"] == 1 and row["completion_percent"] == 100
    assert row["lessons"][0]["watchers"] == 1


@pytest.mark.django_db
def test_instructor_does_not_see_other_instructors_courses(auth_client, instructor, course, django_user_model):
    other = django_user_model.objects.create_instructor(
        email="o2@test.local", password="Instructor123!", name="Other"
    )
    Course.objects.create(title="Theirs", slug="theirs", description="x", instructor=other)
    titles = [c["title"] for c in auth_client(instructor).get(URL).json()["courses"]]
    assert titles == [course.title]


@pytest.mark.django_db
def test_teachers_own_activity_is_not_counted_as_a_student(instructor, auth_client, lesson):
    VideoProgress.objects.create(user=instructor, video=lesson.video, lesson=lesson, completed=True)
    assert auth_client(instructor).get(URL).json()["totals"]["students"] == 0
