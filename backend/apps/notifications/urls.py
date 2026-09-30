"""Notification routes, mounted at ``/api/v1/notifications/``."""

from django.urls import path

from apps.notifications import views

app_name = "notifications"

urlpatterns = [
    path("", views.NotificationListView.as_view(), name="list"),
    path("unread-count/", views.UnreadCountView.as_view(), name="unread-count"),
    path("read/", views.MarkReadView.as_view(), name="mark-read"),
]
