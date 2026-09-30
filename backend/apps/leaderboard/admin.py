"""Leaderboard admin."""

from django.contrib import admin, messages

from apps.leaderboard.models import LeaderboardEntry, LeaderboardSnapshot


@admin.register(LeaderboardEntry)
class LeaderboardEntryAdmin(admin.ModelAdmin):
    list_display = (
        "rank",
        "user",
        "total_score",
        "quiz_score",
        "quizzes_passed",
        "lessons_completed",
        "courses_completed",
        "last_activity_at",
    )
    list_filter = ("courses_completed", "updated_at")
    search_fields = ("user__email", "user__name")
    list_select_related = ("user",)
    ordering = ("rank",)
    readonly_fields = ("updated_at",)
    actions = ["recalculate_selected"]

    @admin.action(description="Recalculate selected entries")
    def recalculate_selected(self, request, queryset):
        from apps.leaderboard.models import recalculate_entry, stamp_ranks

        for entry in queryset:
            recalculate_entry(entry.user)
        stamp_ranks()
        self.message_user(
            request, f"Recalculated {queryset.count()} entry/entries.", messages.SUCCESS
        )


@admin.register(LeaderboardSnapshot)
class LeaderboardSnapshotAdmin(admin.ModelAdmin):
    list_display = ("scope", "captured_at", "entry_count")
    list_filter = ("scope", "captured_at")
    date_hierarchy = "captured_at"
    readonly_fields = ("scope", "captured_at", "entries")

    @admin.display(description="Entries")
    def entry_count(self, obj):
        return len(obj.entries or [])

    def has_add_permission(self, request):
        return False
