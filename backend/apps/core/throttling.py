"""Rate limiting that survives a cache outage, deliberately per scope.

DRF throttles keep their counters in the cache.  When it is unreachable:

* ``auth`` (login, registration, verification, password reset) fails *closed*
  with a 503: it is the brute-force / credential-stuffing control, and an hour
  without it is worse than an hour without sign-in;
* every other scope fails *open*: refresh tokens are signed and their blacklist
  lives in the database, payments and webhooks are signature-checked, and
  playback/progress still pass the entitlement check.  Failing those closed
  would log every user out or drop payment events.
"""

from __future__ import annotations

from rest_framework.throttling import ScopedRateThrottle

from apps.core.cache import report_cache_failure

FAIL_CLOSED_SCOPES = frozenset({"auth"})


class ResilientScopedRateThrottle(ScopedRateThrottle):
    def allow_request(self, request, view) -> bool:
        try:
            return super().allow_request(request, view)
        except Exception as exc:
            report_cache_failure("throttle", exc)
            if getattr(view, self.scope_attr, None) in FAIL_CLOSED_SCOPES:
                # Imported here: DRF loads this class while apps.core.exceptions
                # is still importing DRF.
                from apps.core.exceptions import TemporarilyUnavailableError

                raise TemporarilyUnavailableError()
            return True
