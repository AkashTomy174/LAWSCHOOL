"""Leaderboard routes, mounted at ``/api/v1/leaderboard/``."""

from django.urls import path

from apps.leaderboard import views

app_name = "leaderboard"

urlpatterns = [
    path("", views.LeaderboardView.as_view(), name="list"),
    path("top/", views.LeaderboardTopView.as_view(), name="top"),
    path("me/", views.MyRankView.as_view(), name="me"),
    path("snapshots/", views.LeaderboardSnapshotView.as_view(), name="snapshots"),
    path(
        "recalculate/", views.RecalculateLeaderboardView.as_view(), name="recalculate"
    ),
]
