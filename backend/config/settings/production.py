"""
Production settings.

Everything here fails *closed*: if a required secret is missing the process
refuses to start rather than silently running with a development default.
"""

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

_integration_required = [
    "RAZORPAY_KEY_ID",
    "RAZORPAY_KEY_SECRET",
    "RAZORPAY_WEBHOOK_SECRET",
    "CLOUDFLARE_ACCOUNT_ID",
    "CLOUDFLARE_API_TOKEN",
    "CLOUDFLARE_STREAM_SIGNING_KEY",
]
_missing_integrations = [key for key in _integration_required if not env(key)]
if _missing_integrations:
    raise RuntimeError(
        "Missing payment/video integration secrets: " + ", ".join(_missing_integrations)
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

# --------------------------------------------------------------------------- #
# Servers / hosts
# --------------------------------------------------------------------------- #
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", [])
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", [])

EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
LOG_JSON = env_bool("LOG_JSON", True)
