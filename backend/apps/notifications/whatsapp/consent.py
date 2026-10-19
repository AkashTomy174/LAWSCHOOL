"""WhatsApp number linking, one-time-code verification, consent and opt-out.

A number typed into a profile is never trusted.  Linking needs (1) an explicit
consent flag, (2) a one-time code delivered *to that WhatsApp number* and (3) the
code echoed back within 10 minutes and 5 attempts.  Only then is the number marked
verified -- and a verified number belongs to exactly one account (DB constraint),
which is what lets the inbound assistant trust the sender.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from apps.core.logging import get_logger
from apps.notifications.models import (
    Category,
    ConsentStatus,
    NotificationPreference,
    NotificationStatus,
    Notification,
    WhatsAppVerification,
)
from apps.core.constants import NotificationChannel
from apps.notifications.whatsapp import client
from apps.notifications.whatsapp.service import audit
from apps.notifications.whatsapp.templates import SPECS

logger = get_logger(__name__)

CODE_TTL = timedelta(minutes=10)
RESEND_COOLDOWN = timedelta(seconds=60)
MAX_ATTEMPTS = 5

PREFERENCE_FIELDS = [f"{c.value}_enabled" for c in Category]


class ConsentError(Exception):
    """User-facing failure; ``message`` is safe to show."""

    def __init__(self, message: str, *, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def get_preferences(user) -> NotificationPreference:
    return NotificationPreference.objects.get_or_create(user=user)[0]


def _hash_code(user_id, number: str, code: str) -> str:
    msg = f"{user_id}:{number}:{code}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()


def _consume_daily_otp_budget() -> None:
    """Take one slot from the platform-wide daily OTP budget, or refuse.

    Every code is a paid template message to an arbitrary number, so a flood of
    cheap accounts must hit a ceiling that is shared by all workers.  The counter
    lives in the shared cache (atomic ``incr``).  If the cache is unreachable the
    request is refused: failing open would remove the only global spend limit.
    """
    cap = settings.WHATSAPP_OTP_DAILY_CAP
    key = f"wa:otp:global:{timezone.now().date().isoformat()}"
    try:
        cache.add(key, 0, 2 * 86400)
        used = cache.incr(key)
    except Exception as exc:
        logger.warning("WhatsApp OTP budget unavailable", extra={"error": type(exc).__name__})
        raise ConsentError(
            "WhatsApp verification is temporarily unavailable. Please try again later.",
            status=503,
        ) from None
    if used > cap:
        logger.warning("WhatsApp OTP daily cap reached", extra={"cap": cap})
        raise ConsentError(
            "WhatsApp verification is temporarily unavailable. Please try again later.",
            status=503,
        )


def request_link(user, raw_number: str, *, consent: bool) -> str:
    """Start verification; returns the normalised number (masked by the caller)."""
    if not settings.WHATSAPP_ENABLED:
        raise ConsentError("WhatsApp notifications are not available yet.", status=503)
    if not user.is_email_verified:
        # Throwaway accounts are free; a verified mailbox is the minimum cost of
        # triggering a paid message to someone else's number.
        raise ConsentError("Verify your email address before linking WhatsApp.", status=403)
    if consent is not True:
        raise ConsentError("You must agree to receive WhatsApp messages to continue.")
    try:
        number = client.normalize_phone(raw_number)
    except ValueError as exc:
        raise ConsentError(str(exc)) from None

    last = user.whatsapp_verifications.order_by("-created_at").first()
    if last and timezone.now() - last.created_at < RESEND_COOLDOWN:
        raise ConsentError("Please wait a minute before requesting another code.", status=429)

    # Counted before the "number taken" branch so the response (and the budget)
    # is identical whether or not another account owns the number.
    _consume_daily_otp_budget()

    # Same response whether or not another account owns the number: never reveal
    # who is registered.  We simply do not send the code in that case.
    taken = (
        NotificationPreference.objects.filter(
            whatsapp_number=number, whatsapp_verified_at__isnull=False
        )
        .exclude(user=user)
        .exists()
    )
    code = f"{secrets.randbelow(10**6):06d}"
    with transaction.atomic():
        user.whatsapp_verifications.filter(consumed_at__isnull=True).delete()
        verification = WhatsAppVerification.objects.create(
            user=user,
            number=number,
            code_hash=_hash_code(user.pk, number, code),
            expires_at=timezone.now() + CODE_TTL,
        )
    if taken:
        return number

    # Outside any transaction.  The code is never persisted in clear text.
    try:
        client.send_template(
            number,
            _otp_template_name(),
            settings.WHATSAPP_DEFAULT_LANGUAGE,
            [code],
            url_button_param=code,
        )
    except client.WhatsAppError as exc:
        verification.delete()
        logger.warning("WhatsApp OTP send failed", extra={"code": exc.code})
        raise ConsentError(
            "We could not send a code to that number. Check it and try again.",
            status=502,
        ) from None
    audit(user, "link_requested", subject=user, number=client.mask_phone(number))
    return number


def _otp_template_name() -> str:
    from apps.notifications.models import NotificationTemplate

    row = NotificationTemplate.objects.filter(
        internal_name="whatsapp_verification_code", active=True
    ).first()
    return row.provider_template_name if row else SPECS["whatsapp_verification_code"].name


def confirm_code(user, code: str) -> NotificationPreference:
    verification = (
        user.whatsapp_verifications.filter(consumed_at__isnull=True)
        .order_by("-created_at")
        .first()
    )
    if verification is None or verification.expires_at < timezone.now():
        raise ConsentError("That code has expired. Request a new one.")
    # Count the attempt first so parallel guesses cannot exceed the limit.
    claimed = WhatsAppVerification.objects.filter(
        pk=verification.pk, attempts__lt=MAX_ATTEMPTS
    ).update(attempts=F("attempts") + 1)
    if not claimed:
        raise ConsentError("Too many attempts. Request a new code.", status=429)

    expected = _hash_code(user.pk, verification.number, (code or "").strip())
    if not hmac.compare_digest(expected, verification.code_hash):
        raise ConsentError("That code is not correct.")

    now = timezone.now()
    try:
        with transaction.atomic():
            prefs = get_preferences(user)
            prefs.whatsapp_number = verification.number
            prefs.whatsapp_verified_at = now
            prefs.whatsapp_enabled = True
            prefs.consent_status = ConsentStatus.OPTED_IN
            prefs.consent_at = now
            prefs.consent_source = "web_otp"
            prefs.opted_out_at = None
            prefs.save()
            WhatsAppVerification.objects.filter(pk=verification.pk).update(consumed_at=now)
    except IntegrityError:
        raise ConsentError("That number is already linked to another account.") from None
    audit(user, "link_verified", subject=user, number=client.mask_phone(prefs.whatsapp_number))
    return prefs


def opt_out(user, *, source: str) -> NotificationPreference:
    """Stop all WhatsApp messaging to this user and cancel anything queued."""
    prefs = get_preferences(user)
    prefs.whatsapp_enabled = False
    prefs.consent_status = ConsentStatus.OPTED_OUT
    prefs.opted_out_at = timezone.now()
    prefs.consent_source = source[:40]
    prefs.save(
        update_fields=[
            "whatsapp_enabled",
            "consent_status",
            "opted_out_at",
            "consent_source",
            "updated_at",
        ]
    )
    Notification.objects.filter(
        user=user,
        channel=NotificationChannel.WHATSAPP,
        status__in=[NotificationStatus.PENDING, NotificationStatus.SCHEDULED],
    ).update(status=NotificationStatus.CANCELLED)
    audit(user, "opt_out", subject=user, source=source)
    return prefs


def update_preferences(user, data: dict) -> NotificationPreference:
    """Apply validated toggle changes.  Enabling requires a verified number."""
    prefs = get_preferences(user)
    changed = {}
    for field in PREFERENCE_FIELDS + ["study_reminders_paused_until"]:
        if field in data and getattr(prefs, field) != data[field]:
            setattr(prefs, field, data[field])
            changed[field] = str(data[field])
    if "whatsapp_enabled" in data and data["whatsapp_enabled"] != prefs.whatsapp_enabled:
        if data["whatsapp_enabled"]:
            if not prefs.is_verified:
                raise ConsentError("Verify your WhatsApp number first.")
            if prefs.consent_status == ConsentStatus.OPTED_OUT:
                # Re-opting-in after STOP is a fresh consent: go through linking.
                raise ConsentError("You opted out. Link your number again to resume.")
            prefs.whatsapp_enabled = True
        else:
            # A pause, not a withdrawal of consent: resuming needs no new code.
            # (The explicit opt-out endpoint and STOP withdraw consent.)
            prefs.whatsapp_enabled = False
        changed["whatsapp_enabled"] = str(data["whatsapp_enabled"])
    prefs.save()
    if changed:
        audit(user, "preferences_changed", subject=user, **changed)
    return prefs
