"""
Base settings shared by every environment.

Environment variables are loaded from ``backend/.env`` (never committed) via
python-dotenv.  Secrets are read *only* from the environment so that the same
image can be promoted from staging to production without code changes.
"""

from datetime import timedelta
from pathlib import Path

import dj_database_url
from celery.schedules import crontab
from dotenv import load_dotenv
import os

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
BASE_DIR = Path(__file__).resolve().parents[2]

load_dotenv(BASE_DIR / ".env")


def env(key: str, default: str | None = None) -> str | None:
    """Read a string from the environment."""
    return os.environ.get(key, default)


def env_bool(key: str, default: bool = False) -> bool:
    """Read a boolean from the environment, accepting 1/true/yes/on."""
    raw = os.environ.get(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_list(key: str, default: list[str] | None = None) -> list[str]:
    """Read a comma-separated list from the environment."""
    raw = os.environ.get(key)
    if not raw:
        return list(default or [])
    return [item.strip() for item in raw.split(",") if item.strip()]


# --------------------------------------------------------------------------- #
# Security
# --------------------------------------------------------------------------- #
# Substrings that mark a secret as a copied-from-the-docs placeholder.
PLACEHOLDER_SECRET_MARKERS = (
    "change-me",
    "changeme",
    "insecure",
    "placeholder",
    "your-secret",
    "your_secret",
    "secret-key-here",
    "example",
    "xxxx",
    "build-only",
)
MIN_SECRET_LENGTH = 32


def secret_problem(value: str | None) -> str | None:
    """Why ``value`` is unfit to be a signing secret, or ``None`` if it is fine.

    Never includes the value itself, so the message is safe to log or raise.
    """
    if value is None or not value.strip():
        return "is empty or whitespace-only"
    if value != value.strip():
        return "has leading or trailing whitespace"
    lowered = value.lower()
    if any(marker in lowered for marker in PLACEHOLDER_SECRET_MARKERS):
        return "looks like a placeholder"
    if len(value) < MIN_SECRET_LENGTH:
        return f"is shorter than {MIN_SECRET_LENGTH} characters"
    return None


SECRET_KEY = env("SECRET_KEY", "insecure-development-key-change-me")
DEBUG = env_bool("DEBUG", False)
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", ["localhost", "127.0.0.1"])

# Django admin login: temporary lockout after repeated failures (see
# apps.core.middleware).  Per client IP and per submitted username.
ADMIN_LOGIN_MAX_FAILURES_PER_IP = int(env("ADMIN_LOGIN_MAX_FAILURES_PER_IP", "5"))
ADMIN_LOGIN_MAX_FAILURES_PER_USER = int(env("ADMIN_LOGIN_MAX_FAILURES_PER_USER", "10"))
ADMIN_LOGIN_LOCKOUT_SECONDS = int(env("ADMIN_LOGIN_LOCKOUT_SECONDS", "900"))

# Number of trusted reverse proxies in front of the app.  DRF throttling and audit
# logging use it to pick the client address out of X-Forwarded-For; with 0 the
# header is ignored entirely, so it cannot be used to dodge rate limits.
# This is the single source of truth: REST_FRAMEWORK below reads it, and so does
# apps.core.network.client_ip.  Production raises the default to 1.
NUM_PROXIES = int(env("NUM_PROXIES", "0"))

# Application definition
INSTALLED_APPS = [
    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    "django_celery_beat",
    # Local
    "apps.core",
    "apps.users",
    "apps.courses",
    "apps.subscriptions",
    "apps.videos",
    "apps.quizzes",
    "apps.live",
    "apps.payments",
    "apps.leaderboard",
    "apps.notifications",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "apps.core.middleware.AdminLoginThrottleMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --------------------------------------------------------------------------- #
# Database
# --------------------------------------------------------------------------- #
# DATABASE_URL wins; otherwise fall back to sqlite for zero-config local runs.
DATABASES = {
    "default": dj_database_url.parse(
        env("DATABASE_URL") or f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
        conn_health_checks=True,
    )
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --------------------------------------------------------------------------- #
# Authentication
# --------------------------------------------------------------------------- #
# AUTH_USER_MODEL is fixed in Phase 2, but set here so migrations stay stable
# for every environment from the very first commit.
AUTH_USER_MODEL = "users.User"

AUTHENTICATION_BACKENDS = [
    # Email login is case-insensitive; see apps/users/backends.py for rationale.
    "apps.users.backends.EmailBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# Password-reset links live one hour (single use: they die on any password change).
# Email-verification links keep Django's PASSWORD_RESET_TIMEOUT default (3 days).
PASSWORD_RESET_LINK_SECONDS = int(env("PASSWORD_RESET_LINK_SECONDS", "3600"))

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --------------------------------------------------------------------------- #
# i18n / tz
# --------------------------------------------------------------------------- #
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

# --------------------------------------------------------------------------- #
# Static & media
# --------------------------------------------------------------------------- #
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "whitenoise.storage.CompressedManifestStaticFilesStorage"
            if not DEBUG
            else "django.contrib.staticfiles.storage.StaticFilesStorage"
        )
    },
}

# --------------------------------------------------------------------------- #
# DRF
# --------------------------------------------------------------------------- #
REST_FRAMEWORK = {
    "NUM_PROXIES": NUM_PROXIES,
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardResultsSetPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.core.exceptions.lawschool_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": (
        "apps.core.throttling.ResilientScopedRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "auth": "10/min",
        # Refresh is keyed by IP too (no user yet), and a campus NAT puts hundreds
        # of students behind one address.  A refresh token is a signed secret, so
        # this limit only needs to stop floods, not guessing.
        "token_refresh": "300/min",
        "payment": "30/min",
        "playback": "120/min",
        "progress": "120/min",
        # One scope per provider so one sender's burst cannot starve the other.
        # The key is the (proxy-verified) client IP, never a request header.
        "webhook_razorpay": "300/min",
        "webhook_whatsapp": "300/min",
        # Direct-upload URL minting: each URL is a billable Cloudflare asset slot.
        "video_upload": "20/hour",
        "whatsapp_link": "5/hour",
        "whatsapp_link_ip": "20/hour",
        "whatsapp_verify": "20/hour",
        "whatsapp_admin": "60/min",
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "LawSchool LMS API",
    "DESCRIPTION": (
        "REST API for the LawSchool learning platform.\n\n"
        "## Authentication\n"
        "Every protected endpoint expects a JWT access token:\n"
        "`Authorization: Bearer <access_token>`.\n"
        "Obtain a pair from `POST /api/v1/auth/login/` and rotate it with "
        "`POST /api/v1/auth/refresh/`. Access tokens are short-lived; refresh "
        "tokens are rotated and the previous token is blacklisted.\n\n"
        "## Errors\n"
        "All errors share one envelope: "
        '`{"error": {"code": str, "message": str, "details": {...}}}`.'
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": "/api/v1",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(env("JWT_ACCESS_MINUTES", "15"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(env("JWT_REFRESH_DAYS", "7"))),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    # A *blank* JWT_SECRET (e.g. copied from .env.example) counts as unset, never as
    # an empty key.  The fallback is the validated SECRET_KEY, not a literal.
    "SIGNING_KEY": (env("JWT_SECRET") or "").strip() or SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "TOKEN_OBTAIN_SERIALIZER": "apps.users.serializers.EmailTokenObtainPairSerializer",
}

# --------------------------------------------------------------------------- #
# CORS / CSRF
# --------------------------------------------------------------------------- #
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", ["http://localhost:5173"])
CORS_ALLOW_CREDENTIALS = True

CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", ["http://localhost:5173"])

# --------------------------------------------------------------------------- #
# Redis / cache
# --------------------------------------------------------------------------- #
REDIS_URL = env("REDIS_URL", "redis://127.0.0.1:6379/0")
CACHE_REDIS_URL = env("CACHE_REDIS_URL", REDIS_URL)
CELERY_BROKER_URL = env("CELERY_BROKER_URL", REDIS_URL)

# The cache is a performance optimisation, never a correctness requirement: every
# entitlement check also reads the database.  Setting CACHE_BACKEND=locmem lets a
# developer run the API with no Redis at all, which keeps local setup to one
# command and makes the test suite independent of infrastructure.
CACHE_BACKEND = env("CACHE_BACKEND", "redis")

if CACHE_BACKEND == "locmem":
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "lawschool-locmem",
            "TIMEOUT": 300,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": CACHE_REDIS_URL,
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
                # Fail fast: a hung cache must not hang requests (see apps.core.cache).
                "SOCKET_CONNECT_TIMEOUT": 1,
                "SOCKET_TIMEOUT": 1,
            },
            "KEY_PREFIX": "lawschool",
            "TIMEOUT": 300,
        }
    }

