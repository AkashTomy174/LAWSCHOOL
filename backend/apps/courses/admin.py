"""Course admin with inline sections/lessons and useful filters."""

from django.contrib import admin
from django.utils.html import format_html

from apps.courses.models import Course, Lesson, Section


class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 0
    fields = (
        "ordering",
        "title",
        "video",
        "quiz",
        "duration_seconds",
        "is_preview",
        "status",
    )
    ordering = ("ordering",)
    # Avoids a query per row for the related video/quiz dropdowns.
    autocomplete_fields = ()
    show_change_link = True


class SectionInline(admin.TabularInline):
    model = Section
    extra = 0
    fields = ("ordering", "title", "is_published")
    ordering = ("ordering",)
    show_change_link = True


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "instructor",
        "status",
        "unlock_rule",
        "price",
        "lesson_count",
        "published_at",
    )
    list_filter = ("status", "unlock_rule", "language", "level")
    search_fields = (
        "title",
        "slug",
        "summary",
        "instructor__email",
        "instructor__name",
    )
    prepopulated_fields = {"slug": ("title",)}
    date_hierarchy = "created_at"
    list_select_related = ("instructor",)
    inlines = [SectionInline]
    actions = ["publish_courses", "archive_courses"]
    readonly_fields = ("lesson_count", "duration_minutes", "created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("title", "slug", "subtitle", "summary", "description")}),
        ("Media", {"fields": ("thumbnail",)}),
        (
            "Delivery",
            {"fields": ("instructor", "price", "unlock_rule", "language", "level")},
        ),
        (
            "State",
            {"fields": ("status", "published_at", "lesson_count", "duration_minutes")},
        ),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    @admin.action(description="Publish selected courses")
    def publish_courses(self, request, queryset):
        for course in queryset:
            course.publish()

    @admin.action(description="Archive selected courses")
    def archive_courses(self, request, queryset):
        queryset.update(status="archived")

    def view_on_site(self, obj):  # pragma: no cover - convenience
        return f"/courses/{obj.slug}"


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ("title", "course", "ordering", "is_published", "lesson_count")
    list_filter = ("is_published", "course")
    search_fields = ("title", "course__title")
    list_select_related = ("course",)
    ordering = ("course", "ordering")
    inlines = [LessonInline]

    @admin.display(description="Lessons")
    def lesson_count(self, obj):
        return obj.lessons.count()


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "section",
        "ordering",
        "status",
        "is_preview",
        "video",
        "has_quiz",
    )
    list_filter = ("status", "is_preview", "section__course")
    search_fields = ("title", "section__title", "section__course__title")
    list_select_related = ("section", "section__course", "video")
    ordering = ("section", "ordering")
    autocomplete_fields = ()
    readonly_fields = ("created_at", "updated_at")

    @admin.display(boolean=True, description="Quiz")
    def has_quiz(self, obj):
        return obj.quiz_id is not None

    def video_status(self, obj):  # pragma: no cover - column helper
        if not obj.video:
            return format_html('<span style="color:#999">--</span>')
        colour = {"ready": "green", "failed": "red"}.get(obj.video.status, "orange")
        return format_html(
            '<b style="color:{}">{}</b>', colour, obj.video.get_status_display()
        )
