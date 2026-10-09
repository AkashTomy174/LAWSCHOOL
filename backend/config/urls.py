"""Root URL configuration.

Everything versioned lives under ``/api/v1/``.  Payment webhooks are mounted at
``/api/v1/payments/webhook/`` and are CSRF-exempt by virtue of being a plain
Django/DRF view with ``authentication_classes = []``.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from apps.core.logging import get_logger

logger = get_logger(__name__)


def healthcheck(_request):
    """Liveness probe used by Docker/compose and load balancers."""
    return JsonResponse({"status": "ok", "service": "lawschool-api"})


def _database_ok() -> None:
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")


def readiness(_request):
    """Readiness probe: can this instance serve traffic?

    The database is required (503 without it).  The cache is reported but not
    required: the app degrades without Redis (see apps.core.cache), so a cache
    outage must not keep every instance out of rotation.  Only "ok"/"error" is
    returned; details go to the logs, never to the caller.
    """
    from apps.core.cache import report_cache_failure

    checks = {}
    try:
        _database_ok()
        checks["database"] = "ok"
    except Exception:
        logger.exception("Readiness: database check failed")
        checks["database"] = "error"
    try:
        from django.core.cache import cache

        cache.get("health:ready")
        checks["cache"] = "ok"
    except Exception as exc:
        report_cache_failure("health", exc)
        checks["cache"] = "error"

    ready = checks["database"] == "ok"
    return JsonResponse(
        {"status": "ok" if ready else "unavailable", "checks": checks},
        status=200 if ready else 503,
    )


api_v1 = [
    path("auth/", include("apps.users.urls_auth")),
    path("users/", include("apps.users.urls")),
    path("courses/", include("apps.courses.urls")),
    path("sections/", include("apps.courses.urls_sections")),
    path("lessons/", include("apps.courses.urls_lessons")),
    path("videos/", include("apps.videos.urls")),
    path("progress/", include("apps.videos.urls_progress")),
    path("subscriptions/", include("apps.subscriptions.urls")),
    path("payments/", include("apps.payments.urls")),
    path("quizzes/", include("apps.quizzes.urls")),
    path("quiz-attempts/", include("apps.quizzes.urls_attempts")),
    path("live-classes/", include("apps.live.urls")),
    path("leaderboard/", include("apps.leaderboard.urls")),
    path("notifications/", include("apps.notifications.urls")),
]

urlpatterns = [
    path("health/", healthcheck, name="healthcheck"),
    path("health/ready/", readiness, name="readiness"),
    path("admin/", admin.site.urls),
    path("api/v1/", include((api_v1, "v1"))),
    # OpenAPI schema + interactive docs.
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path(
        "api/redoc/",
        SpectacularRedocView.as_view(url_name="schema"),
        name="redoc",
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

admin.site.site_header = "LawSchool Administration"
admin.site.site_title = "LawSchool Admin"
admin.site.index_title = "Platform administration"
