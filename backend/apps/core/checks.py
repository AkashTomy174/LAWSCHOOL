"""Deployment-time configuration checks (run by ``check`` and ``migrate``)."""

from __future__ import annotations

from django.conf import settings
from django.core.checks import Warning, register

_NON_DELIVERING = ("console", "locmem", "dummy", "filebased")


@register("lawschool")
def check_media_storage(app_configs, **kwargs) -> list:
    """Warn when production keeps uploads on the container filesystem."""
    if not getattr(settings, "PERSISTENT_MEDIA_REQUIRED", False):
        return []
    if settings.STORAGES["default"]["BACKEND"].endswith("FileSystemStorage"):
        return [
            Warning(
                "Uploaded media is stored on the container filesystem.",
                hint="Set AWS_STORAGE_BUCKET_NAME, AWS_S3_ENDPOINT_URL, "
                "AWS_S3_REGION_NAME, AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY "
                "for S3-compatible storage. Until then uploads are lost on every "
                "deploy and /media/ is not served (DEBUG is off).",
                id="lawschool.W003",
            )
        ]
    return []


@register("lawschool")
def check_email_delivery(app_configs, **kwargs) -> list:
    """Warn when production cannot actually deliver email.

    Password reset and email verification depend on it.  A warning, not an
    error: a missing mail provider must not block a release that fixes
    something else, but it must be visible in the deploy log.
    """
    if not getattr(settings, "EMAIL_DELIVERY_REQUIRED", False):
        return []
    backend = settings.EMAIL_BACKEND
    if backend.endswith("smtp.EmailBackend") and not settings.EMAIL_HOST:
        return [
            Warning(
                "EMAIL_BACKEND is SMTP but EMAIL_HOST is empty.",
                hint="Set EMAIL_HOST, EMAIL_PORT, EMAIL_HOST_USER and "
                "EMAIL_HOST_PASSWORD; until then password-reset and verification "
                "emails fail to send.",
                id="lawschool.W001",
            )
        ]
    if any(f".{name}." in backend for name in _NON_DELIVERING):
        return [
            Warning(
                f"EMAIL_BACKEND ({backend.rsplit('.', 2)[-2]}) does not deliver email.",
                hint="Use an SMTP or provider backend. The console backend also "
                "writes reset and verification links (live tokens) into the logs.",
                id="lawschool.W002",
            )
        ]
    return []
