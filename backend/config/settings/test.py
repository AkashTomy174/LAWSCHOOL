"""
Settings used by the pytest suite.

Key properties:
* in-memory sqlite by default.  Only ``TEST_DATABASE_URL`` selects another
  database (CI uses it for PostgreSQL).  ``DATABASE_URL`` is deliberately
  ignored: ``base.py`` loads ``backend/.env``, so honouring it pointed the suite
  at whatever development database the .env names.
* locmem cache so tests never touch a Redis instance
* Celery runs eagerly and synchronously
* throttling effectively disabled unless a test opts in
"""

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = False

# In-memory sqlite keeps the suite fast.  SQLite does not exercise PostgreSQL
# locking (select_for_update), constraint timing or concurrency; CI runs the same
# suite with TEST_DATABASE_URL=postgres://... to cover those.
if env("TEST_DATABASE_URL"):
    DATABASES = {  # noqa: F405
        "default": dj_database_url.parse(  # noqa: F405
            env("TEST_DATABASE_URL"), conn_max_age=0, conn_health_checks=False
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

# base.py picks the manifest storage whenever DEBUG is off, which needs
# ``collectstatic`` output; tests (e.g. admin login pages) must not depend on it
# -- nor on a developer's .env happening to set DEBUG=True.
STORAGES = {  # noqa: F405
    **STORAGES,  # noqa: F405
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Deterministic fake credentials so signature tests are reproducible.
RAZORPAY_KEY_ID = "rzp_test_key"
# Never read from the environment: .env may hold real (test-mode) gateway keys.
RAZORPAY_KEY_SECRET = "rzp-sec-test"
RAZORPAY_WEBHOOK_SECRET = "whsec-test"

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
        "webhook_razorpay": "1000/min",
        "webhook_whatsapp": "1000/min",
        "video_upload": "1000/min",
        "whatsapp_link": "1000/min",
        "whatsapp_link_ip": "1000/min",
        "whatsapp_verify": "1000/min",
        "whatsapp_admin": "1000/min",
    },
}

# WhatsApp: off by default in tests; tests that need it override via settings fixture.
WHATSAPP_ENABLED = False
WHATSAPP_PHONE_NUMBER_ID = "1234567890"
WHATSAPP_ACCESS_TOKEN = "test-access-token-SECRET"
WHATSAPP_APP_SECRET = "test-app-secret"
WHATSAPP_VERIFY_TOKEN = "test-verify-token"
