"""Auth URL routes, mounted at ``/api/v1/auth/``."""

from django.urls import path

from apps.users import views

app_name = "auth"

urlpatterns = [
    path("register/", views.RegisterView.as_view(), name="register"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("refresh/", views.RefreshView.as_view(), name="refresh"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("logout-all/", views.LogoutAllView.as_view(), name="logout-all"),
    path("me/", views.MeView.as_view(), name="me"),
    path("session/", views.SessionHeartbeatView.as_view(), name="session"),
    path("verify-email/", views.EmailVerifyView.as_view(), name="verify-email"),
    path(
        "password/change/", views.PasswordChangeView.as_view(), name="password-change"
    ),
    path(
        "password/reset/",
        views.PasswordResetRequestView.as_view(),
        name="password-reset",
    ),
    path(
        "password/reset/confirm/",
        views.PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),
]
