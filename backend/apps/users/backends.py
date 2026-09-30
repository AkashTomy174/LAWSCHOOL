"""Authentication backends.

Why a custom backend at all: the stock ``ModelBackend`` performs an exact match
on ``USERNAME_FIELD``, so a user who typed ``Student@Test.com`` at signup and
``student@test.com`` at login would be told their password was wrong.

Emails are stored lower-cased (see ``UserManager._create_user`` and
``User.clean``), so the fix is to normalise the *input* before lookup.  The
lookup itself stays parameterised through the ORM, so there is no injection
surface.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

UserModel = get_user_model()


class EmailBackend(ModelBackend):
    """Case-insensitive email/password authentication."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        email = username or kwargs.get(UserModel.USERNAME_FIELD)
        if email is None or password is None:
            return None

        try:
            user = UserModel._default_manager.get(email=email.strip().lower())
        except UserModel.DoesNotExist:
            # Run the hasher once anyway so a missing account and a wrong password
            # take a similar amount of time (avoids user enumeration by timing).
            UserModel().set_password(password)
            return None
        except UserModel.MultipleObjectsReturned:  # pragma: no cover - data corruption
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None

    def user_can_authenticate(self, user) -> bool:
        """Reject inactive accounts -- the stock check, kept explicit here."""
        return bool(getattr(user, "is_active", True))
