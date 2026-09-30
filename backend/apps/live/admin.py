from django.contrib import admin

from apps.live.models import LiveClass


@admin.register(LiveClass)
class LiveClassAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "course",
        "scheduled_start",
        "meeting_provider",
        "is_published",
    )
    list_filter = ("meeting_provider", "is_published", "course")
    search_fields = ("title", "course__title")
    list_select_related = ("course", "instructor")
