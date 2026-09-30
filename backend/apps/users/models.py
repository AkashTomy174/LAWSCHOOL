"""Custom user model.

Decisions and trade-offs
------------------------
* **Email is the username.** ``AbstractBaseUser`` + a custom manager is used
  instead of ``AbstractUser`` so no unused ``username`` column exists.  Django's
  own docs recommend this when email is the identifier.
* **Single ``role`` column, not Django Groups.** Roles here are a closed set
  (student/instructor/admin) that drive *coarse* API surface selection, and they
  are read on nearly every request -- a plain indexed column is cheaper than a
  three-table join through the group/permission tables.  Django's permission
  system is still available for fine-grained admin delegation later.
* **Soft deactivation over deletion** (``is_active``): payments and quiz attempts
  must survive an account being disabled for audit and dispute reasons.
"""

from __future__ import annotations

import uuid

from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.constants import UserRole


class UserManager(BaseUserManager):
    """Manager keyed on email rather than username."""

    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("role", UserRole.STUDENT)
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_instructor(self, email: str, password: str | None = None, **extra):
        extra.setdefault("role", UserRole.INSTRUCTOR)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("role", UserRole.ADMIN)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_email_verified", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Platform account.

    ``id`` is a UUID so identifiers exposed in URLs/API payloads cannot be
    enumerated or leak signup order/volume.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    email = models.EmailField(_("email address"), unique=True, db_index=True)
    name = models.CharField(_("full name"), max_length=150)
    phone = models.CharField(
        _("phone"),
        max_length=20,
        blank=True,
        help_text="Optional contact number in E.164 format where possible.",
    )
    role = models.CharField(
        _("role"),
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.STUDENT,
        db_index=True,
    )

    # ---- profile -------------------------------------------------------- #
    avatar = models.ImageField(upload_to="avatars/%Y/%m/", blank=True, null=True)
    bio = models.TextField(_("bio"), blank=True, max_length=1000)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    # Set for instructor accounts; free-text rather than FK so credentials from
    # outside the platform can be recorded without inventing a second model.
    qualification = models.CharField(max_length=200, blank=True)

    # ---- account state -------------------------------------------------- #
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive accounts cannot authenticate but keep their history.",
    )
    is_staff = models.BooleanField(
        default=False, help_text="Grants access to Django admin."
    )
    is_email_verified = models.BooleanField(default=False)

    date_joined = models.DateTimeField(default=timezone.now)
    last_login = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ("-date_joined",)
        indexes = [
            models.Index(fields=["email"], name="user_email_idx"),
            models.Index(fields=["role", "is_active"], name="user_role_active_idx"),
            models.Index(fields=["date_joined"], name="user_joined_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(role__in=[r.value for r in UserRole]),
                name="user_role_valid",
            ),
        ]

    def __str__(self) -> str:
        return self.email

    @property
    def created_at(self) -> models.DateTimeField:
        """Alias kept for API symmetry with other models."""
        return self.date_joined

    def get_full_name(self) -> str:
        return self.name or self.email

    def get_short_name(self) -> str:
        return (self.name or self.email).split(" ")[0]

    # ---- role helpers used by permissions and serializers ---------------- #
    @property
    def is_student(self) -> bool:
        return self.role == UserRole.STUDENT

    @property
    def is_instructor(self) -> bool:
        return self.role == UserRole.INSTRUCTOR

    @property
    def is_admin_role(self) -> bool:
        return self.role == UserRole.ADMIN

    def clean(self) -> None:
        super().clean()
        self.email = self.email.lower().strip() if self.email else self.email
