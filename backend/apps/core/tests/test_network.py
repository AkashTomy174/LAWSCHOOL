"""client_ip must not be spoofable through X-Forwarded-For."""

from django.test import RequestFactory, override_settings

from apps.core.network import client_ip


def _request(forwarded=None):
    extra = {"REMOTE_ADDR": "10.0.0.5"}
    if forwarded:
        extra["HTTP_X_FORWARDED_FOR"] = forwarded
    return RequestFactory().get("/", **extra)


@override_settings(NUM_PROXIES=0)
def test_header_ignored_without_trusted_proxy():
    assert client_ip(_request("1.2.3.4")) == "10.0.0.5"


@override_settings(NUM_PROXIES=1)
def test_spoofed_leading_entries_are_ignored():
    # Client sent 6.6.6.6; our one proxy appended the real peer address.
    assert client_ip(_request("6.6.6.6, 203.0.113.9")) == "203.0.113.9"


@override_settings(NUM_PROXIES=2)
def test_short_header_falls_back_to_socket_address():
    assert client_ip(_request("203.0.113.9")) == "10.0.0.5"
