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
        # Inside the join window (it opens 15 minutes before the start).
        live_class.scheduled_start = timezone.now() + timedelta(minutes=5)
        live_class.save()
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


def _at(live_class, *, minutes_from_now, duration=60):
    live_class.scheduled_start = timezone.now() + timedelta(minutes=minutes_from_now)
    live_class.duration_minutes = duration
    live_class.save()
    return f"/api/v1/live-classes/{live_class.id}/join/"


class TestJoinWindow:
    """The site hands out the link only from 15 minutes before the start until the end."""

    def test_too_early_is_refused_with_the_opening_time(
        self, jwt_client, student, live_class, active_subscription
    ):
        response = jwt_client(student).get(_at(live_class, minutes_from_now=16))
        assert response.status_code == 403
        assert response.data["error"]["code"] == "class_not_open"
        assert "meeting_url" not in str(response.data)

    @pytest.mark.parametrize("minutes_from_now", [14, 0, -59])
    def test_open_from_just_before_start_until_the_end(
        self, jwt_client, student, live_class, active_subscription, minutes_from_now
    ):
        response = jwt_client(student).get(_at(live_class, minutes_from_now=minutes_from_now))
        assert response.status_code == 200
        assert response.data["meeting_url"] == live_class.meeting_url

    def test_ended_class_is_refused(self, jwt_client, student, live_class, active_subscription):
        response = jwt_client(student).get(_at(live_class, minutes_from_now=-61))
        assert response.status_code == 403
        assert response.data["error"]["code"] == "class_ended"

    def test_entitlement_is_checked_before_the_window(self, jwt_client, student, live_class):
        response = jwt_client(student).get(_at(live_class, minutes_from_now=0))
        assert response.status_code == 403
        assert response.data["error"]["code"] == "subscription_required"

    def test_unpublished_class_is_not_found(self, jwt_client, student, live_class, active_subscription):
        live_class.is_published = False
        url = _at(live_class, minutes_from_now=0)
        assert jwt_client(student).get(url).status_code == 404

    def test_owning_instructor_and_admin_can_join_in_the_window(
        self, jwt_client, instructor, admin_user, live_class
    ):
        url = _at(live_class, minutes_from_now=0)
        assert jwt_client(instructor).get(url).status_code == 200
        assert jwt_client(admin_user).get(url).status_code == 200

    def test_other_instructor_cannot_join(self, jwt_client, live_class):
        from django.contrib.auth import get_user_model

        stranger = get_user_model().objects.create_user(
            email="stranger@test.local", password="x-Pass-12345", name="S", role="instructor"
        )
        response = jwt_client(stranger).get(_at(live_class, minutes_from_now=0))
        assert response.status_code == 403


class TestStudentList:
    URL = "/api/v1/live-classes/"

    def test_only_classes_the_student_can_attend_are_listed(
        self, jwt_client, student, live_class, active_subscription, free_course
    ):
        LiveClass.objects.create(
            course=free_course, title="Free Q&A",
            scheduled_start=timezone.now() + timedelta(days=2),
            meeting_url="https://zoom.us/j/2",
        )
        titles = {row["title"] for row in jwt_client(student).get(self.URL).data}
        assert titles == {"Live Doubt Session", "Free Q&A"}

    def test_locked_courses_are_not_listed(self, jwt_client, student, live_class):
        assert jwt_client(student).get(self.URL).data == []

    def test_rows_carry_course_instructor_and_server_status(
        self, jwt_client, student, live_class, active_subscription
    ):
        _at(live_class, minutes_from_now=-10, duration=60)
        (row,) = jwt_client(student).get(self.URL).data
        assert row["course_title"] == live_class.course.title
        assert row["course_slug"] == live_class.course.slug
        assert row["instructor_name"] == live_class.course.instructor.name
        assert row["status"] == "live"
        assert row["can_join"] is True
        assert "meeting_url" not in row

    @pytest.mark.parametrize(
        ("minutes_from_now", "status", "can_join"),
        [(30, "upcoming", False), (10, "upcoming", True), (-30, "live", True), (-61, "ended", False)],
    )
    def test_status_boundaries(
        self, jwt_client, student, live_class, active_subscription, minutes_from_now, status, can_join
    ):
        _at(live_class, minutes_from_now=minutes_from_now, duration=60)
        (row,) = jwt_client(student).get(self.URL).data
        assert (row["status"], row["can_join"]) == (status, can_join)

    def test_classes_older_than_a_week_drop_off(
        self, jwt_client, student, live_class, active_subscription
    ):
        _at(live_class, minutes_from_now=-8 * 24 * 60)
        assert jwt_client(student).get(self.URL).data == []

    def test_timestamps_are_timezone_aware(self, jwt_client, student, live_class, active_subscription):
        (row,) = jwt_client(student).get(self.URL).data
        assert row["scheduled_start"][-6] in "+-" or row["scheduled_start"].endswith("Z")
        assert row["ends_at"][-6] in "+-" or row["ends_at"].endswith("Z")


class TestMeetingLinkValidation:
    @pytest.mark.parametrize("url", ["", "not a url", "javascript:alert(1)"])
    def test_bad_links_are_rejected(self, jwt_client, instructor, course, url):
        response = jwt_client(instructor).post(
            "/api/v1/live-classes/manage/",
            {"course": str(course.pk), "title": "x", "meeting_url": url,
             "scheduled_start": (timezone.now() + timedelta(days=1)).isoformat()},
            format="json",
        )
        assert response.status_code == 400
        assert "meeting_url" in response.data["error"]["details"]


class TestJoinEdgeCases:
    def test_revoked_access_stops_the_link(self, jwt_client, student, live_class, active_subscription):
        from apps.subscriptions.services_lifecycle import cancel_subscription

        url = _at(live_class, minutes_from_now=0)
        assert jwt_client(student).get(url).status_code == 200
        cancel_subscription(subscription=active_subscription, immediate=True)
        refused = jwt_client(student).get(url)
        assert refused.status_code == 403
        assert "meeting_url" not in str(refused.data)

    def test_deleted_class_is_not_found(self, jwt_client, student, live_class, active_subscription):
        url = _at(live_class, minutes_from_now=0)
        live_class.delete()
        assert jwt_client(student).get(url).status_code == 404

    @pytest.mark.parametrize("stored", ["ftp://files.example/x", "javascript:alert(1)", "zoom"])
    def test_a_malformed_stored_link_is_never_returned(
        self, jwt_client, student, live_class, active_subscription, stored
    ):
        url = _at(live_class, minutes_from_now=0)
        LiveClass.objects.filter(pk=live_class.pk).update(meeting_url=stored)  # bypasses validation
        response = jwt_client(student).get(url)
        assert response.status_code == 409
        assert response.data["error"]["code"] == "meeting_link_invalid"
        assert stored not in str(response.data)
