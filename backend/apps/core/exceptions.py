"""Consistent API error envelope + domain exception types.

Every error leaves the API shaped like::

    {"error": {"code": "permission_denied",
               "message": "Human readable summary.",
               "details": {...} | null}}

The frontend therefore has exactly one error contract to handle, which removes
a whole class of "sometimes it's ``detail``, sometimes ``non_field_errors``"
bugs.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions as drf_exceptions
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

# Maps exception classes to stable machine-readable codes.
_CODE_MAP: dict[type, str] = {
    drf_exceptions.ValidationError: "validation_error",
    drf_exceptions.AuthenticationFailed: "authentication_failed",
    drf_exceptions.NotAuthenticated: "not_authenticated",
    drf_exceptions.PermissionDenied: "permission_denied",
    drf_exceptions.NotFound: "not_found",
    drf_exceptions.MethodNotAllowed: "method_not_allowed",
    drf_exceptions.Throttled: "throttled",
    drf_exceptions.UnsupportedMediaType: "unsupported_media_type",
    drf_exceptions.ParseError: "parse_error",
}


class DomainError(drf_exceptions.APIException):
    """Base class for business-rule violations that map onto HTTP semantics.

    Subclasses set ``status_code``/``default_code``; services raise these instead
    of building ``Response`` objects by hand, which keeps the error envelope
    identical everywhere.
    """

    status_code = 400
    default_detail = "Business rule violation."
    default_code = "domain_error"


class PaymentError(DomainError):
    status_code = 400
    default_detail = "The payment could not be processed."
    default_code = "payment_error"


class EntitlementError(DomainError):
    """Raised when a user has no right to access a course/lesson/video."""

    status_code = 403
    default_detail = "Your subscription does not include access to this content."
    default_code = "entitlement_denied"


class VideoNotReadyError(DomainError):
    status_code = 409
    default_detail = "This video is still processing. Try again shortly."
    default_code = "video_not_ready"


class PlaybackUnavailableError(DomainError):
    """Playback could not be authorised because of a server-side misconfiguration.

    Deliberately a 503, not a 500: the request is valid and the student is entitled
    -- we simply cannot mint a token right now.  The underlying cause (a missing or
    rotated Cloudflare signing key) is logged, never returned to the client.
    """

    status_code = 503
    default_detail = (
        "Video playback is temporarily unavailable. Please try again shortly."
    )
    default_code = "playback_unavailable"


class RateLimitedError(DomainError):
    """Too many requests for a per-user budget (playback tokens, progress)."""

    status_code = 429
    default_detail = "Too many requests. Please slow down."
    default_code = "rate_limited"


class ConflictError(DomainError):
    status_code = 409
    default_detail = "The request conflicts with the current state."
    default_code = "conflict"


def message_for(exc: Exception) -> str:
    """Public: the human-readable first line of an exception's detail."""
    return _message_for(exc, "Request failed.")


def _message_for(exc: Exception, fallback: str) -> str:
    detail = getattr(exc, "detail", None)
    if detail is None:
        return fallback
    if isinstance(detail, (list, tuple)) and detail:
        return str(detail[0])
    if isinstance(detail, dict):
        first = next(iter(detail.values()), fallback)
        if isinstance(first, (list, tuple)) and first:
            return str(first[0])
        return str(first)
    return str(detail)


def _details_for(exc: Exception) -> Any:
    """Field errors for validation failures; ``None`` otherwise."""
    if not isinstance(exc, drf_exceptions.ValidationError):
        return None
    detail = exc.detail
    if isinstance(detail, dict):
        # Normalise every value to a list of strings for easy form rendering.
        return {
            key: [str(item) for item in (value if isinstance(value, list) else [value])]
            for key, value in detail.items()
        }
    if isinstance(detail, list):
        return {"non_field_errors": [str(item) for item in detail]}
    return {"non_field_errors": [str(detail)]}


def lawschool_exception_handler(exc: Exception, context: dict) -> Response | None:
    """DRF ``EXCEPTION_HANDLER`` that wraps every error in the standard envelope."""
    if isinstance(exc, Http404):
        exc = drf_exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = drf_exceptions.PermissionDenied()

    response = drf_exception_handler(exc, context)
    if response is None:
        # Unhandled exception: let Django's 500 handler log it with a traceback.
        return None

    code = code_for(exc)

    response.data = {
        "error": {
            "code": code,
            "message": message_for(exc),
            "details": _details_for(exc),
        }
    }
    return response


def code_for(exc: Exception) -> str:
    """Public: the machine-readable code for an exception.

    Used by views that must branch on a *specific* failure (e.g. the Razorpay
    webhook deciding between 400 and 500).

    Resolution order, most specific first:

    1. A ``code`` passed at the raise site, e.g.
       ``PaymentError({"detail": "..."}, code="unknown_order")``.  Where that code
       lives depends on the shape of the detail DRF was given:

       * ``PaymentError("msg", code="x")``   -> ``exc.detail.code``
       * ``PaymentError({"detail": "msg"}, code="x")`` -> the code lands on the
         *nested* ``ErrorDetail`` inside the dict.

       Reading only ``default_code`` (or only the top level) silently degrades
       every custom code to the class default -- the bug this function prevents.
    2. ``default_code`` for our domain exceptions.
    3. The static map for DRF's built-in exception types.
    """
    detail = getattr(exc, "detail", None)

    # Shape 1: detail is itself an ErrorDetail carrying the raise-site code.
    top_level_code = getattr(detail, "code", None)
    if top_level_code and top_level_code != "error":
        return str(top_level_code)

    # Shape 2: detail is a mapping of field -> (list of) ErrorDetail.
    if isinstance(detail, dict):
        for value in detail.values():
            candidates = value if isinstance(value, (list, tuple)) else [value]
            for candidate in candidates:
                candidate_code = getattr(candidate, "code", None)
                if candidate_code and candidate_code != "error":
                    return str(candidate_code)

    if isinstance(exc, DomainError):
        return str(getattr(exc, "default_code", "error"))

    for exc_type, mapped in _CODE_MAP.items():
        if isinstance(exc, exc_type):
            return mapped

    return str(getattr(exc, "default_code", "error"))
