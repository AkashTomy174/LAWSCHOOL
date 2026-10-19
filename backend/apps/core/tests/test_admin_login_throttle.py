"""W4: Django admin login is rate limited without enabling enumeration or lockout."""

from unittest import mock

import pytest
from django.core.cache import cache
from django.test import Client

from apps.users.models import User

pytestmark = pytest.mark.django_db

LOGIN = "/admin/login/?next=/admin/"
PW = "Str0ng-Passphrase-9"


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def staff(db):
    return User.objects.create_superuser(email="root@test.local", password=PW, name="Root")


def _post(client, username="root@test.local", password="wrong", **extra):
    return client.post(LOGIN, {"username": username, "password": password}, **extra)


def test_valid_login_works(staff):
    client = Client()
    assert _post(client, password=PW).status_code == 302


def test_repeated_failures_are_blocked_then_correct_password_also_blocked(staff, settings):
    settings.ADMIN_LOGIN_MAX_FAILURES_PER_IP = 3
    client = Client()
    assert [_post(client).status_code for _ in range(3)] == [200, 200, 200]
    blocked = _post(client)
    assert blocked.status_code == 429 and blocked["Retry-After"]
    assert _post(client, password=PW).status_code == 429  # no oracle while blocked


def test_block_is_temporary_not_permanent(staff, settings):
    settings.ADMIN_LOGIN_MAX_FAILURES_PER_IP = 1
    client = Client()
    _post(client)
    assert _post(client).status_code == 429
    cache.clear()  # the lockout window elapsing
    assert _post(client, password=PW).status_code == 302


def test_success_clears_ip_counter(staff, settings):
    settings.ADMIN_LOGIN_MAX_FAILURES_PER_IP = 3
    client = Client()
    _post(client)
    _post(client)
    assert _post(client, password=PW).status_code == 302
    assert _post(Client()).status_code == 200  # counter was reset, not at limit


def test_known_and_unknown_usernames_get_identical_responses(staff, settings):
    settings.ADMIN_LOGIN_MAX_FAILURES_PER_IP = 2
    known, unknown = Client(), Client(REMOTE_ADDR="10.9.9.9")
    a = [_post(known).status_code for _ in range(3)]
    b = [_post(unknown, username="ghost@test.local").status_code for _ in range(3)]
    assert a == b == [200, 200, 429]


def test_distributed_guessing_of_one_account_is_limited_per_username(staff, settings):
    settings.ADMIN_LOGIN_MAX_FAILURES_PER_IP = 100
    settings.ADMIN_LOGIN_MAX_FAILURES_PER_USER = 3
    codes = [_post(Client(REMOTE_ADDR=f"10.0.0.{i}")).status_code for i in range(5)]
    assert codes == [200, 200, 200, 429, 429]


def test_other_ips_are_unaffected_by_one_blocked_ip(staff, settings):
    settings.ADMIN_LOGIN_MAX_FAILURES_PER_IP = 1
    _post(Client(REMOTE_ADDR="10.1.1.1"))
    assert _post(Client(REMOTE_ADDR="10.1.1.1")).status_code == 429
    assert _post(Client(REMOTE_ADDR="10.1.1.2"), username="x@test.local").status_code == 200


def test_spoofed_forwarded_header_ignored_without_trusted_proxy(staff, settings):
    settings.NUM_PROXIES = 0
    settings.ADMIN_LOGIN_MAX_FAILURES_PER_IP = 2
    client = Client()
    codes = [_post(client, HTTP_X_FORWARDED_FOR=f"1.2.3.{i}").status_code for i in range(3)]
    assert codes == [200, 200, 429]  # rotating the header does not buy fresh attempts


def test_trusted_proxy_uses_last_hop_address(staff, settings):
    settings.NUM_PROXIES = 1
    settings.ADMIN_LOGIN_MAX_FAILURES_PER_IP = 1
    first = Client(HTTP_X_FORWARDED_FOR="9.9.9.9, 7.7.7.7")
    _post(first)
    # Same trusted hop (7.7.7.7) => same client, whatever the spoofed leading entry.
    assert _post(Client(HTTP_X_FORWARDED_FOR="1.1.1.1, 7.7.7.7")).status_code == 429
    assert _post(Client(HTTP_X_FORWARDED_FOR="9.9.9.9, 8.8.8.8"), username="y@x.l").status_code == 200


def test_csrf_still_enforced_and_not_counted_as_failure(staff, settings):
    settings.ADMIN_LOGIN_MAX_FAILURES_PER_IP = 1
    client = Client(enforce_csrf_checks=True)
    assert _post(client).status_code == 403
    assert _post(client).status_code == 403  # a CSRF reject is not a guess


def test_get_requests_are_untouched(staff):
    assert Client().get("/admin/login/").status_code == 200


def test_cache_outage_fails_closed(staff):
    with mock.patch.object(cache, "get", side_effect=ConnectionError("down")):
        assert _post(Client(), password=PW).status_code == 503
