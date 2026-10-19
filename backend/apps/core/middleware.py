"""Brute-force protection for the Django admin login.

DRF throttles never see ``/admin/login/`` (it is a plain Django form view), and an
administrator account controls everything, so it gets its own limiter:

* failed attempts are counted per client IP *and* per submitted username, so both a
  single noisy host and a distributed guess against one account are slowed;
* a successful login clears that IP's counter;
* the block is temporary (``ADMIN_LOGIN_LOCKOUT_SECONDS``), so a real administrator
  is only delayed, never permanently locked out;
* the response is identical for known and unknown usernames, and the counters are
  keyed by a hash, so nothing reveals whether an account exists;
* the client address comes from ``client_ip`` (honours ``NUM_PROXIES`` only), never
  from a raw ``X-Forwarded-For``;
* if the cache is unavailable the login is refused (503) rather than left unlimited.
"""

from __future__ import annotations

import hashlib

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from django.urls import reverse

from apps.core.logging import get_logger
from apps.core.network import client_ip

logger = get_logger(__name__)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:32]


class AdminLoginThrottleMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method != "POST" or request.path != reverse("admin:login"):
            return self.get_response(request)

        ip_key = f"adminlogin:ip:{_digest(client_ip(request) or 'unknown')}"
        user_key = "adminlogin:user:" + _digest(
            (request.POST.get("username") or "").strip().lower()
        )
        limit_ip = settings.ADMIN_LOGIN_MAX_FAILURES_PER_IP
        limit_user = settings.ADMIN_LOGIN_MAX_FAILURES_PER_USER
        window = settings.ADMIN_LOGIN_LOCKOUT_SECONDS

        try:
            if (cache.get(ip_key) or 0) >= limit_ip or (cache.get(user_key) or 0) >= limit_user:
                logger.warning("Admin login blocked by rate limit")
                return HttpResponse(
                    "Too many failed sign-in attempts. Try again later.",
                    status=429,
                    headers={"Retry-After": str(window)},
                )
        except Exception as exc:
            logger.warning("Admin login limiter unavailable", extra={"error": type(exc).__name__})
            return HttpResponse("Sign-in is temporarily unavailable.", status=503)

        response = self.get_response(request)

        try:
            if response.status_code == 302:  # authenticated: forgive this host
                cache.delete(ip_key)
            elif response.status_code == 200:  # form re-rendered with an error
                for key in (ip_key, user_key):
                    cache.add(key, 0, window)
                    cache.incr(key)
        except Exception as exc:
            logger.warning("Admin login limiter write failed", extra={"error": type(exc).__name__})
        return response
