"""Subscription plans and per-user subscription records.

The entitlement chain required by the spec::

    User ─▶ Subscription ─▶ Plan ─▶ Course access

``Plan.courses`` is an explicit M2M (rather than "all courses") so a plan can be
scoped to a track, and ``Plan.is_all_access`` exists for the common flagship
case without forcing every new course to be attached by hand.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.constants import SubscriptionStatus


class Plan(models.Model):
    """A purchasable access tier."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, db_index=True)
    description = models.TextField(blank=True)

    price = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(0)]
    )
    currency = models.CharField(max_length=3, default="INR")
    duration_days = models.PositiveIntegerField(
        default=365, help_text="Length of access granted when the payment settles."
    )

    courses = models.ManyToManyField(
        "courses.Course",
        blank=True,
        related_name="plans",
        help_text="Courses unlocked by this plan.",
    )
    is_all_access = models.BooleanField(
        default=False,
        help_text="When true, every published course is unlocked (overrides the M2M).",
    )

    is_active = models.BooleanField(default=True, db_index=True)
    is_featured = models.BooleanField(default=False)
    ordering = models.PositiveIntegerField(default=1)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("ordering", "price")
        verbose_name = _("plan")
        verbose_name_plural = _("plans")
        indexes = [
            models.Index(
                fields=["is_active", "ordering"], name="plan_active_order_idx"
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(price__gte=0), name="plan_price_non_negative"
            ),
            models.CheckConstraint(
                condition=Q(duration_days__gt=0), name="plan_duration_positive"
            ),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def price_paise(self) -> int:
        """Razorpay expects the smallest currency unit (paise)."""
        return int(self.price * 100)


class Subscription(models.Model):
    """A user's entitlement window for a plan.

    Status transitions are owned by ``apps.subscriptions.services``; the model
    only encodes the invariants (valid status, end after start).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )
    plan = models.ForeignKey(
        Plan, on_delete=models.PROTECT, related_name="subscriptions"
    )

    status = models.CharField(
        max_length=20,
        choices=SubscriptionStatus.choices,
        default=SubscriptionStatus.PENDING,
        db_index=True,
    )
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True, db_index=True)

    # Reference to the payment that created/activated this subscription.
    payment_reference = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        help_text="Provider payment id (e.g. Razorpay pay_xxx).",
    )

    # Set when a user cancels; access continues until end_date.
    cancelled_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = _("subscription")
        verbose_name_plural = _("subscriptions")
        indexes = [
            # The single hottest query in the system:
            # "does this user have a currently active subscription?".
            models.Index(
                fields=["user", "status", "end_date"], name="sub_user_status_end_idx"
            ),
            models.Index(fields=["status", "end_date"], name="sub_status_end_idx"),
            models.Index(fields=["payment_reference"], name="sub_payment_ref_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=[s.value for s in SubscriptionStatus]),
                name="subscription_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(end_date__isnull=True)
                | Q(start_date__isnull=True)
                | Q(end_date__gte=models.F("start_date")),
                name="subscription_end_after_start",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user.email} -- {self.plan.name} ({self.status})"

    # ---- derived state (never trust a status string alone) ---------------- #
    @property
    def is_currently_active(self) -> bool:
        """True only when status is ACTIVE *and* now is inside the window.

        Relying on ``status`` alone would keep access alive for rows that a
        crashed expiry job never flipped, so the date window is always checked.
        """
        if self.status != SubscriptionStatus.ACTIVE:
            return False
        now = timezone.now()
        if self.start_date and self.start_date > now:
            return False
        if self.end_date and self.end_date <= now:
            return False
        return True

    @property
    def days_remaining(self) -> int:
        if not self.end_date:
            return 0
        delta = self.end_date - timezone.now()
        return max(0, delta.days)

    def covers_course(self, course) -> bool:
        """Whether this (active) subscription's plan unlocks ``course``."""
        if not self.is_currently_active:
            return False
        if self.plan.is_all_access:
            return True
        return self.plan.courses.filter(pk=course.pk).exists()
