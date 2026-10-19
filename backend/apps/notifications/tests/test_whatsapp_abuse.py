"""W2: paid-message abuse controls on the WhatsApp linking endpoint."""

from unittest import mock

import pytest
from django.core.cache import cache
from rest_framework.throttling import ScopedRateThrottle

from apps.notifications.whatsapp import consent
from apps.users.models import User

LINK = "/api/v1/notifications/whatsapp/link/"

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


def _verified(email):
    return User.objects.create_user(
        email=email, password="Str0ng-Passphrase-9", name="U", is_email_verified=True
    )


def _link(client, phone="+919876543210"):
    return client.post(LINK, {"phone": phone, "consent": True}, format="json")


def test_unverified_email_cannot_request_code(wa_on, auth_client, student, mock_post):
    assert student.is_email_verified is False
    response = _link(auth_client(student))
    assert response.status_code == 403
    mock_post.assert_not_called()


def test_verified_email_can_request_code(wa_on, auth_client, mock_post):
    user = _verified("v@test.local")
    assert _link(auth_client(user)).status_code == 202
    mock_post.assert_called_once()


def test_invalid_number_rejected_before_budget_is_spent(wa_on, auth_client, mock_post, settings):
    user = _verified("bad@test.local")
    assert _link(auth_client(user), phone="12345").status_code == 400
    assert cache.get(f"wa:otp:global:{__import__('django').utils.timezone.now().date().isoformat()}") is None


def test_global_daily_cap_blocks_further_sends(wa_on, auth_client, mock_post, settings):
    settings.WHATSAPP_OTP_DAILY_CAP = 2
    results = []
    for i in range(4):
        user = _verified(f"cap{i}@test.local")
        results.append(_link(auth_client(user), phone=f"+91987650000{i}").status_code)
    assert results == [202, 202, 503, 503]
    assert mock_post.call_count == 2


def test_cap_applies_equally_when_number_belongs_to_someone_else(
    wa_on, auth_client, mock_post, settings
):
    """The 'number taken' branch must not be a cheaper, distinguishable path."""
    settings.WHATSAPP_OTP_DAILY_CAP = 1
    first = _verified("one@test.local")
    assert _link(auth_client(first)).status_code == 202
    second = _verified("two@test.local")
    assert _link(auth_client(second)).status_code == 503


def test_cap_is_shared_state_not_per_process(wa_on, settings):
    """Two 'workers' (separate calls into the service) draw on one shared counter."""
    settings.WHATSAPP_OTP_DAILY_CAP = 3
    for _ in range(3):
        consent._consume_daily_otp_budget()
    with pytest.raises(consent.ConsentError) as exc:
        consent._consume_daily_otp_budget()
    assert exc.value.status == 503


def test_concurrent_requests_crossing_the_cap_never_exceed_it(wa_on, settings):
    from concurrent.futures import ThreadPoolExecutor

    settings.WHATSAPP_OTP_DAILY_CAP = 5

    def take(_):
        try:
            consent._consume_daily_otp_budget()
            return True
        except consent.ConsentError:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        granted = sum(pool.map(take, range(20)))
    assert granted == 5


def test_cache_outage_fails_closed(wa_on, auth_client, mock_post):
    user = _verified("down@test.local")
    with mock.patch.object(cache, "incr", side_effect=ConnectionError("redis down")):
        response = _link(auth_client(user))
    assert response.status_code == 503
    mock_post.assert_not_called()


def test_per_user_limit(wa_on, auth_client, mock_post, monkeypatch):
    monkeypatch.setattr(
        ScopedRateThrottle, "THROTTLE_RATES",
        {**ScopedRateThrottle.THROTTLE_RATES, "whatsapp_link": "2/hour", "whatsapp_link_ip": "1000/hour"},
    )
    user = _verified("rate@test.local")
    codes = [_link(auth_client(user), phone="12345").status_code for _ in range(4)]
    assert codes[:2] == [400, 400] and codes[2:] == [429, 429]


def test_per_ip_limit_applies_across_many_accounts(wa_on, auth_client, mock_post, monkeypatch):
    monkeypatch.setattr(
        ScopedRateThrottle, "THROTTLE_RATES",
        {**ScopedRateThrottle.THROTTLE_RATES, "whatsapp_link": "1000/hour", "whatsapp_link_ip": "2/hour"},
    )
    codes = []
    for i in range(4):
        user = _verified(f"ip{i}@test.local")
        codes.append(_link(auth_client(user), phone="12345").status_code)  # same test-client IP
    assert codes[:2] == [400, 400] and codes[2:] == [429, 429]


def test_throttle_backend_outage_fails_closed(wa_on, auth_client, mock_post):
    user = _verified("thr@test.local")
    with mock.patch.object(cache, "get", side_effect=ConnectionError("down")):
        response = _link(auth_client(user))
    assert response.status_code == 503
    mock_post.assert_not_called()


def test_provider_failure_returns_502_without_leaking_detail(wa_on, auth_client, mock_post):
    import requests

    mock_post.side_effect = requests.ConnectionError("provider secret detail")
    user = _verified("prov@test.local")
    response = _link(auth_client(user))
    assert response.status_code == 502
    assert "secret" not in str(response.data)