# --------------------------------------------------------------------------- #
# Celery
# --------------------------------------------------------------------------- #
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", False)
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# Periodic maintenance.  Each entry is deliberately a *background* concern:
# nothing here is required to answer a user's HTTP request, which is why the
# application stays correct even if the worker is down for a while.
CELERY_BEAT_SCHEDULE = {
    "expire-subscriptions-hourly": {
        "task": "apps.core.tasks.expire_subscriptions",
        "schedule": 60 * 60,
    },
    "subscription-expiry-reminders-daily": {
        "task": "apps.core.tasks.send_expiry_reminders",
        "schedule": 60 * 60 * 24,
    },
    "reconcile-payments-every-15-min": {
        "task": "apps.core.tasks.reconcile_payments",
        "schedule": 60 * 15,
    },
    "sync-pending-videos-every-10-min": {
        "task": "apps.core.tasks.sync_pending_videos",
        "schedule": 60 * 10,
    },
    "retry-failed-emails-hourly": {
        "task": "apps.notifications.tasks.retry_failed_notification_emails",
        "schedule": 60 * 60,
    },
    "recalculate-leaderboard-nightly": {
        "task": "apps.core.tasks.recalculate_leaderboard_task",
        "schedule": 60 * 60 * 24,
    },
    # ---- WhatsApp (all no-ops while WHATSAPP_ENABLED is false) ------------- #
    "whatsapp-class-reminders-every-5-min": {
        "task": "apps.notifications.tasks.dispatch_class_reminders",
        "schedule": 60 * 5,
    },
    "whatsapp-sweep-pending-every-5-min": {
        "task": "apps.notifications.tasks.sweep_pending_whatsapp",
        "schedule": 60 * 5,
    },
    "whatsapp-weekly-summary": {
        "task": "apps.notifications.tasks.send_weekly_summaries",
        # Monday 09:00 in CELERY_TIMEZONE (Asia/Kolkata).
        "schedule": crontab(hour=9, minute=0, day_of_week=1),
    },
    "whatsapp-inactivity-daily": {
        "task": "apps.notifications.tasks.send_inactivity_reminders",
        "schedule": crontab(hour=11, minute=0),
    },
    "whatsapp-cleanup-daily": {
        "task": "apps.notifications.tasks.cleanup_whatsapp_records",
        "schedule": crontab(hour=3, minute=30),
    },
}

