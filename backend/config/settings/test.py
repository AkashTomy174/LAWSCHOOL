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
RAZORPAY_KEY_SECRET = env("RAZORPAY_KEY_SECRET") or "rzp-sec-test"
RAZORPAY_WEBHOOK_SECRET = env("RAZORPAY_WEBHOOK_SECRET") or "whsec-test"

CLOUDFLARE_ACCOUNT_ID = "test-account"
CLOUDFLARE_API_TOKEN = "test-token"
CLOUDFLARE_STREAM_CUSTOMER_CODE = "customer-code"
# Cloudflare signing keys are RSA (RS256).  Generate a throwaway keypair so the
# real signing path runs in tests; nothing here is a credential.
import base64 as _base64

from cryptography.hazmat.primitives import serialization as _serialization
from cryptography.hazmat.primitives.asymmetric import rsa as _rsa

_test_rsa_key = _rsa.generate_private_key(public_exponent=65537, key_size=2048)
CLOUDFLARE_STREAM_KEY_ID = "test-key-id"
CLOUDFLARE_STREAM_SIGNING_KEY = _base64.b64encode(
    _test_rsa_key.private_bytes(
        _serialization.Encoding.PEM,
        _serialization.PrivateFormat.PKCS8,
        _serialization.NoEncryption(),
    )
).decode()
TEST_CLOUDFLARE_PUBLIC_KEY = _test_rsa_key.public_key()
CLOUDFLARE_PLAYBACK_TOKEN_TTL = int(env("CLOUDFLARE_PLAYBACK_TOKEN_TTL", "300"))

REST_FRAMEWORK = {  # noqa: F405
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_THROTTLE_RATES": {
        "auth": "1000/min",
        "token_refresh": "1000/min",
        "payment": "1000/min",
        "playback": "1000/min",
        "progress": "1000/min",
        "webhook": "1000/min",
    },
}
