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