# --------------------------------------------------------------------------- #
# Email
# --------------------------------------------------------------------------- #
EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", "")
EMAIL_PORT = int(env("EMAIL_PORT", "587"))
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "LawSchool <no-reply@lawschool.local>")

FRONTEND_URL = env("FRONTEND_URL", "http://localhost:5173")

# --------------------------------------------------------------------------- #
# Third-party integrations (never hard-coded)
# --------------------------------------------------------------------------- #
RAZORPAY_KEY_ID = env("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = env("RAZORPAY_KEY_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = env("RAZORPAY_WEBHOOK_SECRET", "")

CLOUDFLARE_ACCOUNT_ID = env("CLOUDFLARE_ACCOUNT_ID", "")
CLOUDFLARE_API_TOKEN = env("CLOUDFLARE_API_TOKEN", "")
# Signing key from `POST /stream/keys`: the key `id`, and its base64 `pem` (RSA, RS256).
CLOUDFLARE_STREAM_KEY_ID = env("CLOUDFLARE_STREAM_KEY_ID", "")
CLOUDFLARE_STREAM_SIGNING_KEY = env("CLOUDFLARE_STREAM_SIGNING_KEY", "")
CLOUDFLARE_STREAM_CUSTOMER_CODE = env("CLOUDFLARE_STREAM_CUSTOMER_CODE", "")
# Signed playback tokens are intentionally very short lived.
CLOUDFLARE_PLAYBACK_TOKEN_TTL = int(env("CLOUDFLARE_PLAYBACK_TOKEN_TTL", "300"))

# --------------------------------------------------------------------------- #
# WhatsApp Business Platform (Meta Cloud API).  Disabled unless explicitly turned
# on; the LMS behaves exactly as before while WHATSAPP_ENABLED is false.
# --------------------------------------------------------------------------- #
WHATSAPP_ENABLED = env_bool("WHATSAPP_ENABLED", False)
WHATSAPP_API_VERSION = env("WHATSAPP_API_VERSION", "v21.0")
WHATSAPP_API_BASE_URL = env("WHATSAPP_API_BASE_URL", "https://graph.facebook.com")
WHATSAPP_PHONE_NUMBER_ID = env("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_BUSINESS_ACCOUNT_ID = env("WHATSAPP_BUSINESS_ACCOUNT_ID", "")
WHATSAPP_ACCESS_TOKEN = env("WHATSAPP_ACCESS_TOKEN", "")
WHATSAPP_APP_SECRET = env("WHATSAPP_APP_SECRET", "")
WHATSAPP_VERIFY_TOKEN = env("WHATSAPP_VERIFY_TOKEN", "")
WHATSAPP_DEFAULT_LANGUAGE = env("WHATSAPP_DEFAULT_LANGUAGE", "en")
WHATSAPP_REQUEST_TIMEOUT = int(env("WHATSAPP_REQUEST_TIMEOUT", "10"))
# Sends only go out for templates whose approval_status is "approved".  Turn this
# on in a sandbox/test WABA where templates are not reviewed.
WHATSAPP_ALLOW_UNAPPROVED_TEMPLATES = env_bool("WHATSAPP_ALLOW_UNAPPROVED_TEMPLATES", False)
# Meta has no idempotency key for message submission.  After a read timeout we
# cannot tell whether the message was accepted, so by default we do not resend.
WHATSAPP_RETRY_AMBIGUOUS = env_bool("WHATSAPP_RETRY_AMBIGUOUS", False)
WHATSAPP_MAX_ATTEMPTS = int(env("WHATSAPP_MAX_ATTEMPTS", "4"))
# Platform-wide ceiling on verification codes per day (each is a paid message).
WHATSAPP_OTP_DAILY_CAP = int(env("WHATSAPP_OTP_DAILY_CAP", "300"))
WHATSAPP_SEND_RATE_PER_MINUTE = int(env("WHATSAPP_SEND_RATE_PER_MINUTE", "600"))
WHATSAPP_MAX_BROADCAST_RECIPIENTS = int(env("WHATSAPP_MAX_BROADCAST_RECIPIENTS", "2000"))
WHATSAPP_WEBHOOK_MAX_BYTES = int(env("WHATSAPP_WEBHOOK_MAX_BYTES", str(512 * 1024)))
WHATSAPP_RETENTION_DAYS = int(env("WHATSAPP_RETENTION_DAYS", "90"))
WHATSAPP_INBOUND_RETENTION_DAYS = int(env("WHATSAPP_INBOUND_RETENTION_DAYS", "30"))
# Planning figure only (per delivered template message, INR).  Empty = unknown;
# real charges come from Meta billing, never from this number.
WHATSAPP_ESTIMATED_COST_PER_MESSAGE = env("WHATSAPP_ESTIMATED_COST_PER_MESSAGE", "")
SUPPORT_EMAIL = env("SUPPORT_EMAIL", "support@lawschool.local")

# --------------------------------------------------------------------------- #
# Domain tuning
# --------------------------------------------------------------------------- #
# How much clock skew we tolerate when validating Razorpay webhook timestamps.
PAYMENT_WEBHOOK_TOLERANCE_SECONDS = int(env("PAYMENT_WEBHOOK_TOLERANCE_SECONDS", "300"))
# Razorpay retries failed deliveries for about 24h, so the *age* limit on a signed
# event timestamp must be generous.  Replays inside it are caught by the
# content-addressed event id, not by the clock.
PAYMENT_WEBHOOK_MAX_AGE_SECONDS = int(env("PAYMENT_WEBHOOK_MAX_AGE_SECONDS", str(3 * 86400)))
# Progress updates may not jump further than this per submitted delta (anti-cheat).
VIDEO_PROGRESS_MAX_DRIFT_SECONDS = int(env("VIDEO_PROGRESS_MAX_DRIFT_SECONDS", "30"))
# Longest video Cloudflare will accept through a direct-upload URL (seconds).
VIDEO_MAX_DURATION_SECONDS = int(env("VIDEO_MAX_DURATION_SECONDS", str(4 * 3600)))
# Maximum upload size accepted for thumbnails / images (5 MB).
MAX_IMAGE_UPLOAD_BYTES = int(env("MAX_IMAGE_UPLOAD_BYTES", str(5 * 1024 * 1024)))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} {process:d} {message}",
            "style": "{",
        },
        "json": {
            "()": "apps.core.logging.JsonFormatter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json" if env_bool("LOG_JSON", False) else "verbose",
        },
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
    "loggers": {
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
        "lawschool": {
            "handlers": ["console"],
            "level": env("LOG_LEVEL", "INFO"),
            "propagate": False,
        },
    },
}
