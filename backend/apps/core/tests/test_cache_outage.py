"""Behaviour with the cache (Redis) unreachable.

Regression: every cache call raised straight through, so a Redis outage turned
login, token refresh, course access and playback into HTTP 500s.

The policy each test pins:

* entitlement / leaderboard caching is an optimisation: skip it, decide from
  the database, and never *grant* access because the cache failed;
* the ``auth`` throttle (login, register, verification, password reset) is a
  brute-force control: fail closed with a fast 503;
* other throttles and the playback limiter fail open: tokens are signed, the
  blacklist lives in the database, and entitlement is still checked;
* invalidation failures never break the state change that triggered them.
"""

from __future__ import annotations

import pytest
from django.core.cache.backends.base import BaseCache


class BrokenCache(BaseCache):
    """A cache whose every operation fails, like Redis refusing connections."""

    def __init__(self, location, params):
        super().__init__(params)

    def _fail(self, *args, **kwargs):
        raise ConnectionError("cache unreachable")

    get = set = add = delete = incr = get_many = set_many = delete_many = _fail
    has_key = touch = clear = _fail


@pytest.fixture
def cache_down(settings):
    settings.CACHES = {
        "default": {"BACKEND": "apps.core.tests.test_cache_outage.BrokenCache"}
    }


def _login(client, email, password):
    return client.post("/api/v1/auth/login/", {"email": email, "password": password}, format="json")


class TestAuthentication:
    def test_login_fails_closed_with_a_clean_503(self, cache_down, api_client, student):
        response = _login(api_client, student.email, "StudentPass123!")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "service_unavailable"

    def test_refresh_still_works(self, settings, api_client, student):
        tokens = _login(api_client, student.email, "StudentPass123!").json()
        settings.CACHES = {
            "default": {"BACKEND": "apps.core.tests.test_cache_outage.BrokenCache"}
        }
        refresh = tokens.get("refresh") or tokens["tokens"]["refresh"]
        response = api_client.post("/api/v1/auth/refresh/", {"refresh": refresh}, format="json")
        assert response.status_code == 200

    def test_revoked_refresh_token_stays_revoked(self, settings, api_client, auth_client, student):
        """The blacklist is in the database, so revocation does not depend on Redis."""
        tokens = _login(api_client, student.email, "StudentPass123!").json()
        refresh = tokens.get("refresh") or tokens["tokens"]["refresh"]
        auth_client(student).post("/api/v1/auth/logout/", {"refresh": refresh}, format="json")
        settings.CACHES = {
            "default": {"BACKEND": "apps.core.tests.test_cache_outage.BrokenCache"}
        }
        response = api_client.post("/api/v1/auth/refresh/", {"refresh": refresh}, format="json")
        assert response.status_code == 401


class TestEntitlement:
    def test_subscribed_student_keeps_access(self, plan, student, course, active_subscription, cache_down, auth_client):
        body = auth_client(student).get(f"/api/v1/courses/{course.slug}/access/").json()
        assert body["allowed"] is True

    def test_cache_failure_never_grants_access(self, cache_down, auth_client, student, course):
        body = auth_client(student).get(f"/api/v1/courses/{course.slug}/access/").json()
        assert body["allowed"] is False

    def test_course_catalogue_still_loads(self, cache_down, auth_client, student, course):
        assert auth_client(student).get("/api/v1/courses/").status_code == 200

    def test_cancellation_completes_despite_failed_invalidation(
        self, student, course, active_subscription, cache_down
    ):
        from apps.subscriptions.services import can_user_access_course
        from apps.subscriptions.services_lifecycle import cancel_subscription

        cancel_subscription(subscription=active_subscription, immediate=True)
        active_subscription.refresh_from_db()
        assert active_subscription.status == "cancelled"
        assert not can_user_access_course(student, course).allowed

    def test_plan_edit_saves_despite_failed_generation_bump(self, plan, course, cache_down):
        plan.courses.remove(course)
        plan.is_all_access = True
        plan.save()
        plan.refresh_from_db()
        assert plan.is_all_access and not plan.courses.exists()


class TestPlaybackAndLeaderboard:
    def test_entitled_playback_still_issues_a_token(self, student, lesson, active_subscription, cache_down, auth_client):
        response = auth_client(student).get(f"/api/v1/videos/{lesson.video.playback_uid}/playback/")
        assert response.status_code == 200, response.data
        assert response.data["token"]

    def test_unentitled_playback_is_still_refused(self, cache_down, auth_client, student, lesson):
        response = auth_client(student).get(f"/api/v1/videos/{lesson.video.playback_uid}/playback/")
        assert response.status_code == 403

    def test_leaderboard_top_still_loads(self, db, cache_down, api_client):
        assert api_client.get("/api/v1/leaderboard/top/").status_code == 200
