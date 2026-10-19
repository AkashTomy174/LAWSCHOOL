"""Notification routes, mounted at ``/api/v1/notifications/``."""

from django.urls import path

from apps.notifications import views, views_whatsapp as wa

app_name = "notifications"

urlpatterns = [
    path("", views.NotificationListView.as_view(), name="list"),
    path("unread-count/", views.UnreadCountView.as_view(), name="unread-count"),
    path("read/", views.MarkReadView.as_view(), name="mark-read"),
    # ---- WhatsApp: student ------------------------------------------------ #
    path("whatsapp/preferences/", wa.PreferencesView.as_view(), name="wa-preferences"),
    path("whatsapp/link/", wa.LinkView.as_view(), name="wa-link"),
    path("whatsapp/verify/", wa.VerifyView.as_view(), name="wa-verify"),
    path("whatsapp/opt-out/", wa.OptOutView.as_view(), name="wa-opt-out"),
    path("whatsapp/history/", wa.HistoryView.as_view(), name="wa-history"),
    # ---- WhatsApp: Meta webhook (signature-authenticated) ------------------ #
    path("whatsapp/webhook/", wa.WebhookView.as_view(), name="wa-webhook"),
    # ---- WhatsApp: admin -------------------------------------------------- #
    path("admin/overview/", wa.AdminOverviewView.as_view(), name="wa-admin-overview"),
    path("admin/history/", wa.AdminHistoryView.as_view(), name="wa-admin-history"),
    path("admin/failed/", wa.AdminFailedView.as_view(), name="wa-admin-failed"),
    path("admin/<uuid:pk>/retry/", wa.AdminRetryView.as_view(), name="wa-admin-retry"),
    path("admin/templates/", wa.AdminTemplatesView.as_view(), name="wa-admin-templates"),
    path(
        "admin/templates/<int:pk>/",
        wa.AdminTemplateDetailView.as_view(),
        name="wa-admin-template",
    ),
    path("admin/settings/", wa.AdminSettingsView.as_view(), name="wa-admin-settings"),
    path(
        "admin/announcements/preview/",
        wa.AdminAnnouncementPreviewView.as_view(),
        name="wa-admin-announce-preview",
    ),
    path(
        "admin/announcements/",
        wa.AdminAnnouncementView.as_view(),
        name="wa-admin-announce",
    ),
]
