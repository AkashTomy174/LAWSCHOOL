"""User/people routes, mounted at ``/api/v1/users/``."""

from django.urls import path

from apps.users.views import MeView, UserDetailView, UserListView

app_name = "users"

urlpatterns = [
    # Instructor/admin view of students; students only ever see themselves.
    path("", UserListView.as_view(), name="list"),
    path("me/", MeView.as_view(), name="me"),
    path("<uuid:pk>/", UserDetailView.as_view(), name="detail"),
]
