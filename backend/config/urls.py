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


def healthcheck(_request):
    """Liveness probe used by Docker/compose and load balancers."""
    return JsonResponse({"status": "ok", "service": "lawschool-api"})


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
