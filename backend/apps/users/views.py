"""Authentication endpoints: register, login, refresh, logout, me, passwords.

All views are thin.  Authorization decisions that matter (``is_active``,
token validity, blacklisting) are enforced server-side by SimpleJWT and the
services layer -- never by the SPA.
"""

from __future__ import annotations

from django.contrib.auth.hashers import make_password
from django.db import IntegrityError
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.core.throttling import ResilientScopedRateThrottle
from apps.core.logging import get_logger
from apps.core.permissions import IsAdminRole
from apps.users import services
from apps.users.models import LastAdminError, User
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
    throttle_classes = [ResilientScopedRateThrottle]
    throttle_scope = "auth"

    @extend_schema(
        summary="Register a student",
        responses={
            202: OpenApiResponse(description="Accepted (same body for any email)"),
            400: OpenApiResponse(description="Validation error"),
        },
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # The answer is identical whether or not the address is already registered
        # (no tokens, no user object), so this endpoint cannot be used to test which
        # emails have accounts.  A new address gets its account + verification
        # email; an existing one gets a password-reset email to its real owner.
        if User.objects.filter(email=data["email"]).exists():
            # Pay the same password-hashing cost as a real sign-up, so response
            # time does not reveal that the address is taken.
            make_password(data["password"])
            services.request_password_reset(data["email"])
        else:
            try:
                services.create_student(**data)
            except IntegrityError:
                # Lost a race with a concurrent registration of the same address.
                # Only that specific cause is swallowed; anything else propagates.
                if not User.objects.filter(email=data["email"]).exists():
                    raise
                services.request_password_reset(data["email"])
        return Response(
            {
                "detail": (
                    "If this email can be registered, your account is ready and a "
                    "verification email is on its way. If you already have an "
                    "account, use Sign in or reset your password."
                )
            },
            status=status.HTTP_202_ACCEPTED,
        )


class LoginView(TokenObtainPairView):
    """POST /api/v1/auth/login/ -- email + password -> access/refresh pair."""

    serializer_class = EmailTokenObtainPairSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ResilientScopedRateThrottle]
    throttle_scope = "auth"


class RefreshView(TokenRefreshView):
    """POST /api/v1/auth/refresh/ -- rotate the refresh token.

    ``ROTATE_REFRESH_TOKENS`` + ``BLACKLIST_AFTER_ROTATION`` mean the old token
    is invalidated, so a stolen refresh token has a single-use window.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ResilientScopedRateThrottle]
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
            token = RefreshToken(raw_refresh)
            if str(token.get("user_id")) != str(request.user.pk):
                # Someone else's token: refuse silently.  Same response as an
                # invalid one, so this cannot be used to probe other sessions.
                logger.warning(
                    "Logout attempted with a refresh token owned by another user",
                    extra={"user_id": str(request.user.pk)},
                )
            else:
                token.blacklist()
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
    throttle_classes = [ResilientScopedRateThrottle]
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
    throttle_classes = [ResilientScopedRateThrottle]
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
    throttle_classes = [ResilientScopedRateThrottle]
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

    def perform_update(self, serializer):
        user = serializer.instance
        deactivating = serializer.validated_data.get("is_active") is False
        if deactivating and user.pk == self.request.user.pk:
            # Locking yourself out leaves no admin to undo it.
            raise ValidationError({"is_active": "You cannot deactivate your own account."})
        new_role = serializer.validated_data.get("role")
        if (
            user.pk == self.request.user.pk
            and new_role is not None
            and new_role != user.role
        ):
            # Demoting yourself is irreversible without another admin.
            raise ValidationError({"role": "You cannot change your own role."})
        was_active = user.is_active
        try:
            updated = serializer.save()
        except LastAdminError:
            raise ValidationError(
                {"role": "At least one active administrator must remain."}
            )
        if was_active and not updated.is_active:
            # Access tokens already fail for inactive users; also make sure no
            # open session can be renewed.
            services.blacklist_user_refresh_tokens(updated)
