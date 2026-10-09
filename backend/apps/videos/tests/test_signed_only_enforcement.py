"""Signed-only enforcement on Cloudflare, and playback tokens bounded by access.

Regressions:

* ``register_video`` swallowed a failed ``requireSignedURLs`` update yet stored
  the video as signed-only, and nothing retried it.  The asset stayed public on
  Cloudflare while a playback token's ``sub`` claim tells any student its raw id.
* ``sync_video_metadata`` crashed (``TypeError``) on Cloudflare's real payload,
  whose ``status`` is an object, so no upload ever became READY.
* A playback token outlived the subscription that justified it by up to the
  full token TTL.
"""

from __future__ import annotations

from datetime import timedelta
from unittest import mock

import jwt
import pytest
from django.utils import timezone

from apps.core.constants import VideoStatus
from apps.videos.cloudflare import CloudflareStreamError
from apps.videos.models import Video
from apps.videos.services import register_video, sync_video_metadata
from conftest import make_plan, make_subscription


def playback_url(video):
    return f"/api/v1/videos/{video.playback_uid}/playback/"


@pytest.fixture
def cloudflare(monkeypatch):
    fake = mock.MagicMock()
    fake.get_video.return_value = {"status": {"state": "ready"}, "duration": 60}
    monkeypatch.setattr("apps.videos.services.client", fake)
    return fake


# --------------------------------------------------------------------------- #
# Enforcement state
# --------------------------------------------------------------------------- #
def test_failed_enforcement_is_recorded_not_assumed(db, cloudflare):
    cloudflare.update_video.side_effect = CloudflareStreamError("API down")
    video = register_video(title="T", cloudflare_video_id="cf-1")
    assert video.require_signed_urls is False


def test_unsecured_video_never_gets_a_playback_token(
    jwt_client, student, lesson, active_subscription
):
    Video.objects.filter(pk=lesson.video_id).update(require_signed_urls=False)
    response = jwt_client(student).get(playback_url(lesson.video))
    assert response.status_code == 503
    assert response.data["error"]["code"] == "playback_unavailable"
    assert "token" not in response.data


def test_sync_retries_enforcement_without_duplicating_rows(db, cloudflare):
    cloudflare.update_video.side_effect = CloudflareStreamError("API down")
    video = register_video(title="T", cloudflare_video_id="cf-2")
    assert video.require_signed_urls is False

    cloudflare.update_video.side_effect = None
    sync_video_metadata(video)
    video.refresh_from_db()
    assert video.require_signed_urls is True
    cloudflare.update_video.assert_called_with("cf-2", require_signed_urls=True)
    assert Video.objects.filter(cloudflare_video_id="cf-2").count() == 1


def test_sync_reenforces_when_cloudflare_reports_the_asset_public(db, cloudflare, video):
    cloudflare.get_video.return_value = {
        "status": {"state": "ready"}, "requireSignedURLs": False,
    }
    sync_video_metadata(video)
    cloudflare.update_video.assert_called_with(
        video.cloudflare_video_id, require_signed_urls=True
    )
    video.refresh_from_db()
    assert video.require_signed_urls is True


def test_sync_marks_video_unsecured_when_reenforcement_fails(db, cloudflare, video):
    cloudflare.get_video.return_value = {
        "status": {"state": "ready"}, "requireSignedURLs": False,
    }
    cloudflare.update_video.side_effect = CloudflareStreamError("API down")
    sync_video_metadata(video)
    video.refresh_from_db()
    assert video.require_signed_urls is False


def test_sync_reads_cloudflares_object_status(db, cloudflare):
    video = Video.objects.create(title="T", cloudflare_video_id="cf-3")
    cloudflare.get_video.return_value = {
        "status": {"state": "ready"}, "duration": 75, "requireSignedURLs": True,
    }
    sync_video_metadata(video)
    video.refresh_from_db()
    assert video.status == VideoStatus.READY
    assert video.duration_seconds == 75

    cloudflare.get_video.return_value = {
        "status": {"state": "error", "errorReasonText": "bad codec"},
        "requireSignedURLs": True,
    }
    sync_video_metadata(video)
    video.refresh_from_db()
    assert video.status == VideoStatus.FAILED
    assert video.processing_error == "bad codec"


def test_periodic_sync_picks_up_unsecured_ready_videos(db, cloudflare, video):
    from apps.core.tasks import sync_pending_videos

    Video.objects.filter(pk=video.pk).update(require_signed_urls=False)
    cloudflare.get_video.return_value = {"status": {"state": "ready"}}
    assert sync_pending_videos() == 1
    video.refresh_from_db()
    assert video.require_signed_urls is True


# --------------------------------------------------------------------------- #
# Token lifetime never exceeds the access behind it
# --------------------------------------------------------------------------- #
def _token_claims(response):
    return jwt.decode(response.data["token"], options={"verify_signature": False})


def test_token_expires_with_the_subscription(jwt_client, student, lesson, plan, settings):
    sub = make_subscription(student, plan, payment_reference="p")
    sub.end_date = timezone.now() + timedelta(seconds=100)
    sub.save(update_fields=["end_date"])

    response = jwt_client(student).get(playback_url(lesson.video))
    assert response.status_code == 200, response.data
    assert response.data["expires_in"] <= 100
    assert _token_claims(response)["exp"] <= int(sub.end_date.timestamp())


def test_overlapping_coverage_keeps_the_full_token_ttl(
    jwt_client, student, lesson, plan, course, settings
):
    """A short subscription must not cut the token when a longer one also covers
    the course."""
    short = make_subscription(student, plan, payment_reference="short")
    short.end_date = timezone.now() + timedelta(seconds=100)
    short.save(update_fields=["end_date"])
    make_subscription(
        student, make_plan(name="AA", slug="aa", is_all_access=True),
        payment_reference="long", ends_in_days=30,
    )

    response = jwt_client(student).get(playback_url(lesson.video))
    assert response.status_code == 200, response.data
    assert response.data["expires_in"] == settings.CLOUDFLARE_PLAYBACK_TOKEN_TTL


def test_non_subscription_access_keeps_the_full_token_ttl(
    jwt_client, instructor, lesson, settings
):
    response = jwt_client(instructor).get(playback_url(lesson.video))
    assert response.status_code == 200, response.data
    assert response.data["expires_in"] == settings.CLOUDFLARE_PLAYBACK_TOKEN_TTL


def test_unknown_video_id_is_404(jwt_client, student):
    response = jwt_client(student).get("/api/v1/videos/00000000-0000-0000-0000-000000000000/playback/")
    assert response.status_code == 404
