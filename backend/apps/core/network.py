"""Client IP resolution that cannot be spoofed through ``X-Forwarded-For``.

The header is client-controlled: every proxy *appends* to whatever the client sent,
so only the entries added by our own proxies are trustworthy.  ``NUM_PROXIES`` is
the number of trusted proxy hops in front of the app (0 = none, use the socket
address).  It is the same setting DRF's throttles read, so rate limiting and audit
logging agree on who the client is.
"""

from __future__ import annotations

from django.conf import settings


def client_ip(request) -> str | None:
    remote = request.META.get("REMOTE_ADDR")
    num_proxies = getattr(settings, "NUM_PROXIES", 0) or 0
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if not num_proxies or not forwarded:
        return remote
    addresses = [part.strip() for part in forwarded.split(",") if part.strip()]
    if len(addresses) < num_proxies:
        return remote
    return addresses[-num_proxies]
