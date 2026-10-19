"""W3 (upload URL throttle/authz) and L3 (registration uniqueness race)."""

from unittest import mock

import pytest
from django.core.cache import cache
from django.db import IntegrityError
from rest_framework.throttling import ScopedRateThrottle

from apps.videos.models import Video
from apps.videos.services import register_video

pytestmark = pytest.mark.django_db

UPLOAD = "/api/v1/videos/upload-url/"
REGISTER = "/api/v1/videos/register/"


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def fake_cf(monkeypatch):
    fake = mock.MagicMock()
    fake.create_direct_upload.return_value = {"uploadURL": "https://up.example/x", "uid": "cf-uid-1"}
    monkeypatch.setattr("apps.videos.cloudflare.client", fake)
    return fake


class TestUploadUrl:
    def test_instructor_with_a_course_gets_a_capped_url(self, jwt_client, instructor, course, fake_cf, settings):
        r = jwt_client(instructor).post(UPLOAD)
        assert r.status_code == 200 and r.data["upload_url"]
        kwargs = fake_cf.create_direct_upload.call_args.kwargs
        assert kwargs["creator"] == str(instructor.pk)
        assert kwargs["max_duration_seconds"] == settings.VIDEO_MAX_DURATION_SECONDS

    def test_admin_allowed_without_owning_a_course(self, jwt_client, admin_user, fake_cf):
        assert jwt_client(admin_user).post(UPLOAD).status_code == 200

    def test_instructor_without_any_course_is_refused(self, jwt_client, instructor, fake_cf):
        assert jwt_client(instructor).post(UPLOAD).status_code == 403
        fake_cf.create_direct_upload.assert_not_called()

    def test_student_and_anonymous_refused(self, jwt_client, api_client, student, fake_cf):
        assert jwt_client(student).post(UPLOAD).status_code == 403
        assert api_client.post(UPLOAD).status_code in (401, 403)
        fake_cf.create_direct_upload.assert_not_called()

    def test_throttle_blocks_after_limit(self, jwt_client, instructor, course, fake_cf, monkeypatch):
        monkeypatch.setattr(
            ScopedRateThrottle, "THROTTLE_RATES",
            {**ScopedRateThrottle.THROTTLE_RATES, "video_upload": "2/hour"},
        )
        client = jwt_client(instructor)
        codes = [client.post(UPLOAD).status_code for _ in range(4)]
        assert codes == [200, 200, 429, 429]
        assert fake_cf.create_direct_upload.call_count == 2

    def test_throttle_is_per_user(self, jwt_client, instructor, admin_user, course, fake_cf, monkeypatch):
        monkeypatch.setattr(
            ScopedRateThrottle, "THROTTLE_RATES",
            {**ScopedRateThrottle.THROTTLE_RATES, "video_upload": "1/hour"},
        )
        assert jwt_client(instructor).post(UPLOAD).status_code == 200
        assert jwt_client(admin_user).post(UPLOAD).status_code == 200

    def test_limiter_outage_fails_closed(self, jwt_client, instructor, course, fake_cf):
        with mock.patch.object(cache, "get", side_effect=ConnectionError("down")):
            assert jwt_client(instructor).post(UPLOAD).status_code == 503
        fake_cf.create_direct_upload.assert_not_called()

    def test_provider_error_is_a_clean_502(self, jwt_client, instructor, course, fake_cf):
        from apps.videos.cloudflare import CloudflareStreamError

        fake_cf.create_direct_upload.side_effect = CloudflareStreamError("boom")
        assert jwt_client(instructor).post(UPLOAD).status_code == 502


class TestRegistrationUniqueness:
    def test_first_registration_then_duplicate_is_a_409_at_service_level(self, admin_user, monkeypatch):
        monkeypatch.setattr("apps.videos.services.client", mock.MagicMock(get_video=lambda _id: {}))
        monkeypatch.setattr("apps.videos.services._enforce_signed_only", lambda v: True)
        register_video(title="a", cloudflare_video_id="cf-dup", owner=admin_user)
        from apps.core.exceptions import ConflictError

        with pytest.raises(ConflictError):
            register_video(title="b", cloudflare_video_id="cf-dup", owner=admin_user)
        assert Video.objects.filter(cloudflare_video_id="cf-dup").count() == 1

    def test_race_lost_after_precheck_is_a_409_not_500(self, admin_user, monkeypatch):
        """The serializer pre-check passed, then another request inserted first."""
        monkeypatch.setattr("apps.videos.services.client", mock.MagicMock(get_video=lambda _id: {}))
        monkeypatch.setattr("apps.videos.services._enforce_signed_only", lambda v: True)
        Video.objects.create(title="winner", cloudflare_video_id="cf-race")
        from apps.core.exceptions import ConflictError

        with pytest.raises(ConflictError):
            register_video(title="loser", cloudflare_video_id="cf-race", owner=admin_user)

    def test_unrelated_integrity_error_is_not_reported_as_duplicate(self, admin_user, monkeypatch):
        monkeypatch.setattr("apps.videos.services.client", mock.MagicMock(get_video=lambda _id: {}))
        with mock.patch.object(Video.objects, "create", side_effect=IntegrityError("other")):
            with pytest.raises(IntegrityError):
                register_video(title="x", cloudflare_video_id="cf-unique", owner=admin_user)

    def test_api_duplicate_is_a_400_from_the_precheck(self, jwt_client, admin_user, lesson):
        r = jwt_client(admin_user).post(
            REGISTER,
            {"title": "t", "cloudflare_video_id": lesson.video.cloudflare_video_id},
            format="json",
        )
        assert r.status_code == 400
