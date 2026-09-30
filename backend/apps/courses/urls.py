"""Course routes, mounted at ``/api/v1/courses/``."""

from django.urls import path

from apps.courses import views

app_name = "courses"

urlpatterns = [
    path("", views.CourseListView.as_view(), name="list"),
    path("<slug:slug>/", views.CourseDetailView.as_view(), name="detail"),
    path(
        "<slug:slug>/lessons/", views.CourseLessonListView.as_view(), name="lesson-list"
    ),
    path("<slug:slug>/access/", views.CourseAccessCheckView.as_view(), name="access"),
]
