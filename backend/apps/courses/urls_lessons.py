"""Lesson routes, mounted at ``/api/v1/lessons/``."""

from django.urls import path

from apps.courses import views

app_name = "lessons"

urlpatterns = [
    path("", views.LessonListCreateView.as_view(), name="list"),
    path("<uuid:pk>/", views.LessonDetailView.as_view(), name="detail"),
    path("<uuid:pk>/watch/", views.LessonWatchView.as_view(), name="watch"),
]
