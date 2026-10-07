"""Local development settings -- verbose errors, permissive CORS, no HTTPS."""

from .base import *  # noqa: F401,F403
from .base import env_bool

DEBUG = True

ALLOWED_HOSTS = ["*"]

# Development should not require Redis: the cache is an optimisation, not a
# dependency.  Override with CACHE_BACKEND=redis when running the full stack.
import os as _os  # noqa: E402

if _os.environ.get("CACHE_BACKEND", "locmem") == "locmem":
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "lawschool-dev",
            "TIMEOUT": 300,
        }
    }

# Anything on localhost may call the API during development.
CORS_ALLOW_ALL_ORIGINS = True
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8000",
]

# Console email keeps password-reset links visible in the runserver output.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Run Celery tasks inline so the dev loop needs no broker.
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", True)

# Rate limits are relaxed locally to keep test/dev scripts usable.
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
