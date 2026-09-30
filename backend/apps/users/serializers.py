"""User serializers.

Validation lives here (DRF's job); business decisions live in ``services.py``.
Password policy is delegated to Django's configured validators so all four
``AUTH_PASSWORD_VALIDATORS`` are enforced consistently.
"""

from __future__ import annotations

from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.core.constants import UserRole
from apps.users.models import User


class UserSerializer(serializers.ModelSerializer):
    """Public representation of an account. Never exposes password material."""

    role_display = serializers.CharField(source="get_role_display", read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "name",
            "phone",
            "role",
            "role_display",
            "avatar",
            "bio",
            "city",
            "state",
            "qualification",
            "is_email_verified",
            "date_joined",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "email",
            "role",
            "is_email_verified",
            "date_joined",
            "updated_at",
        )


class PublicUserSerializer(serializers.ModelSerializer):
    """Minimal shape safe to embed in course/leaderboard payloads."""

    class Meta:
        model = User
        fields = ("id", "name", "avatar", "role")


class RegisterSerializer(serializers.ModelSerializer):
    """Student self-registration.

    ``role`` is intentionally *not* writable: a payload cannot promote itself to
    instructor or admin.  Elevated roles are only assignable from Django admin.
    """

    password = serializers.CharField(
        write_only=True,
        min_length=10,
        style={"input_type": "password"},
        trim_whitespace=False,
    )
    password_confirm = serializers.CharField(
        write_only=True, style={"input_type": "password"}
    )

    class Meta:
        model = User
        fields = ("email", "name", "phone", "password", "password_confirm")

    def validate_email(self, value: str) -> str:
        email = value.strip().lower()
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError(
                "An account with this email already exists."
            )
        return email

    def validate(self, attrs: dict) -> dict:
        if attrs["password"] != attrs.pop("password_confirm"):
            raise serializers.ValidationError(
                {"password_confirm": "Passwords do not match."}
            )
        # Run Django's configured validators (length, common, numeric, similarity).
        probe = User(email=attrs["email"], name=attrs.get("name", ""))
        validate_password(attrs["password"], user=probe)
        return attrs

    def create(self, validated_data: dict) -> User:
        return User.objects.create_user(**validated_data)


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Adds role/name claims to the tokens so the SPA can render without a 2nd call.

    Only non-sensitive claims are embedded -- never permissions that the backend
    then *trusts* for authorization.
    """

    username_field = User.USERNAME_FIELD

    @classmethod
    def get_token(cls, user: User):
        token = super().get_token(user)
        token["role"] = user.role
        token["name"] = user.get_full_name()
        token["email"] = user.email
        return token

    def validate(self, attrs: dict) -> dict:
        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user).data
        return data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # SimpleJWT's default error ("No active account found with the given
        # credentials") is fine, but make the message explicit for the UI.
        self.fields[self.username_field].error_messages[
            "required"
        ] = "Email is required."
        self.fields["password"].error_messages["required"] = "Password is required."


class LoginSerializer(serializers.Serializer):
    """Plain credential serializer used when we need ``authenticate()`` semantics."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs: dict) -> dict:
        user = authenticate(
            request=self.context.get("request"),
            username=attrs["email"].strip().lower(),
            password=attrs["password"],
        )
        if user is None:
            raise serializers.ValidationError(
                {"non_field_errors": ["Invalid email or password."]},
                code="authorization",
            )
        if not user.is_active:
            raise serializers.ValidationError(
                {"non_field_errors": ["This account has been disabled."]},
                code="authorization",
            )
        attrs["user"] = user
        return attrs


class ProfileUpdateSerializer(serializers.ModelSerializer):
    """Fields a student/instructor may edit on their own profile."""

    class Meta:
        model = User
        fields = ("name", "phone", "bio", "city", "state", "qualification", "avatar")

    def validate_phone(self, value: str) -> str:
        cleaned = value.strip()
        if (
            cleaned
            and not cleaned.replace("+", "").replace("-", "").replace(" ", "").isdigit()
        ):
            raise serializers.ValidationError("Enter a valid phone number.")
        return cleaned

    def validate_avatar(self, value):
        if value is None:
            return value
        from apps.core.validators import validate_image_upload

        if hasattr(value, "size"):
            validate_image_upload(value)
        return value


class PasswordChangeSerializer(serializers.Serializer):
    """Authenticated password change -- requires the current password."""

    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(
        write_only=True, min_length=10, trim_whitespace=False
    )
    new_password_confirm = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_current_password(self, value: str) -> str:
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate(self, attrs: dict) -> dict:
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": "Passwords do not match."}
            )
        validate_password(attrs["new_password"], user=self.context["request"].user)
        return attrs

    @transaction.atomic
    def save(self, **kwargs) -> User:
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password", "updated_at"])
        return user


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value: str) -> str:
        # Deliberately does NOT reveal whether the address exists: the view
        # always returns the same response to avoid account enumeration.
        return value.strip().lower()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(
        write_only=True, min_length=10, trim_whitespace=False
    )
    new_password_confirm = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs: dict) -> dict:
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": "Passwords do not match."}
            )
        return attrs


class AdminUserSerializer(UserSerializer):
    """Admin-only: allows changing role and activation state."""

    class Meta(UserSerializer.Meta):
        read_only_fields = ("id", "date_joined", "updated_at")
