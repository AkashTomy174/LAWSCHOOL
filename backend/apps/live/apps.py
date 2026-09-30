"""Live classes app -- scheduled Zoom/Google Meet sessions per course."""

from django.apps import AppConfig


class LiveConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.live"
    verbose_name = "Live Classes"
