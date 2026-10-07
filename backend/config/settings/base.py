"""
Base settings shared by every environment.

Environment variables are loaded from ``backend/.env`` (never committed) via
python-dotenv.  Secrets are read *only* from the environment so that the same
image can be promoted from staging to production without code changes.
"""

from datetime import timedelta
from pathlib import Path

import dj_database_url
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
SECRET_KEY = env("SECRET_KEY", "insecure-development-key-change-me")
DEBUG = env_bool("DEBUG", False)
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", ["localhost", "127.0.0.1"])

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
    "DEFAULT_THROTTLE_CLASSES": ("rest_framework.throttling.ScopedRateThrottle",),
    "DEFAULT_THROTTLE_RATES": {
        "auth": "10/min",
        # Refresh is keyed by IP too (no user yet), and a campus NAT puts hundreds
        # of students behind one address.  A refresh token is a signed secret, so
        # this limit only needs to stop floods, not guessing.
        "token_refresh": "300/min",
        "payment": "30/min",
        "playback": "120/min",
        "progress": "120/min",
        "webhook": "300/min",
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
    "SIGNING_KEY": env("JWT_SECRET", SECRET_KEY),
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
            "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
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
# Domain tuning
# --------------------------------------------------------------------------- #
# How much clock skew we tolerate when validating Razorpay webhook timestamps.
PAYMENT_WEBHOOK_TOLERANCE_SECONDS = int(env("PAYMENT_WEBHOOK_TOLERANCE_SECONDS", "300"))
# Progress updates may not jump further than this per submitted delta (anti-cheat).
VIDEO_PROGRESS_MAX_DRIFT_SECONDS = int(env("VIDEO_PROGRESS_MAX_DRIFT_SECONDS", "30"))
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
