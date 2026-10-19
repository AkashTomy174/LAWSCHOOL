"""
Production settings.

Everything here fails *closed*: if a required secret is missing the process
refuses to start rather than silently running with a development default.
"""

import os

from .base import *  # noqa: F401,F403
from .base import env, env_bool, env_list

DEBUG = False

# --------------------------------------------------------------------------- #
# Fail fast on missing configuration
# --------------------------------------------------------------------------- #
_required = ["SECRET_KEY", "DATABASE_URL", "REDIS_URL", "CORS_ALLOWED_ORIGINS"]
_missing = [key for key in _required if not env(key)]
if _missing:
    raise RuntimeError(
        "Missing required production environment variables: " + ", ".join(_missing)
    )

from .base import SIMPLE_JWT, secret_problem  # noqa: E402

_secret_names = ["SECRET_KEY"]
if "JWT_SECRET" in os.environ:  # set but possibly blank: validate what is there
    _secret_names.append("JWT_SECRET")
_bad_secrets = [
    f"{name} {secret_problem(os.environ.get(name))}"
    for name in _secret_names
    if secret_problem(os.environ.get(name))
]
if _bad_secrets:
    raise RuntimeError(
        "Unsafe production secrets: " + "; ".join(_bad_secrets) + ". "
        "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
    )
if SIMPLE_JWT["ALGORITHM"] != "HS256":  # signing key below is a shared secret
    raise RuntimeError("SIMPLE_JWT ALGORITHM must be HS256 with a shared secret.")

_integration_required = [
    "RAZORPAY_KEY_ID",
    "RAZORPAY_KEY_SECRET",
    "RAZORPAY_WEBHOOK_SECRET",
    "CLOUDFLARE_ACCOUNT_ID",
    "CLOUDFLARE_API_TOKEN",
    "CLOUDFLARE_STREAM_KEY_ID",
    "CLOUDFLARE_STREAM_SIGNING_KEY",
]
_missing_integrations = [key for key in _integration_required if not env(key)]
if _missing_integrations:
    raise RuntimeError(
        "Missing payment/video integration secrets: "
        + ", ".join(_missing_integrations)
        + ". See docs/production-readiness-remediation.md (environment variables). "
        "CLOUDFLARE_STREAM_KEY_ID / CLOUDFLARE_STREAM_SIGNING_KEY are the `id` and "
        "base64 `pem` returned by Cloudflare's POST /accounts/<id>/stream/keys."
    )

# --------------------------------------------------------------------------- #
# Transport security
# --------------------------------------------------------------------------- #
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = int(env("SECURE_HSTS_SECONDS", "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = False  # the SPA reads it to send X-CSRFToken

X_FRAME_OPTIONS = "DENY"

# One proxy hop (the nginx container) by default; raise it if a CDN/LB sits in
# front as well.  Never leave it at 0 behind a proxy, or every client shares an IP.
NUM_PROXIES = int(env("NUM_PROXIES", "1"))
REST_FRAMEWORK = {**REST_FRAMEWORK, "NUM_PROXIES": NUM_PROXIES}  # noqa: F405

# --------------------------------------------------------------------------- #
# Servers / hosts
# --------------------------------------------------------------------------- #
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", [])
# Railway's deploy healthcheck calls the container over plain HTTP with this
# Host header; without both lines below it gets a 400 (host) or a 301 (HTTPS
# redirect) and every deploy fails its healthcheck.
ALLOWED_HOSTS.append("healthcheck.railway.app")
SECURE_REDIRECT_EXEMPT = [r"^health/"]
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", [])

# The OpenAPI schema and Swagger/Redoc UIs map every endpoint; admins only.
SPECTACULAR_SETTINGS = {  # noqa: F405
    **SPECTACULAR_SETTINGS,  # noqa: F405
    "SERVE_PERMISSIONS": ["apps.core.permissions.IsAdminRole"],
}

EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
# Password reset and verification need real delivery: apps.core.checks warns
# (in ``check`` and the pre-deploy ``migrate``) when it is not configured.
EMAIL_DELIVERY_REQUIRED = True

# --------------------------------------------------------------------------- #
# Uploaded media (avatars, course thumbnails)
# --------------------------------------------------------------------------- #
# The container filesystem is wiped on every deploy and Django does not serve
# /media/ with DEBUG off, so production uploads belong in S3-compatible object
# storage (a Railway Bucket, Cloudflare R2, AWS S3...).  The bucket stays
# private: every media URL is a short-lived signed link on the bucket's own
# domain, so an uploaded file never executes on the app's origin.
# apps.core.checks warns while this is not configured.
PERSISTENT_MEDIA_REQUIRED = True
if env("AWS_STORAGE_BUCKET_NAME"):
    STORAGES = {  # noqa: F405
        **STORAGES,  # noqa: F405
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                "bucket_name": env("AWS_STORAGE_BUCKET_NAME"),
                "endpoint_url": env("AWS_S3_ENDPOINT_URL") or None,
                "region_name": env("AWS_S3_REGION_NAME") or None,
                "access_key": env("AWS_ACCESS_KEY_ID"),
                "secret_key": env("AWS_SECRET_ACCESS_KEY"),
                "default_acl": None,
                "querystring_auth": True,
                "querystring_expire": 3600,
                "file_overwrite": False,
            },
        },
    }
LOG_JSON = env_bool("LOG_JSON", True)
