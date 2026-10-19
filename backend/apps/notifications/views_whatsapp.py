"""WhatsApp API: student settings, Meta webhook, and admin operations.

Mounted under ``/api/v1/notifications/``.  Student endpoints act only on
``request.user``; admin endpoints require ``IsAdminRole``; the webhook uses Meta's
signature instead of JWT.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db.models import Count, Q
from django.http import HttpResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import generics, serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.constants import NotificationChannel
from apps.core.pagination import StandardResultsSetPagination
from apps.core.permissions import IsAdminRole, is_schema_generation
from apps.core.throttling import IpScopedRateThrottle, ResilientScopedRateThrottle
from apps.notifications.models import (
    Category,
    Notification,
    NotificationPreference,
    NotificationSettings,
    NotificationStatus,
    NotificationTemplate,
)
from apps.notifications.whatsapp import client, consent, events, webhook
from apps.notifications.whatsapp.service import audit

WA = NotificationChannel.WHATSAPP


def _error(message: str, http_status: int, code: str = "invalid") -> Response:
    return Response(
        {"error": {"code": code, "message": message, "details": None}}, status=http_status
    )


# --------------------------------------------------------------------------- #
# Student: preferences / linking
# --------------------------------------------------------------------------- #
class PreferenceSerializer(serializers.ModelSerializer):
    whatsapp_number_masked = serializers.SerializerMethodField()
    is_verified = serializers.BooleanField(read_only=True)
    whatsapp_available = serializers.SerializerMethodField()

    class Meta:
        model = NotificationPreference
        fields = (
            "whatsapp_number_masked",
            "is_verified",
            "whatsapp_enabled",
            "consent_status",
            "consent_at",
            "opted_out_at",
            "whatsapp_available",
            "study_reminders_paused_until",
            *[f"{c.value}_enabled" for c in Category],
        )
        read_only_fields = ("consent_status", "consent_at", "opted_out_at")

    def get_whatsapp_number_masked(self, obj) -> str:
        return client.mask_phone(obj.whatsapp_number) if obj.whatsapp_number else ""

    def get_whatsapp_available(self, obj) -> bool:
        return bool(settings.WHATSAPP_ENABLED)


class PreferencesView(APIView):
    """GET/PATCH /notifications/whatsapp/preferences/ -- the caller's own settings."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        prefs = consent.get_preferences(request.user)
        return Response(PreferenceSerializer(prefs).data)

    def patch(self, request):
        prefs = consent.get_preferences(request.user)
        serializer = PreferenceSerializer(prefs, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            prefs = consent.update_preferences(request.user, serializer.validated_data)
        except consent.ConsentError as exc:
            return _error(exc.message, exc.status)
        return Response(PreferenceSerializer(prefs).data)


class LinkSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=30)
    consent = serializers.BooleanField()


class LinkView(APIView):
    """POST /notifications/whatsapp/link/ -- send a verification code to a number."""

    permission_classes = [IsAuthenticated]
    # Per-user (stock scoped throttle) AND per-IP (many accounts, one address).
    throttle_classes = [ResilientScopedRateThrottle, IpScopedRateThrottle]
    throttle_scope = "whatsapp_link"
    throttle_scope_ip = "whatsapp_link_ip"

    def post(self, request):
        serializer = LinkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            number = consent.request_link(
                request.user,
                serializer.validated_data["phone"],
                consent=serializer.validated_data["consent"],
            )
        except consent.ConsentError as exc:
            return _error(exc.message, exc.status)
        return Response(
            {
                "detail": "If this number can receive WhatsApp messages, a code is on its way.",
                "whatsapp_number_masked": client.mask_phone(number),
                "expires_in_seconds": int(consent.CODE_TTL.total_seconds()),
            },
            status=status.HTTP_202_ACCEPTED,
        )


class VerifySerializer(serializers.Serializer):
    code = serializers.RegexField(r"^\d{6}$", max_length=6)


class VerifyView(APIView):
    """POST /notifications/whatsapp/verify/ -- confirm the one-time code."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ResilientScopedRateThrottle]
    throttle_scope = "whatsapp_verify"

    def post(self, request):
        serializer = VerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            prefs = consent.confirm_code(request.user, serializer.validated_data["code"])
        except consent.ConsentError as exc:
            return _error(exc.message, exc.status)
        return Response(PreferenceSerializer(prefs).data)


class OptOutView(APIView):
    """POST /notifications/whatsapp/opt-out/ -- withdraw consent entirely."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        prefs = consent.opt_out(request.user, source="web_opt_out")
        return Response(PreferenceSerializer(prefs).data)


class HistorySerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Notification
        fields = ("id", "template_name", "status", "status_label", "created_at", "delivered_at")
        read_only_fields = fields


class HistoryView(generics.ListAPIView):
    """GET /notifications/whatsapp/history/ -- the caller's own WhatsApp messages."""

    serializer_class = HistorySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        if is_schema_generation(self):
            return Notification.objects.none()
        return Notification.objects.filter(user=self.request.user, channel=WA).order_by(
            "-created_at"
        )


# --------------------------------------------------------------------------- #
# Meta webhook
# --------------------------------------------------------------------------- #
@method_decorator(csrf_exempt, name="dispatch")
class WebhookView(APIView):
    """GET = Meta's subscription handshake, POST = signed event delivery."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ResilientScopedRateThrottle]
    throttle_scope = "webhook_whatsapp"

    def get(self, request):
        challenge = webhook.verify_handshake(
            request.query_params.get("hub.mode", ""),
            request.query_params.get("hub.verify_token", ""),
            request.query_params.get("hub.challenge", ""),
        )
        if challenge is None:
            return HttpResponse(status=403)
        return HttpResponse(challenge, content_type="text/plain")

    def post(self, request):
        try:
            declared = int(request.META.get("CONTENT_LENGTH") or 0)
        except ValueError:
            declared = 0
        if declared > settings.WHATSAPP_WEBHOOK_MAX_BYTES:
            return HttpResponse(status=413)
        raw = request.body  # exact bytes; never re-serialised
        if len(raw) > settings.WHATSAPP_WEBHOOK_MAX_BYTES:
            return HttpResponse(status=413)
        if not webhook.signature_valid(raw, request.headers.get("X-Hub-Signature-256", "")):
            return HttpResponse(status=403)
        try:
            payload = webhook.parse(raw)
        except webhook.PayloadError:
            return HttpResponse(status=400)
        if not settings.WHATSAPP_ENABLED:
            return Response({"status": "disabled"})
        return Response({"status": "ok", **webhook.ingest(payload)})


# --------------------------------------------------------------------------- #
# Admin
# --------------------------------------------------------------------------- #
class AdminBase(APIView):
    permission_classes = [IsAdminRole]
    throttle_classes = [ResilientScopedRateThrottle]
    throttle_scope = "whatsapp_admin"


class AdminHistorySerializer(serializers.ModelSerializer):
    recipient = serializers.CharField(source="user.name", read_only=True)
    recipient_number = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Notification
        fields = (
            "id",
            "recipient",
            "recipient_number",
            "template_name",
            "status",
            "status_label",
            "attempts",
            "last_error_code",
            "related_object_type",
            "created_at",
            "accepted_at",
            "delivered_at",
        )
        read_only_fields = fields

    def get_recipient_number(self, obj) -> str:
        prefs = getattr(obj.user, "notification_preference", None)
        return client.mask_phone(prefs.whatsapp_number) if prefs and prefs.whatsapp_number else ""


def _admin_queryset(params):
    qs = Notification.objects.filter(channel=WA).select_related(
        "user", "user__notification_preference"
    )
    if params.get("status"):
        qs = qs.filter(status=params["status"])
    if params.get("kind"):
        qs = qs.filter(kind=params["kind"])
    if params.get("date_from"):
        qs = qs.filter(created_at__date__gte=params["date_from"])
    if params.get("date_to"):
        qs = qs.filter(created_at__date__lte=params["date_to"])
    if params.get("recipient"):
        needle = params["recipient"]
        qs = qs.filter(Q(user__email__icontains=needle) | Q(user__name__icontains=needle))
    if params.get("course"):
        from apps.live.models import LiveClass

        class_ids = [
            str(pk)
            for pk in LiveClass.objects.filter(course__slug=params["course"]).values_list(
                "pk", flat=True
            )
        ]
        qs = qs.filter(related_object_type="live_class", related_object_id__in=class_ids)
    return qs.order_by("-created_at")


class AdminHistoryView(generics.ListAPIView):
    """GET /notifications/admin/history/ -- filterable, paginated delivery log."""

    serializer_class = AdminHistorySerializer
    permission_classes = [IsAdminRole]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        if is_schema_generation(self):
            return Notification.objects.none()
        return _admin_queryset(self.request.query_params)


class AdminFailedView(AdminHistoryView):
    """GET /notifications/admin/failed/ -- failures only."""

    def get_queryset(self):
        if is_schema_generation(self):
            return Notification.objects.none()
        return _admin_queryset(self.request.query_params).filter(
            status=NotificationStatus.FAILED
        )


class AdminRetryView(AdminBase):
    """POST /notifications/admin/<uuid>/retry/ -- re-queue one failed message."""

    def post(self, request, pk):
        notification = Notification.objects.filter(pk=pk, channel=WA).first()
        if notification is None:
            return _error("Notification not found.", 404, "not_found")
        from apps.notifications.whatsapp.service import retry_failed

        if not retry_failed(notification, request.user):
            return _error("Only failed notifications can be retried.", 409, "not_failed")
        return Response({"detail": "Queued for retry."})


class AdminOverviewView(AdminBase):
    """GET /notifications/admin/overview/?days=30 -- volume and delivery funnel."""

    def get(self, request):
        try:
            days = max(1, min(int(request.query_params.get("days", 30)), 365))
        except ValueError:
            days = 30
        since = timezone.now() - timedelta(days=days)
        qs = Notification.objects.filter(channel=WA, created_at__gte=since)
        by_status = {row["status"]: row["n"] for row in qs.values("status").annotate(n=Count("id"))}
        by_template = list(
            qs.values("template_name").annotate(n=Count("id")).order_by("-n")[:20]
        )
        submitted = sum(
            by_status.get(s, 0)
            for s in (
                NotificationStatus.ACCEPTED,
                NotificationStatus.SENT,
                NotificationStatus.DELIVERED,
                NotificationStatus.READ,
            )
        )
        cost = None
        try:
            unit = Decimal(settings.WHATSAPP_ESTIMATED_COST_PER_MESSAGE)
            cost = str((unit * submitted).quantize(Decimal("0.01")))
        except (InvalidOperation, TypeError):
            pass
        return Response(
            {
                "enabled": settings.WHATSAPP_ENABLED,
                "days": days,
                "by_status": by_status,
                "by_template": by_template,
                "accepted_or_later": submitted,
                "note": "'Accepted' means WhatsApp took the message; only 'Delivered' "
                "and 'Read' come from delivery receipts.",
                "estimated_cost": cost,
                "estimated_cost_note": "Planning estimate from WHATSAPP_ESTIMATED_COST_PER_MESSAGE; "
                "actual charges come from Meta billing."
                if cost is not None
                else "Cost estimate not configured.",
            }
        )


class TemplateSerializer(serializers.ModelSerializer):
    has_trigger = serializers.SerializerMethodField()

    def get_has_trigger(self, obj) -> bool:
        from apps.notifications.whatsapp.templates import SPECS

        spec = SPECS.get(obj.internal_name)
        return bool(spec and spec.has_trigger)

    class Meta:
        model = NotificationTemplate
        fields = (
            "id",
            "internal_name",
            "provider_template_name",
            "language_code",
            "meta_category",
            "notification_category",
            "variable_schema",
            "body_preview",
            "active",
            "approval_status",
            "has_trigger",
        )
        read_only_fields = (
            "id",
            "has_trigger",
            "internal_name",
            "meta_category",
            "notification_category",
            "variable_schema",
            "body_preview",
        )


class AdminTemplatesView(AdminBase):
    """GET /notifications/admin/templates/ -- registry + recorded approval state."""

    def get(self, request):
        from apps.notifications.whatsapp.templates import seed_templates

        seed_templates()
        rows = NotificationTemplate.objects.order_by("internal_name")
        return Response(TemplateSerializer(rows, many=True).data)


class AdminTemplateDetailView(AdminBase):
    """PATCH /notifications/admin/templates/<id>/ -- record Meta's approval state."""

    def patch(self, request, pk):
        row = NotificationTemplate.objects.filter(pk=pk).first()
        if row is None:
            return _error("Template not found.", 404, "not_found")
        serializer = TemplateSerializer(row, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        audit(request.user, "template_updated", template=row.internal_name, **{
            k: str(v) for k, v in serializer.validated_data.items()
        })
        return Response(serializer.data)


class SettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationSettings
        fields = (
            "reminder_offsets_minutes",
            "schedule_notifications_enabled",
            "weekly_summary_enabled",
            "inactivity_reminders_enabled",
            "inactivity_days",
            "inactivity_max_reminders",
            "disabled_templates",
            "send_rate_per_minute",
        )

    def validate_reminder_offsets_minutes(self, value):
        if (
            not isinstance(value, list)
            or len(value) > 6
            or any(not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= 10080 for v in value)
        ):
            raise serializers.ValidationError(
                "Provide up to 6 whole minute values between 0 and 10080."
            )
        return sorted(set(value), reverse=True)

    def validate_inactivity_days(self, value):
        if not 2 <= value <= 90:
            raise serializers.ValidationError("Choose between 2 and 90 days.")
        return value

    def validate_inactivity_max_reminders(self, value):
        if not 1 <= value <= 5:
            raise serializers.ValidationError("Choose between 1 and 5 reminders.")
        return value

    def validate_send_rate_per_minute(self, value):
        if not 1 <= value <= 5000:
            raise serializers.ValidationError("Choose between 1 and 5000 per minute.")
        return value

    def validate_disabled_templates(self, value):
        from apps.notifications.whatsapp.templates import SPECS

        if not isinstance(value, list) or any(v not in SPECS for v in value):
            raise serializers.ValidationError("Unknown template name.")
        return value


class AdminSettingsView(AdminBase):
    """GET/PATCH /notifications/admin/settings/ -- operational knobs."""

    def get(self, request):
        return Response(SettingsSerializer(NotificationSettings.load()).data)

    def patch(self, request):
        current = NotificationSettings.load()
        serializer = SettingsSerializer(current, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        audit(request.user, "settings_changed", **{
            k: str(v) for k, v in serializer.validated_data.items()
        })
        return Response(serializer.data)


class AnnouncementSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=60)
    text = serializers.CharField(max_length=300)
    course = serializers.SlugField(required=False, allow_blank=True)
    confirm_recipient_count = serializers.IntegerField(min_value=0, required=False)


def _audience(slug):
    from apps.courses.models import Course

    course = Course.objects.filter(slug=slug).first() if slug else None
    return course, events.announcement_audience(course)


class AdminAnnouncementPreviewView(AdminBase):
    """GET /notifications/admin/announcements/preview/?course=<slug>"""

    def get(self, request):
        slug = request.query_params.get("course", "")
        course, audience = _audience(slug)
        if slug and course is None:
            return _error("Course not found.", 404, "not_found")
        return Response(
            {
                "recipients": audience.count(),
                "cap": settings.WHATSAPP_MAX_BROADCAST_RECIPIENTS,
            }
        )


class AdminAnnouncementView(AdminBase):
    """POST /notifications/admin/announcements/ -- consent-respecting broadcast.

    Admin only (instructors have no broadcast right).  The caller must echo the
    previewed recipient count; a mismatch or an over-cap audience is refused.
    """

    def post(self, request):
        serializer = AnnouncementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if not settings.WHATSAPP_ENABLED:
            return _error("WhatsApp is not enabled.", 503, "disabled")
        course, audience = _audience(data.get("course", ""))
        if data.get("course") and course is None:
            return _error("Course not found.", 404, "not_found")
        count = audience.count()
        if count == 0:
            return _error("No consenting recipients for this audience.", 400, "no_recipients")
        if count > settings.WHATSAPP_MAX_BROADCAST_RECIPIENTS:
            return _error(
                f"Audience of {count} exceeds the {settings.WHATSAPP_MAX_BROADCAST_RECIPIENTS} limit.",
                400,
                "too_many_recipients",
            )
        if data.get("confirm_recipient_count") != count:
            return _error(
                f"Confirm the recipient count ({count}) to send.", 409, "confirm_required"
            )
        template = NotificationTemplate.objects.filter(
            internal_name="platform_announcement", active=True
        ).first()
        if template is None or (
            template.approval_status != "approved"
            and not settings.WHATSAPP_ALLOW_UNAPPROVED_TEMPLATES
        ):
            return _error("The announcement template is not approved yet.", 409, "template_not_approved")

        batch_id = events.new_batch_id()
        audit(
            request.user,
            "announcement_sent",
            batch=batch_id,
            course=data.get("course", ""),
            recipients=count,
        )
        from apps.notifications.tasks import send_announcement

        send_announcement.delay(
            data["title"], data["text"], str(course.pk) if course else None, batch_id
        )
        return Response({"detail": "Announcement queued.", "recipients": count}, status=202)
