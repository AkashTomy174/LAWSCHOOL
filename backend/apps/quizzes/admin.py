"""Quiz admin with nested questions/options inlines."""

from django.contrib import admin

from apps.quizzes.models import (
    AttemptQuestion,
    Option,
    Question,
    Quiz,
    QuizAnswer,
    QuizAttempt,
    QuizSectionRule,
    Subject,
)


class OptionInline(admin.TabularInline):
    model = Option
    extra = 2
    fields = ("ordering", "text", "is_correct")
    ordering = ("ordering",)


class QuizSectionRuleInline(admin.TabularInline):
    model = QuizSectionRule
    extra = 0
    fields = ("ordering", "subject", "question_count", "marks_per_question")
    ordering = ("ordering",)


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "course",
        "is_published",
        "question_count_display",
        "total_marks_display",
        "pass_percentage",
        "max_attempts",
    )
    list_filter = ("is_published", "course")
    search_fields = ("title", "course__title")
    list_select_related = ("course",)
    inlines = [QuizSectionRuleInline]
    readonly_fields = ("created_at", "updated_at")

    @admin.display(description="Questions")
    def question_count_display(self, obj):
        return obj.question_count

    @admin.display(description="Total marks")
    def total_marks_display(self, obj):
        return obj.total_marks


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    """Shared question bank -- questions are tagged by subject, not owned by one quiz."""

    list_display = ("text_short", "subjects_display", "marks", "is_active")
    list_filter = ("subjects", "is_active")
    search_fields = ("text",)
    filter_horizontal = ("subjects",)
    inlines = [OptionInline]
    ordering = ("-created_at",)

    @admin.display(description="Question")
    def text_short(self, obj):
        return obj.text[:70]

    @admin.display(description="Subjects")
    def subjects_display(self, obj):
        return ", ".join(obj.subjects.values_list("name", flat=True))


@admin.register(Option)
class OptionAdmin(admin.ModelAdmin):
    list_display = ("text_short", "question", "is_correct", "ordering")
    list_filter = ("is_correct",)
    search_fields = ("text", "question__text")
    list_select_related = ("question",)

    @admin.display(description="Option")
    def text_short(self, obj):
        return obj.text[:70]


class QuizAnswerInline(admin.TabularInline):
    model = QuizAnswer
    extra = 0
    can_delete = False
    readonly_fields = ("question", "selected_option", "is_correct", "marks_awarded")


class AttemptQuestionInline(admin.TabularInline):
    """Read-only view of exactly which bank questions this attempt sampled."""

    model = AttemptQuestion
    extra = 0
    can_delete = False
    readonly_fields = ("question", "subject", "marks", "ordering")
    fields = readonly_fields


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "quiz",
        "attempt_number",
        "score",
        "max_score",
        "percentage",
        "passed",
        "submitted_at",
    )
    list_filter = ("passed", "quiz__course", "submitted_at")
    search_fields = ("user__email", "user__name", "quiz__title")
    list_select_related = ("user", "quiz")
    date_hierarchy = "started_at"
    inlines = [AttemptQuestionInline, QuizAnswerInline]
    readonly_fields = (
        "started_at",
        "submitted_at",
        "score",
        "max_score",
        "percentage",
        "passed",
    )

    def has_add_permission(self, request):
        # Attempts are produced by students, never created by hand.
        return False


@admin.register(QuizAnswer)
class QuizAnswerAdmin(admin.ModelAdmin):
    list_display = ("attempt", "question", "is_correct", "marks_awarded")
    list_filter = ("is_correct",)
    search_fields = ("attempt__user__email", "question__text")
    list_select_related = ("attempt", "question", "selected_option")

    def has_add_permission(self, request):
        return False
