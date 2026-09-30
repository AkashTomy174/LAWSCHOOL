"""Quiz serializers.

The critical property: **``OptionSerializer`` never exposes ``is_correct``.**
Correct answers are only revealed by ``AttemptResultSerializer`` after grading,
where leaking them can no longer affect a score.
"""

from __future__ import annotations

from rest_framework import serializers

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


class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ("id", "name", "slug", "description")
        read_only_fields = ("id", "slug")


class OptionSerializer(serializers.ModelSerializer):
    """Student-facing option.  ``is_correct`` is deliberately absent."""

    class Meta:
        model = Option
        fields = ("id", "text", "ordering")


class OptionAdminSerializer(serializers.ModelSerializer):
    """Instructor/admin option shape, including correctness."""

    class Meta:
        model = Option
        fields = ("id", "text", "is_correct", "ordering")


class QuestionBankSerializer(serializers.ModelSerializer):
    """Shared question-bank authoring shape -- read/write, subject-tagged."""

    options = OptionAdminSerializer(many=True, read_only=True)
    subjects = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Subject.objects.all(), required=False
    )

    class Meta:
        model = Question
        fields = (
            "id",
            "text",
            "explanation",
            "marks",
            "subjects",
            "is_active",
            "options",
        )


class QuizSectionRuleSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source="subject.name", read_only=True)

    class Meta:
        model = QuizSectionRule
        fields = (
            "id",
            "quiz",
            "subject",
            "subject_name",
            "question_count",
            "marks_per_question",
            "ordering",
        )
        read_only_fields = ("id",)


class AttemptQuestionSerializer(serializers.ModelSerializer):
    """One sampled question inside an attempt's payload.

    ``id`` is intentionally the underlying bank ``Question`` id (not the
    ``AttemptQuestion`` row id) -- the frontend keys its answers dict by
    question id, and this keeps that contract unchanged.
    """

    id = serializers.UUIDField(source="question_id", read_only=True)
    text = serializers.CharField(source="question.text", read_only=True)
    options = OptionSerializer(source="question.options", many=True, read_only=True)

    class Meta:
        model = AttemptQuestion
        fields = ("id", "text", "marks", "ordering", "options")


class QuizListSerializer(serializers.ModelSerializer):
    """Quiz card for course pages and lists."""

    question_count = serializers.IntegerField(read_only=True)
    total_marks = serializers.IntegerField(read_only=True)

    class Meta:
        model = Quiz
        fields = (
            "id",
            "course",
            "title",
            "description",
            "pass_percentage",
            "max_attempts",
            "time_limit_minutes",
            "question_count",
            "total_marks",
            "is_published",
        )


class QuizDetailSerializer(QuizListSerializer):
    """Quiz shape for the attempt screen.

    ``questions`` has no backing model relation any more (a quiz's concrete
    question set is sampled per attempt) -- it defaults to an empty list here
    and the view overwrites it with the attempt's sampled
    ``AttemptQuestionSerializer`` list before returning the response.
    """

    questions = serializers.SerializerMethodField()

    def get_questions(self, obj):
        return []

    class Meta(QuizListSerializer.Meta):
        fields = QuizListSerializer.Meta.fields + (
            "questions",
            "available_from",
            "available_until",
        )


class QuizWriteSerializer(serializers.ModelSerializer):
    """Instructor/admin quiz authoring."""

    class Meta:
        model = Quiz
        fields = (
            "id",
            "course",
            "title",
            "description",
            "pass_percentage",
            "max_attempts",
            "time_limit_minutes",
            "shuffle_questions",
            "is_published",
            "available_from",
            "available_until",
        )
        read_only_fields = ("id",)

    def validate_pass_percentage(self, value: int) -> int:
        if not 1 <= value <= 100:
            raise serializers.ValidationError(
                "Pass percentage must be between 1 and 100."
            )
        return value

    def validate(self, attrs: dict) -> dict:
        start = attrs.get(
            "available_from", getattr(self.instance, "available_from", None)
        )
        end = attrs.get(
            "available_until", getattr(self.instance, "available_until", None)
        )
        if start and end and end <= start:
            raise serializers.ValidationError(
                {"available_until": "The closing time must be after the opening time."}
            )
        return attrs


class OptionWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Option
        fields = ("id", "question", "text", "is_correct", "ordering")
        read_only_fields = ("id",)

    def validate(self, attrs: dict) -> dict:
        question = attrs.get("question") or getattr(self.instance, "question", None)
        ordering = attrs.get("ordering", getattr(self.instance, "ordering", None))
        if question and ordering:
            clash = Option.objects.filter(question=question, ordering=ordering)
            if self.instance:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise serializers.ValidationError(
                    {
                        "ordering": "Another option for this question already uses that position."
                    }
                )
        return attrs


class SubmitAttemptSerializer(serializers.Serializer):
    """Body for ``POST /api/v1/quiz-attempts/<id>/submit/``.

    ``answers`` maps ``question_id -> option_id``.  Nothing else is accepted: the
    client cannot submit a score, a percentage or a pass flag.
    """

    answers = serializers.DictField(
        child=serializers.CharField(allow_blank=True, allow_null=True),
        allow_empty=True,
    )
    duration_seconds = serializers.IntegerField(min_value=0, required=False, default=0)

    def validate_answers(self, value: dict) -> dict:
        if len(value) > 500:
            raise serializers.ValidationError("Too many answers submitted.")
        return value


class QuizAnswerSerializer(serializers.ModelSerializer):
    question_text = serializers.CharField(source="question.text", read_only=True)
    selected_option_text = serializers.CharField(
        source="selected_option.text", read_only=True, default=None
    )

    class Meta:
        model = QuizAnswer
        fields = (
            "id",
            "question",
            "question_text",
            "selected_option",
            "selected_option_text",
            "is_correct",
            "marks_awarded",
        )
        read_only_fields = fields


class QuizAttemptSerializer(serializers.ModelSerializer):
    """Result payload for a graded (or in-progress) attempt."""

    quiz_title = serializers.CharField(source="quiz.title", read_only=True)
    course_slug = serializers.CharField(source="quiz.course.slug", read_only=True)
    pass_percentage = serializers.IntegerField(
        source="quiz.pass_percentage", read_only=True
    )
    answers = QuizAnswerSerializer(many=True, read_only=True)

    class Meta:
        model = QuizAttempt
        fields = (
            "id",
            "quiz",
            "quiz_title",
            "course_slug",
            "attempt_number",
            "started_at",
            "submitted_at",
            "score",
            "max_score",
            "percentage",
            "passed",
            "pass_percentage",
            "duration_seconds",
            "answers",
        )
        read_only_fields = fields


class QuizAttemptSummarySerializer(serializers.ModelSerializer):
    """Lighter shape for history lists (no per-answer rows)."""

    quiz_title = serializers.CharField(source="quiz.title", read_only=True)
    pass_percentage = serializers.IntegerField(
        source="quiz.pass_percentage", read_only=True
    )

    class Meta:
        model = QuizAttempt
        fields = (
            "id",
            "quiz",
            "quiz_title",
            "attempt_number",
            "submitted_at",
            "score",
            "max_score",
            "percentage",
            "passed",
            "pass_percentage",
            "duration_seconds",
        )
        read_only_fields = fields


class AttemptReviewSerializer(serializers.Serializer):
    """Serializes the dict list produced by ``services.attempt_review``."""

    question_id = serializers.UUIDField()
    question_text = serializers.CharField()
    explanation = serializers.CharField(allow_blank=True)
    selected_option_id = serializers.UUIDField(allow_null=True)
    correct_option_id = serializers.UUIDField(allow_null=True)
    is_correct = serializers.BooleanField()
    marks_awarded = serializers.IntegerField()
    marks_possible = serializers.IntegerField()
