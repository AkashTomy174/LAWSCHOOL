"""Authentication endpoints: register, login, refresh, logout, me, passwords.

All views are thin.  Authorization decisions that matter (``is_active``,
token validity, blacklisting) are enforced server-side by SimpleJWT and the
services layer -- never by the SPA.
"""

from __future__ import annotations

from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.core.logging import get_logger
from apps.core.permissions import IsAdminRole
from apps.users import services
from apps.users.models import User
from apps.users.serializers import (
    AdminUserSerializer,
    EmailTokenObtainPairSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    ProfileUpdateSerializer,
    RegisterSerializer,
    UserSerializer,
)

logger = get_logger(__name__)


class RegisterView(generics.CreateAPIView):
    """POST /api/v1/auth/register/ -- create a student account."""

    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    @extend_schema(
        summary="Register a student",
        responses={
            201: UserSerializer,
            400: OpenApiResponse(description="Validation error"),
        },
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = services.create_student(**serializer.validated_data)

        # Issue tokens immediately so registration is a single round trip.
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "user": UserSerializer(user).data,
                "tokens": {
                    "access": str(refresh.access_token),
                    "refresh": str(refresh),
                },
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(TokenObtainPairView):
    """POST /api/v1/auth/login/ -- email + password -> access/refresh pair."""

    serializer_class = EmailTokenObtainPairSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


class RefreshView(TokenRefreshView):
    """POST /api/v1/auth/refresh/ -- rotate the refresh token.

    ``ROTATE_REFRESH_TOKENS`` + ``BLACKLIST_AFTER_ROTATION`` mean the old token
    is invalidated, so a stolen refresh token has a single-use window.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "token_refresh"


class LogoutView(APIView):
    """POST /api/v1/auth/logout/ -- blacklist the supplied refresh token."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request={
            "application/json": {
                "type": "object",
                "properties": {"refresh": {"type": "string"}},
            }
        },
        summary="Log out (blacklist refresh token)",
    )
    def post(self, request):
        raw_refresh = request.data.get("refresh")
        if not raw_refresh:
            # Logout is idempotent: a client without the token is already logged out.
            return Response(
                {"detail": "Logged out."}, status=status.HTTP_205_RESET_CONTENT
            )
        try:
            RefreshToken(raw_refresh).blacklist()
        except TokenError:
            # Already expired/blacklisted -- the desired end state holds.
            logger.info(
                "Logout with unusable refresh token",
                extra={"user_id": str(request.user.pk)},
            )
        return Response({"detail": "Logged out."}, status=status.HTTP_205_RESET_CONTENT)


class LogoutAllView(APIView):
    """POST /api/v1/auth/logout-all/ -- revoke every session for this account."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        revoked = services.blacklist_user_refresh_tokens(request.user)
        return Response({"detail": f"Revoked {revoked} session(s)."})


class MeView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/v1/auth/me/ -- current profile.

    Split serializers keep ``role``/``email``/``is_email_verified`` read-only:
    a PATCH can never escalate privileges.
    """

    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        return (
            ProfileUpdateSerializer
            if self.request.method in {"PATCH", "PUT"}
            else UserSerializer
        )

    def get_object(self):
        return self.request.user

    def update(self, request, *args, **kwargs):
        super().update(request, *args, **kwargs)
        # Always return the full representation so the client store stays complete.
        return Response(UserSerializer(self.request.user).data)


class EmailVerifyView(APIView):
    """POST /api/v1/auth/verify-email/ -- confirm an email-verification token."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    @extend_schema(
        request={
            "application/json": {
                "type": "object",
                "properties": {"uid": {"type": "string"}, "token": {"type": "string"}},
            }
        },
        summary="Verify an email address",
    )
    def post(self, request):
        user = services.verify_email_token(
            uid=request.data.get("uid", ""), token=request.data.get("token", "")
        )
        return Response(
            {"detail": "Email verified.", "user": UserSerializer(user).data}
        )


class PasswordChangeView(APIView):
    """POST /api/v1/auth/password/change/ -- change password while signed in."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=PasswordChangeSerializer, summary="Change password")
    def post(self, request):
        serializer = PasswordChangeSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        # Force other devices to re-authenticate after a password change.
        revoked = services.blacklist_user_refresh_tokens(user)
        logger.info(
            "Password changed",
            extra={"user_id": str(user.pk), "sessions_revoked": revoked},
        )
        return Response({"detail": "Password updated. Please sign in again."})


class PasswordResetRequestView(APIView):
    """POST /api/v1/auth/password/reset/ -- request a reset email (always 200)."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    @extend_schema(
        request=PasswordResetRequestSerializer, summary="Request password reset"
    )
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.request_password_reset(serializer.validated_data["email"])
        return Response(
            {
                "detail": "If an account exists for that email, a reset link has been sent."
            }
        )


class PasswordResetConfirmView(APIView):
    """POST /api/v1/auth/password/reset/confirm/ -- set a new password."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    @extend_schema(
        request=PasswordResetConfirmSerializer, summary="Confirm password reset"
    )
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.confirm_password_reset(
            uid=serializer.validated_data["uid"],
            token=serializer.validated_data["token"],
            new_password=serializer.validated_data["new_password"],
        )
        return Response({"detail": "Password has been reset. You can now sign in."})


class SessionHeartbeatView(APIView):
    """GET /api/v1/auth/session/ -- cheap call for the SPA to confirm the token still works."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            {
                "authenticated": True,
                "role": request.user.role,
                "server_time": timezone.now(),
            }
        )


class UserListView(generics.ListAPIView):
    """GET /api/v1/users/ -- people directory, administrators only.

    The listing exposes every account's email and phone number, so it is not
    available to students *or* instructors.  Results are paginated.
    """

    serializer_class = UserSerializer
    permission_classes = [IsAdminRole]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["role", "is_active"]
    search_fields = ["email", "name"]
    ordering_fields = ["date_joined", "name"]
    ordering = ["-date_joined"]

    def get_queryset(self):
        from apps.users.selectors import user_list

        params = self.request.query_params
        return user_list(
            role=params.get("role"),
            is_active=(
                None if "is_active" not in params else params.get("is_active") == "true"
            ),
            search=params.get("search"),
        )


class UserDetailView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/v1/users/<uuid>/ -- admins only.

    Object-level permission is enforced by ``IsAdminRole`` plus the queryset
    filter, so a student requesting another UUID gets 403/404 rather than data.
    """

    serializer_class = AdminUserSerializer
    permission_classes = [IsAdminRole]
    queryset = User.objects.all()
    lookup_field = "pk"
