"""Progress routes, mounted at ``/api/v1/progress/``."""

from django.urls import path

from apps.videos import views

app_name = "progress"

urlpatterns = [
    path("", views.MyProgressView.as_view(), name="list"),
    path("course/<slug:slug>/", views.CourseProgressView.as_view(), name="course"),
]
