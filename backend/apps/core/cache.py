"""Cache calls that degrade instead of failing the request.

The cache (Redis in production) only speeds things up or rate-limits; the
database is the source of truth.  These turn an outage into a cache miss, and
log it at most once a minute per process so an outage cannot flood the logs.
"""

from __future__ import annotations

import time

from django.core.cache import cache

from apps.core.logging import get_logger

logger = get_logger(__name__)

_WARN_INTERVAL_SECONDS = 60.0
_last_warning = 0.0


def report_cache_failure(operation: str, exc: Exception) -> None:
    """Log a cache failure (error type only: messages can carry the Redis URL)."""
    global _last_warning
    now = time.monotonic()
    if now - _last_warning >= _WARN_INTERVAL_SECONDS:
        _last_warning = now
        logger.warning(
            "Cache unavailable; continuing without it",
            extra={"operation": operation, "error": type(exc).__name__},
        )


def cache_get(key, default=None):
    try:
        return cache.get(key, default)
    except Exception as exc:
        report_cache_failure("get", exc)
        return default


def cache_set(key, value, timeout) -> None:
    try:
        cache.set(key, value, timeout)
    except Exception as exc:
        report_cache_failure("set", exc)


def cache_delete_many(keys) -> None:
    try:
        cache.delete_many(keys)
    except Exception as exc:
        report_cache_failure("delete_many", exc)
