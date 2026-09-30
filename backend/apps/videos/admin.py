"""Video + progress admin (includes the admin-only Cloudflare id column)."""

from django.contrib import admin
from django.utils.html import format_html

from apps.videos.models import PlaybackSession, Video, VideoProgress


@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "cloudflare_video_id",
        "status",
        "duration_seconds",
        "require_signed_urls",
        "lesson_link",
        "last_synced_at",
    )
    list_filter = ("status", "require_signed_urls", "created_at")
    search_fields = ("title", "cloudflare_video_id", "playback_uid")
    readonly_fields = ("playback_uid", "created_at", "updated_at", "last_synced_at")
    actions = ["sync_metadata"]
    list_select_related = ("lesson",)

    @admin.display(description="Lesson")
    def lesson_link(self, obj):
        if not obj.lesson_id:
            return "--"
        return format_html(
            '<a href="/admin/courses/lesson/{}/change/">{}</a>',
            obj.lesson_id,
            obj.lesson.title,
        )

    @admin.action(description="Re-sync metadata from Cloudflare")
    def sync_metadata(self, request, queryset):
        from apps.videos.services import sync_video_metadata

        for video in queryset:
            sync_video_metadata(video)
        self.message_user(
            request, f"Re-synced {queryset.count()} video(s) with Cloudflare."
        )


@admin.register(VideoProgress)
class VideoProgressAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "video",
        "completion_percentage",
        "completed",
        "last_position",
        "updated_at",
    )
    list_filter = ("completed", "updated_at")
    search_fields = ("user__email", "user__name", "video__title")
    list_select_related = ("user", "video", "lesson")
    date_hierarchy = "updated_at"
    readonly_fields = ("created_at", "updated_at")

    def has_add_permission(self, request):  # progress is only ever observed
        return False


@admin.register(PlaybackSession)
class PlaybackSessionAdmin(admin.ModelAdmin):
    """Read-only audit trail: who was granted playback and when."""

    list_display = ("user", "video", "ip_address", "created_at", "expires_at")
    list_filter = ("created_at",)
    search_fields = ("user__email", "video__title", "ip_address")
    list_select_related = ("user", "video")
    date_hierarchy = "created_at"
    readonly_fields = tuple(field.name for field in PlaybackSession._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
