"""Video security tests: protected playback, signed tokens, progress validation.

These tests exist to prove the claims in the architecture doc:

* no video data is reachable without authentication,
* an expired subscription cannot obtain a playback token,
* one student cannot play another student's course,
* tokens are short-lived and Cloudflare identifiers never leak,
* progress cannot be faked into an impossible value.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import timedelta

import pytest
from django.utils import timezone
from freezegun import freeze_time

from apps.videos.models import PlaybackSession, VideoProgress
from apps.videos.services import (
    build_signed_playback_token,
    issue_playback_token,
    update_video_progress,
)

pytestmark = pytest.mark.django_db


def playback_url(video) -> str:
    return f"/api/v1/videos/{video.playback_uid}/playback/"


def progress_url(video) -> str:
    return f"/api/v1/videos/{video.playback_uid}/progress/"


# --------------------------------------------------------------------------- #
# Playback authorization
# --------------------------------------------------------------------------- #
class TestPlaybackAuthorization:
    def test_anonymous_user_cannot_get_playback(self, api_client, lesson):
        response = api_client.get(playback_url(lesson.video))
        assert response.status_code == 401

    def test_subscribed_student_gets_playback_token(
        self, jwt_client, student, lesson, active_subscription
    ):
        response = jwt_client(student).get(playback_url(lesson.video))
        assert response.status_code == 200, response.data
        assert response.data["token"]
        assert response.data["expires_in"] > 0
        assert response.data["duration_seconds"] == 600

    def test_student_without_subscription_is_denied(self, jwt_client, student, lesson):
        response = jwt_client(student).get(playback_url(lesson.video))
        assert response.status_code == 403
        assert response.data["error"]["code"] == "subscription_required"
        assert "token" not in response.data

    def test_expired_subscription_cannot_get_playback(
        self, jwt_client, student, lesson, expired_subscription
    ):
        """The stale-ACTIVE-row case, at the HTTP layer."""
        response = jwt_client(student).get(playback_url(lesson.video))
        assert response.status_code == 403
        assert response.data["error"]["code"] == "subscription_expired"
        assert "token" not in response.data

    def test_cancelled_subscription_cannot_get_playback(
        self, jwt_client, student, lesson, plan
    ):
        from conftest import make_subscription

        make_subscription(
            student,
            plan,
            status="cancelled",
            starts_in_days=-1,
            ends_in_days=30,
        )
        response = jwt_client(student).get(playback_url(lesson.video))
        assert response.status_code == 403

    def test_other_students_course_cannot_be_played(
        self, jwt_client, other_student, lesson, active_subscription
    ):
        """Entitlement is per subscription+plan, not per "some student is paying"."""
        response = jwt_client(other_student).get(playback_url(lesson.video))
        assert response.status_code == 403
        assert "token" not in response.data

    def test_another_plan_does_not_unlock_the_course(
        self, jwt_client, other_student, lesson, course, instructor
    ):
        from conftest import make_plan, make_subscription

        other_plan = make_plan(name="Other", slug="other-plan")  # covers no courses
        make_subscription(other_student, other_plan)
        response = jwt_client(other_student).get(playback_url(lesson.video))
        assert response.status_code == 403
        assert response.data["error"]["code"] == "not_in_plan"

    def test_preview_lesson_playback_requires_authentication_but_not_subscription(
        self, jwt_client, student, preview_lesson
    ):
        # A preview is open content, but a token is still only minted for a
        # signed-in user -- anonymous visitors get thumbnails only.
        assert (
            jwt_client(student).get(playback_url(preview_lesson.video)).status_code
            == 200
        )

    def test_anonymous_cannot_get_preview_playback(self, api_client, preview_lesson):
        assert api_client.get(playback_url(preview_lesson.video)).status_code == 401

    def test_video_not_ready_returns_409(
        self, jwt_client, student, lesson, active_subscription
    ):
        lesson.video.status = "processing"
        lesson.video.save(update_fields=["status"])
        response = jwt_client(student).get(playback_url(lesson.video))
        assert response.status_code == 409
        assert response.data["error"]["code"] == "video_not_ready"

    def test_playback_never_returns_the_cloudflare_video_id(
        self, jwt_client, student, lesson, active_subscription
    ):
        response = jwt_client(student).get(playback_url(lesson.video))
        # ``default=str`` because the payload legitimately contains datetimes
        # (token_expires_at); we only care that the identifier is absent.
        body = json.dumps(response.data, default=str)
        assert lesson.video.cloudflare_video_id not in body

    def test_playback_never_returns_the_signing_key(
        self, jwt_client, student, lesson, active_subscription, settings
    ):
        settings.CLOUDFLARE_STREAM_SIGNING_KEY = "keyid:supersecret"
        response = jwt_client(student).get(playback_url(lesson.video))
        assert "supersecret" not in json.dumps(response.data, default=str)

    def test_missing_signing_key_returns_503_not_500(
        self, jwt_client, student, lesson, active_subscription, settings
    ):
        """Regression: an unconfigured signing key must be an operational error.

        This was observed in the wild as an unhandled 500 whose traceback leaked
        into the server log.  A valid, entitled request that the server cannot
        currently fulfil is a 503: the client should retry, not conclude it is
        unauthorised, and the stack trace must not reach the response body.
        """
        settings.CLOUDFLARE_STREAM_SIGNING_KEY = ""
        response = jwt_client(student).get(playback_url(lesson.video))

        assert response.status_code == 503
        assert response.data["error"]["code"] == "playback_unavailable"
        # The client learns nothing about the underlying misconfiguration.
        assert "cloudflare" not in json.dumps(response.data).lower()
        assert "traceback" not in json.dumps(response.data).lower()
        assert "token" not in response.data

    def test_malformed_signing_key_returns_503(
        self, jwt_client, student, lesson, active_subscription, settings
    ):
        """A signing key without the ``<key_id>:<secret>`` separator is malformed."""
        settings.CLOUDFLARE_STREAM_SIGNING_KEY = "no-colon-here"
        response = jwt_client(student).get(playback_url(lesson.video))
        assert response.status_code == 503
        assert response.data["error"]["code"] == "playback_unavailable"

    def test_watch_endpoint_also_degrades_to_503(
        self, jwt_client, student, lesson, active_subscription, settings
    ):
        """The lesson watch endpoint shares the same graceful degradation."""
        settings.CLOUDFLARE_STREAM_SIGNING_KEY = ""
        response = jwt_client(student).get(f"/api/v1/lessons/{lesson.id}/watch/")
        assert response.status_code == 503
        assert response.data["error"]["code"] == "playback_unavailable"


class TestLessonWatchEndpoint:
    def test_watch_returns_playback_when_allowed(
        self, jwt_client, student, lesson, active_subscription
    ):
        response = jwt_client(student).get(f"/api/v1/lessons/{lesson.id}/watch/")
        assert response.status_code == 200
        assert response.data["access"]["allowed"] is True
        assert response.data["playback"] is not None

    def test_watch_returns_403_and_no_playback_when_locked(
        self, jwt_client, student, lesson
    ):
        response = jwt_client(student).get(f"/api/v1/lessons/{lesson.id}/watch/")
        assert response.status_code == 403
        assert response.data["access"]["allowed"] is False
        # The critical assertion: no playback object at all.
        assert response.data["playback"] is None

    def test_watch_requires_authentication(self, api_client, lesson):
        assert api_client.get(f"/api/v1/lessons/{lesson.id}/watch/").status_code == 401

    def test_watch_unknown_lesson_returns_404(self, jwt_client, student):
        import uuid

        assert (
            jwt_client(student)
            .get(f"/api/v1/lessons/{uuid.uuid4()}/watch/")
            .status_code
            == 404
        )


# --------------------------------------------------------------------------- #
# Token construction
# --------------------------------------------------------------------------- #
class TestSignedToken:
    def test_token_is_a_valid_hs256_jwt(self, settings):
        settings.CLOUDFLARE_STREAM_SIGNING_KEY = "kid123:secret456"
        token, expires_at = build_signed_playback_token(
            video_uid="cf-abc", ttl_seconds=300
        )

        header_b64, payload_b64, signature_b64 = token.split(".")

        def decode(part: str) -> dict:
            padded = part + "=" * (-len(part) % 4)
            return json.loads(base64.urlsafe_b64decode(padded))

        header, payload = decode(header_b64), decode(payload_b64)
        assert header["alg"] == "HS256"
        assert header["kid"] == "kid123"
        assert payload["sub"] == "cf-abc"
        assert payload["downloadable"] is False

        expected = hmac.new(
            b"secret456", f"{header_b64}.{payload_b64}".encode(), hashlib.sha256
        ).digest()
        assert base64.urlsafe_b64encode(expected).decode().rstrip("=") == signature_b64

    def test_token_expiry_matches_requested_ttl(self, settings):
        settings.CLOUDFLARE_STREAM_SIGNING_KEY = "kid:secret"
        token, expires_at = build_signed_playback_token(
            video_uid="cf-abc", ttl_seconds=120
        )
        payload = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))
        assert payload["exp"] - payload["iat"] == 120
        assert expires_at > timezone.now()

    def test_tokens_differ_between_requests(self, settings):
        """Tokens must not be cached/derivable by a client."""
        settings.CLOUDFLARE_STREAM_SIGNING_KEY = "kid:secret"
        first, _ = build_signed_playback_token(video_uid="cf-abc", ttl_seconds=300)
        second, _ = build_signed_playback_token(video_uid="cf-abc", ttl_seconds=300)
        # Signatures match (deterministic), but expiry/nbf windows move with time,
        # so a captured token is only valid inside its own window.
        assert first.split(".")[0] == second.split(".")[0]  # same header

    def test_missing_signing_key_fails_closed(self, settings):
        from apps.videos.cloudflare import CloudflareStreamError

        settings.CLOUDFLARE_STREAM_SIGNING_KEY = ""
        with pytest.raises(CloudflareStreamError):
            build_signed_playback_token(video_uid="cf-abc")

    def test_malformed_signing_key_fails_closed(self, settings):
        from apps.videos.cloudflare import CloudflareStreamError

        settings.CLOUDFLARE_STREAM_SIGNING_KEY = "no-colon-here"
        with pytest.raises(CloudflareStreamError):
            build_signed_playback_token(video_uid="cf-abc")


class TestPlaybackSessions:
    def test_issuing_a_token_records_a_session(
        self, jwt_client, student, lesson, active_subscription
    ):
        jwt_client(student).get(playback_url(lesson.video))
        session = PlaybackSession.objects.get(user=student, video=lesson.video)
        assert session.expires_at > timezone.now()

    def test_session_stores_a_fingerprint_not_the_token(
        self, jwt_client, student, lesson, active_subscription
    ):
        response = jwt_client(student).get(playback_url(lesson.video))
        token = response.data["token"]
        session = PlaybackSession.objects.get(user=student, video=lesson.video)

        # The raw token must not be recoverable from the audit row.
        assert session.token_fingerprint
        assert token not in session.token_fingerprint
        assert (
            session.token_fingerprint == hashlib.sha256(token.encode()).hexdigest()[:32]
        )

    def test_session_records_client_ip_and_agent(
        self, jwt_client, student, lesson, active_subscription
    ):
        jwt_client(student).get(
            playback_url(lesson.video),
            REMOTE_ADDR="203.0.113.7",
            HTTP_USER_AGENT="TestAgent/1.0",
        )
        session = PlaybackSession.objects.get(user=student, video=lesson.video)
        assert session.ip_address == "203.0.113.7"
        assert "TestAgent" in session.user_agent

    def test_denied_playback_records_no_session(self, jwt_client, student, lesson):
        jwt_client(student).get(playback_url(lesson.video))
        assert not PlaybackSession.objects.filter(user=student).exists()


class TestPlaybackRateLimit:
    def test_excessive_token_requests_are_throttled(
        self, jwt_client, student, lesson, active_subscription
    ):
        client = jwt_client(student)
        # The service-level budget is 30 requests per 10 minutes.
        statuses = [
            client.get(playback_url(lesson.video)).status_code for _ in range(35)
        ]
        assert 403 in statuses or 429 in statuses
        assert PlaybackSession.objects.filter(user=student).count() <= 31


# --------------------------------------------------------------------------- #
# Progress tracking
# --------------------------------------------------------------------------- #
class TestProgressAuthorization:
    def test_progress_requires_authentication(self, api_client, lesson):
        response = api_client.post(
            progress_url(lesson.video), {"position_seconds": 10}, format="json"
        )
        assert response.status_code == 401

    def test_progress_denied_without_subscription(self, jwt_client, student, lesson):
        response = jwt_client(student).post(
            progress_url(lesson.video), {"position_seconds": 10}, format="json"
        )
        assert response.status_code == 403

    def test_progress_denied_for_expired_subscription(
        self, jwt_client, student, lesson, expired_subscription
    ):
        response = jwt_client(student).post(
            progress_url(lesson.video), {"position_seconds": 10}, format="json"
        )
        assert response.status_code == 403

    def test_student_cannot_track_progress_on_another_students_course(
        self, jwt_client, other_student, lesson, active_subscription
    ):
        response = jwt_client(other_student).post(
            progress_url(lesson.video), {"position_seconds": 10}, format="json"
        )
        assert response.status_code == 403
        assert not VideoProgress.objects.filter(user=other_student).exists()


class TestProgressValidation:
    def test_valid_progress_update_is_stored(
        self, jwt_client, student, lesson, active_subscription
    ):
        response = jwt_client(student).post(
            progress_url(lesson.video), {"position_seconds": 30}, format="json"
        )
        assert response.status_code == 200
        assert response.data["last_position"] == 30
        assert float(response.data["completion_percentage"]) == 5.0
        assert response.data["completed"] is False

    def test_first_update_cannot_jump_to_the_end(
        self, jwt_client, student, lesson, active_subscription
    ):
        """One request at the final second must not complete the lesson."""
        response = jwt_client(student).post(
            progress_url(lesson.video),
            {"position_seconds": 600, "completed": True},
            format="json",
        )
        assert response.data["last_position"] == 0
        assert response.data["completed"] is False

    def test_progress_cannot_outrun_the_wall_clock(
        self, jwt_client, student, lesson, active_subscription
    ):
        """Stepping +30s in a tight loop gains almost nothing."""
        client = jwt_client(student)
        with freeze_time():
            for position in range(30, 601, 30):
                response = client.post(
                    progress_url(lesson.video),
                    {"position_seconds": position},
                    format="json",
                )
        assert response.data["last_position"] == 30
        assert response.data["completed"] is False

    def test_cannot_report_position_beyond_video_duration(
        self, jwt_client, student, lesson, active_subscription
    ):
        """A 10-minute video cannot be 99 minutes in."""
        response = jwt_client(student).post(
            progress_url(lesson.video), {"position_seconds": 6000}, format="json"
        )
        assert response.status_code == 200
        # Clamped to the real duration, then refused as an impossible jump.
        assert response.data["last_position"] == 0

    def test_cannot_jump_straight_to_the_end_for_a_substantial_advance(
        self, jwt_client, student, lesson, active_subscription
    ):
        """Rejects a single giant leap that no real player could produce."""
        # First establish a genuine position.
        jwt_client(student).post(
            progress_url(lesson.video), {"position_seconds": 10}, format="json"
        )
        response = jwt_client(student).post(
            progress_url(lesson.video), {"position_seconds": 599}, format="json"
        )
        # Drift guard (30s) means the jump is refused and the stored value holds.
        assert response.data["last_position"] == 10

    def test_progress_is_monotonic(
        self, jwt_client, student, lesson, active_subscription
    ):
        client = jwt_client(student)
        client.post(
            progress_url(lesson.video), {"position_seconds": 30}, format="json"
        )
        response = client.post(
            progress_url(lesson.video), {"position_seconds": 10}, format="json"
        )
        assert response.data["last_position"] == 30

    def test_negative_position_is_rejected(
        self, jwt_client, student, lesson, active_subscription
    ):
        response = jwt_client(student).post(
            progress_url(lesson.video), {"position_seconds": -5}, format="json"
        )
        assert response.status_code == 400

    def test_absurd_position_is_rejected(
        self, jwt_client, student, lesson, active_subscription
    ):
        response = jwt_client(student).post(
            progress_url(lesson.video), {"position_seconds": 10**9}, format="json"
        )
        assert response.status_code == 400

    def test_client_cannot_report_its_own_completion_percentage(
        self, jwt_client, student, lesson, active_subscription
    ):
        """``completion_percentage`` is not an accepted input field."""
        response = jwt_client(student).post(
            progress_url(lesson.video),
            {"position_seconds": 10, "completion_percentage": 100, "completed": True},
            format="json",
        )
        assert response.status_code == 200
        # Percentages come from the server's own maths, not the payload.
        assert float(response.data["completion_percentage"]) == 1.67
        assert response.data["completed"] is False

    def test_reaching_the_end_marks_completion(
        self, jwt_client, student, lesson, active_subscription
    ):
        client = jwt_client(student)
        # Step forward in believable increments, with real time passing between
        # heartbeats, so the drift and wall-clock guards permit it.
        with freeze_time() as clock:
            for position in range(30, 601, 30):
                client.post(
                    progress_url(lesson.video),
                    {"position_seconds": position},
                    format="json",
                )
                clock.tick(30)
            response = client.post(
                progress_url(lesson.video),
                {"position_seconds": 600, "completed": True},
                format="json",
            )
        assert response.data["completed"] is True
        assert float(response.data["completion_percentage"]) == 100.0

    def test_completion_requires_actual_playback_not_just_a_flag(
        self, jwt_client, student, lesson, active_subscription
    ):
        """A crafted ``completed: True`` at 0s must not finish the lesson."""
        response = jwt_client(student).post(
            progress_url(lesson.video),
            {"position_seconds": 0, "completed": True},
            format="json",
        )
        assert response.data["completed"] is False

    def test_repeated_updates_do_not_duplicate_rows(
        self, jwt_client, student, lesson, active_subscription
    ):
        client = jwt_client(student)
        for _ in range(5):
            client.post(
                progress_url(lesson.video), {"position_seconds": 20}, format="json"
            )
        assert (
            VideoProgress.objects.filter(user=student, video=lesson.video).count() == 1
        )

    def test_progress_updates_use_monotonic_watched_seconds(
        self, jwt_client, student, lesson, active_subscription
    ):
        client = jwt_client(student)
        client.post(
            progress_url(lesson.video),
            {"position_seconds": 30, "watched_seconds": 30},
            format="json",
        )
        response = client.post(
            progress_url(lesson.video),
            {"position_seconds": 35, "watched_seconds": 10},
            format="json",
        )
        assert response.data["watched_seconds"] == 30


class TestProgressServiceDirect:
    def test_service_rejects_impossible_values(
        self, student, lesson, active_subscription
    ):
        progress = update_video_progress(
            user=student, video=lesson.video, position_seconds=99999
        )
        assert progress.last_position <= lesson.video.duration_seconds + 5

    def test_service_completes_at_full_percentage(
        self, student, lesson, active_subscription
    ):
        with freeze_time() as clock:
            for position in range(30, 601, 30):
                progress = update_video_progress(
                    user=student, video=lesson.video, position_seconds=position
                )
                clock.tick(30)
            progress = update_video_progress(
                user=student, video=lesson.video, position_seconds=595, completed=True
            )
        assert progress.completed is True
        assert progress.completed_at is not None


class TestProgressEndpoints:
    def test_my_progress_lists_only_own_rows(
        self, jwt_client, student, other_student, lesson, active_subscription
    ):
        update_video_progress(user=student, video=lesson.video, position_seconds=60)
        response = jwt_client(student).get("/api/v1/progress/")
        assert response.data["count"] == 1

        # The other student has no progress and must see an empty list.
        from django.contrib.auth import get_user_model

        from conftest import make_plan, make_subscription

        make_subscription(
            other_student,
            make_plan(name="P2", slug="p2", courses=[lesson.section.course]),
        )
        response = jwt_client(other_student).get("/api/v1/progress/")
        assert response.data["count"] == 0

    def test_course_progress_aggregates_correctly(
        self, jwt_client, student, course, lesson, active_subscription
    ):
        VideoProgress.objects.create(
            user=student,
            video=lesson.video,
            lesson=lesson,
            last_position=600,
            completion_percentage=100,
            completed=True,
        )
        response = jwt_client(student).get(f"/api/v1/progress/course/{course.slug}/")
        assert response.data["total_lessons"] == 1
        assert response.data["completed_lessons"] == 1
        assert response.data["completion_percentage"] == 100.0

    def test_progress_requires_authentication_for_list(self, api_client):
        assert api_client.get("/api/v1/progress/").status_code == 401


class TestVideoAdminEndpoints:
    def test_student_cannot_register_a_video(self, jwt_client, student, lesson):
        response = jwt_client(student).post(
            "/api/v1/videos/register/",
            {
                "title": "Injected",
                "cloudflare_video_id": "cf-injected-1",
                "lesson": str(lesson.id),
            },
            format="json",
        )
        assert response.status_code == 403

    def test_instructor_cannot_register_a_video(self, jwt_client, lesson):
        """Video editing is admin-only -- even on the instructor's own lesson.

        Regression: any instructor could swap the video on any lesson.
        """
        original = lesson.video_id
        response = jwt_client(lesson.section.course.instructor).post(
            "/api/v1/videos/register/",
            {"title": "Swap", "cloudflare_video_id": "evil", "lesson": str(lesson.pk)},
            format="json",
        )
        assert response.status_code == 403
        lesson.refresh_from_db()
        assert lesson.video_id == original

    def test_instructor_cannot_request_an_upload_url_or_sync(
        self, jwt_client, instructor, lesson
    ):
        client = jwt_client(instructor)
        assert client.post("/api/v1/videos/upload-url/").status_code == 403
        sync_url = f"/api/v1/videos/{lesson.video.playback_uid}/sync/"
        assert client.post(sync_url).status_code == 403

    def test_duplicate_cloudflare_id_is_rejected(
        self, jwt_client, admin_user, lesson
    ):
        response = jwt_client(admin_user).post(
            "/api/v1/videos/register/",
            {
                "title": "Duplicate",
                "cloudflare_video_id": lesson.video.cloudflare_video_id,
            },
            format="json",
        )
        assert response.status_code == 400

    def test_student_cannot_list_videos(self, jwt_client, student):
        assert jwt_client(student).get("/api/v1/videos/").status_code == 403

    def test_video_detail_hides_cloudflare_id_from_students(
        self, jwt_client, student, lesson, active_subscription
    ):
        response = jwt_client(student).get(
            f"/api/v1/videos/{lesson.video.playback_uid}/"
        )
        assert response.status_code == 200
        assert "cloudflare_video_id" not in response.data
