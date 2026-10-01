"""Payment records and webhook event log.

Two tables, two jobs:

* :class:`Payment` -- the authoritative record of *money*.  One row per checkout
  attempt, keyed by the provider order id, and updated only from verified
  server-side facts.
* :class:`WebhookEvent` -- an append-only log of received provider events.  The
  unique constraint on ``(provider, event_id)`` is what makes webhook processing
  idempotent: a duplicate delivery is caught by the database, not by a race-prone
  "check then insert".
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.core.constants import PaymentProvider, PaymentStatus


class Payment(models.Model):
    """A single payment attempt against a plan."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payments"
    )
    plan = models.ForeignKey(
        "subscriptions.Plan", on_delete=models.PROTECT, related_name="payments"
    )
    subscription = models.ForeignKey(
        "subscriptions.Subscription",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
    )

    provider = models.CharField(
        max_length=20, choices=PaymentProvider.choices, default=PaymentProvider.RAZORPAY
    )
    # Provider identifiers. Unique so a replayed order id cannot create a second row.
    provider_order_id = models.CharField(max_length=100, unique=True, db_index=True)
    provider_payment_id = models.CharField(max_length=100, blank=True, db_index=True)
    provider_signature = models.CharField(
        max_length=255,
        blank=True,
        help_text="Verified signature (kept for dispute evidence).",
    )
    provider_refund_id = models.CharField(max_length=100, blank=True)

    amount = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(0)]
    )
    currency = models.CharField(max_length=3, default="INR")

    status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.CREATED,
        db_index=True,
    )
    failure_reason = models.TextField(blank=True)

    # Idempotency key supplied by the client (or generated) so a double-submit
    # returns the same order instead of charging twice.
    idempotency_key = models.CharField(max_length=100, blank=True, db_index=True)

    notes = models.JSONField(default=dict, blank=True)
    # Raw provider payloads for audit -- never exposed through the API.
    provider_payload = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    captured_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = _("payment")
        verbose_name_plural = _("payments")
        indexes = [
            models.Index(fields=["user", "status"], name="payment_user_status_idx"),
            models.Index(
                fields=["status", "created_at"], name="payment_status_created_idx"
            ),
            models.Index(
                fields=["provider_payment_id"], name="payment_provider_pay_idx"
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=[s.value for s in PaymentStatus]),
                name="payment_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(amount__gte=0), name="payment_amount_non_negative"
            ),
            # The database, not the application, owns idempotency: two concurrent
            # requests with the same key cannot both insert a row.
            models.UniqueConstraint(
                fields=["user", "plan", "idempotency_key"],
                condition=~Q(idempotency_key=""),
                name="payment_idempotency_unique",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.provider_order_id} -- {self.amount} {self.currency} ({self.status})"
        )

    @property
    def amount_paise(self) -> int:
        return int(self.amount * 100)

    @property
    def is_settled(self) -> bool:
        return self.status == PaymentStatus.CAPTURED


class WebhookEvent(models.Model):
    """Idempotency ledger for provider webhooks."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.CharField(
        max_length=20, choices=PaymentProvider.choices, default=PaymentProvider.RAZORPAY
    )
    # Razorpay's X-Razorpay-Event-Id header.
    event_id = models.CharField(max_length=120, db_index=True)
    event_type = models.CharField(max_length=100, db_index=True)

    payload = models.JSONField(default=dict)
    payload_hash = models.CharField(max_length=64, blank=True)

    signature_valid = models.BooleanField(default=False)
    processed = models.BooleanField(default=False, db_index=True)
    processing_error = models.TextField(blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    received_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-received_at",)
        verbose_name = _("webhook event")
        verbose_name_plural = _("webhook events")
        constraints = [
            # THE idempotency guarantee: one row per provider event id.
            models.UniqueConstraint(
                fields=["provider", "event_id"],
                name="unique_webhook_event_per_provider",
            ),
        ]
        indexes = [
            models.Index(
                fields=["processed", "received_at"], name="webhook_processed_idx"
            ),
            models.Index(fields=["event_type", "received_at"], name="webhook_type_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.event_type}:{self.event_id}"
