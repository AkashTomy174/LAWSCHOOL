"""Live classes: the join link is gated by the same course entitlement as
everything else -- no new access logic is being tested here, just that the
existing ``can_user_access_course`` reasons propagate unchanged.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.live.models import LiveClass

pytestmark = pytest.mark.django_db


@pytest.fixture
def live_class(course):
    return LiveClass.objects.create(
        course=course,
        title="Live Doubt Session",
        scheduled_start=timezone.now() + timedelta(days=1),
        meeting_provider="zoom",
        meeting_url="https://zoom.us/j/123456789",
    )


class TestLiveClassAccess:
    def test_entitled_user_gets_meeting_url(
        self, jwt_client, student, live_class, active_subscription
    ):
        response = jwt_client(student).get(f"/api/v1/live-classes/{live_class.id}/join/")
        assert response.status_code == 200
        assert response.data["meeting_url"] == live_class.meeting_url

    def test_unsubscribed_user_is_denied(self, jwt_client, student, live_class):
        response = jwt_client(student).get(f"/api/v1/live-classes/{live_class.id}/join/")
        assert response.status_code == 403
        assert "meeting_url" not in response.data

    def test_anonymous_user_is_denied(self, api_client, live_class):
        response = api_client.get(f"/api/v1/live-classes/{live_class.id}/join/")
        assert response.status_code == 401

    def test_list_endpoint_never_exposes_the_meeting_url(
        self, jwt_client, student, live_class, active_subscription
    ):
        """Even an entitled student only gets the link from the join endpoint."""
        response = jwt_client(student).get(
            f"/api/v1/live-classes/?course={live_class.course.slug}"
        )
        assert response.status_code == 200
        assert "meeting_url" not in str(response.data)

    def test_instructor_can_schedule_a_live_class(self, jwt_client, instructor, course):
        response = jwt_client(instructor).post(
            "/api/v1/live-classes/manage/",
            {
                "course": str(course.id),
                "title": "New Session",
                "scheduled_start": (timezone.now() + timedelta(days=2)).isoformat(),
                "meeting_provider": "google_meet",
                "meeting_url": "https://meet.google.com/abc-defg-hij",
            },
            format="json",
        )
        assert response.status_code == 201, response.data
        assert LiveClass.objects.filter(title="New Session").exists()

    def test_student_cannot_schedule_a_live_class(self, jwt_client, student, course):
        response = jwt_client(student).post(
            "/api/v1/live-classes/manage/",
            {
                "course": str(course.id),
                "title": "Sneaky Session",
                "scheduled_start": timezone.now().isoformat(),
                "meeting_url": "https://zoom.us/j/999",
            },
            format="json",
        )
        assert response.status_code == 403


class TestHostIsDerivedFromCourse:
    """``instructor`` used to be client-writable: any user (even a student) could be
    named as a live class's host.  It is now always the course's instructor."""

    def _payload(self, course, **extra):
        return {
            "course": str(course.id),
            "title": "Host check",
            "scheduled_start": (timezone.now() + timedelta(days=1)).isoformat(),
            "meeting_url": "https://meet.google.com/abc-defg-hij",
            **extra,
        }

    def test_create_ignores_a_client_supplied_host(
        self, jwt_client, instructor, student, course
    ):
        response = jwt_client(instructor).post(
            "/api/v1/live-classes/manage/",
            self._payload(course, instructor=str(student.id)),
            format="json",
        )
        assert response.status_code == 201, response.data
        live = LiveClass.objects.get(pk=response.data["id"])
        assert live.instructor_id == course.instructor_id
        assert str(response.data["instructor"]) == str(course.instructor_id)

    def test_admin_created_class_is_hosted_by_the_course_instructor(
        self, jwt_client, admin_user, course
    ):
        response = jwt_client(admin_user).post(
            "/api/v1/live-classes/manage/", self._payload(course), format="json"
        )
        assert response.status_code == 201, response.data
        assert LiveClass.objects.get(pk=response.data["id"]).instructor_id == (
            course.instructor_id
        )

    def test_update_cannot_change_the_host(
        self, jwt_client, instructor, student, live_class
    ):
        response = jwt_client(instructor).patch(
            f"/api/v1/live-classes/manage/{live_class.id}/",
            {"instructor": str(student.id), "title": "Renamed"},
            format="json",
        )
        assert response.status_code == 200, response.data
        live_class.refresh_from_db()
        assert live_class.title == "Renamed"
        assert live_class.instructor_id == live_class.course.instructor_id

    def test_orm_writes_are_overridden_too(self, student, course):
        """Covers the Django admin and any future code path, not just the API."""
        live = LiveClass.objects.create(
            course=course,
            title="ORM",
            scheduled_start=timezone.now(),
            meeting_url="https://zoom.us/j/1",
            instructor=student,
        )
        assert live.instructor_id == course.instructor_id
        live.instructor = student
        live.save(update_fields=["instructor"])
        live.refresh_from_db()
        assert live.instructor_id == course.instructor_id
