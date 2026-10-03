"""User business logic (registration, verification, password reset).

Views stay thin: they validate input with serializers, call a service, and map
the result to a response.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth.tokens import (
    PasswordResetTokenGenerator,
    default_token_generator,
)
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from apps.core.logging import get_logger
from apps.users.models import User

logger = get_logger(__name__)


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    """Verification tokens that are useless as password-reset tokens.

    Sharing ``default_token_generator`` meant a leaked verification link was
    also a working password-reset link.  A distinct salt separates the two, and
    hashing ``is_email_verified`` makes each link single-use.
    """

    key_salt = "apps.users.services.EmailVerificationTokenGenerator"

    def _make_hash_value(self, user, timestamp) -> str:
        return f"{user.pk}{user.is_email_verified}{timestamp}"


email_verification_token = EmailVerificationTokenGenerator()


def create_student(*, email: str, name: str, password: str, phone: str = "") -> User:
    """Register a student account and queue the verification email.

    The account is created *active* but ``is_email_verified=False``: students can
    buy and watch immediately, while the flag still drives reminders/notifications.
    Blocking login until verification would add friction without adding security
    for a paid-content product.
    """
    user = User.objects.create_user(
        email=email, password=password, name=name, phone=phone, role="student"
    )
    # Imported lazily: notifications must not be a hard dependency of user creation.
    try:
        from apps.notifications.services import notify_user

        notify_user(
            user=user,
            kind="account_verification",
            context={"verify_url": build_email_verification_url(user)},
        )
    except Exception:  # pragma: no cover - notification failure is never fatal
        logger.exception(
            "Failed to queue verification notification", extra={"user_id": str(user.pk)}
        )
    return user


def build_email_verification_url(user: User) -> str:
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = email_verification_token.make_token(user)
    return f"{settings.FRONTEND_URL}/verify-email?uid={uid}&token={token}"


def verify_email_token(*, uid: str, token: str) -> User:
    """Validate an email-verification token and mark the account verified."""
    from apps.core.exceptions import DomainError

    user = _user_from_uid(uid)
    if user is None or not email_verification_token.check_token(user, token):
        raise DomainError(
            {"detail": "This verification link is invalid or has expired."},
            code="invalid_token",
        )
    if not user.is_email_verified:
        user.is_email_verified = True
        user.save(update_fields=["is_email_verified", "updated_at"])
    return user


def request_password_reset(email: str) -> None:
    """Send a reset link if the account exists -- always silently.

    Returning the same response for known and unknown addresses prevents
    attackers from using this endpoint to enumerate registered emails.
    """
    user = User.objects.filter(email=email.strip().lower(), is_active=True).first()
    if user is None:
        logger.info("Password reset requested for unknown email")
        return

    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    reset_url = f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}"

    from apps.notifications.services import notify_user

    notify_user(user=user, kind="password_reset", context={"reset_url": reset_url})


def confirm_password_reset(*, uid: str, token: str, new_password: str) -> User:
    """Set a new password after validating the reset token.

    ``set_password`` hashes via the configured hasher (PBKDF2 by default) -- the
    plaintext is never persisted or logged.
    """
    from apps.core.exceptions import DomainError

    user = _user_from_uid(uid)
    if user is None or not default_token_generator.check_token(user, token):
        raise DomainError(
            {"detail": "This reset link is invalid or has expired."},
            code="invalid_token",
        )

    try:
        from django.contrib.auth.password_validation import validate_password

        validate_password(new_password, user=user)
    except DjangoValidationError as exc:
        raise DomainError({"new_password": list(exc.messages)}, code="weak_password")

    user.set_password(new_password)
    user.save(update_fields=["password", "updated_at"])

    # Invalidate every existing refresh token: a password reset must not leave
    # previously issued sessions usable.
    blacklist_user_refresh_tokens(user)
    return user


def blacklist_user_refresh_tokens(user: User) -> int:
    """Revoke outstanding refresh tokens for a user (logout / reset / role change)."""
    from rest_framework_simplejwt.token_blacklist.models import (
        BlacklistedToken,
        OutstandingToken,
    )

    outstanding = OutstandingToken.objects.filter(user=user)
    created = 0
    for token in outstanding.iterator():
        _, was_created = BlacklistedToken.objects.get_or_create(token=token)
        created += int(was_created)
    return created


def _user_from_uid(uid: str) -> User | None:
    try:
        pk = force_str(urlsafe_base64_decode(uid))
    except (TypeError, ValueError, OverflowError):
        return None
    return User.objects.filter(pk=pk, is_active=True).first()
