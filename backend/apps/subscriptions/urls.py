"""Subscription routes, mounted at ``/api/v1/subscriptions/``."""

from django.urls import path

from apps.subscriptions import views

app_name = "subscriptions"

urlpatterns = [
    # Student-facing
    path("plans/", views.PlanListView.as_view(), name="plan-list"),
    path("plans/<slug:slug>/", views.PlanDetailView.as_view(), name="plan-detail"),
    path("me/", views.MySubscriptionView.as_view(), name="me"),
    path("me/cancel/", views.CancelMySubscriptionView.as_view(), name="me-cancel"),
    path("history/", views.SubscriptionHistoryView.as_view(), name="history"),
    # Admin
    path("", views.AdminSubscriptionListView.as_view(), name="admin-list"),
    path(
        "<uuid:pk>/", views.AdminSubscriptionDetailView.as_view(), name="admin-detail"
    ),
]
