"""Live class routes, mounted at ``/api/v1/live-classes/``."""

from django.urls import path

from apps.live import views

app_name = "live"

urlpatterns = [
    path("", views.CourseLiveClassListView.as_view(), name="list"),
    path(
        "manage/", views.LiveClassListCreateView.as_view(), name="manage-list"
    ),
    path(
        "manage/<uuid:pk>/",
        views.LiveClassDetailView.as_view(),
        name="manage-detail",
    ),
    path("<uuid:pk>/join/", views.LiveClassJoinView.as_view(), name="join"),
]
