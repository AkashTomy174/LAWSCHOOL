"""
Settings used by the pytest suite.

Key properties:
* in-memory sqlite by default, but ``DATABASE_URL`` is honoured so the same
  settings module can drive ``manage.py migrate``/``seed_demo`` against a file
  database when you need to inspect real data.
* locmem cache so tests never touch a Redis instance
* Celery runs eagerly and synchronously
* throttling effectively disabled unless a test opts in
"""

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = False

# In-memory sqlite keeps the suite fast; override with DATABASE_URL to work
# against a real file or Postgres instance.
if env("DATABASE_URL"):
    DATABASES = {  # noqa: F405
        "default": dj_database_url.parse(  # noqa: F405
            env("DATABASE_URL"), conn_max_age=0, conn_health_checks=False
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
            "TEST": {"NAME": ":memory:"},
        }
    }

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Deterministic fake credentials so signature tests are reproducible.
RAZORPAY_KEY_ID = "rzp_test_key"
RAZORPAY_KEY_SECRET = "test_secret_key"
RAZORPAY_WEBHOOK_SECRET = "test_webhook_secret"

CLOUDFLARE_ACCOUNT_ID = "test-account"
CLOUDFLARE_API_TOKEN = "test-token"
CLOUDFLARE_STREAM_CUSTOMER_CODE = "customer-code"
# Cloudflare issues signing keys as "<key_id>:<key_secret>"; tests need a
# well-formed value so the HMAC path is exercised rather than short-circuited.
CLOUDFLARE_STREAM_SIGNING_KEY = "test-key-id:test-signing-secret"
CLOUDFLARE_PLAYBACK_TOKEN_TTL = int(env("CLOUDFLARE_PLAYBACK_TOKEN_TTL", "300"))

REST_FRAMEWORK = {  # noqa: F405
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_THROTTLE_RATES": {
        "auth": "1000/min",
        "payment": "1000/min",
        "playback": "1000/min",
        "progress": "1000/min",
        "webhook": "1000/min",
    },
}
