"""Quiz hierarchy::

    Subject ──< Question (M2M) ──< Option
    Quiz ──< QuizSectionRule >── Subject
      │
      └──< QuizAttempt ──< AttemptQuestion >── Question
                        ──< QuizAnswer >── Question/Option

Scoring rules that shape the schema
-----------------------------------
* ``Option.is_correct`` is *never* serialized to students.  The correct answer
  only ever exists server-side; the public serializer exposes option text and id
  solely for rendering.
* Questions live in a shared bank tagged by ``Subject``, reusable across many
  quizzes.  Each ``Quiz`` declares, per ``Subject``, how many questions to draw
  and how many marks each is worth (``QuizSectionRule``).  The concrete set of
  questions served to a student is sampled once per attempt and frozen onto
  ``AttemptQuestion`` -- editing a rule or the bank later never changes a
  graded attempt's score.
* ``QuizAttempt`` stores the computed score, so the leaderboard can aggregate a
  single table instead of re-scoring every attempt on every page load.
* One attempt row per (quiz, user, attempt_number) -- enforced in the database.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from apps.core.constants import CourseStatus


class Subject(models.Model):
    """An independent, reusable exam category (Maths, Physics, ...).

    Not tied to any Course/Section -- the same subject, and the same
    ``Question``, can be reused across unrelated exams.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)
    description = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)
        verbose_name = _("subject")
        verbose_name_plural = _("subjects")

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:140]
        super().save(*args, **kwargs)


class Quiz(models.Model):
    """An assessment attached (optionally) to a lesson, or course-wide."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(
        "courses.Course", on_delete=models.CASCADE, related_name="quizzes"
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    pass_percentage = models.PositiveIntegerField(
        default=60,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="Minimum percentage required to pass.",
    )
    max_attempts = models.PositiveIntegerField(
        default=0, help_text="0 means unlimited attempts."
    )
    time_limit_minutes = models.PositiveIntegerField(
        default=0, help_text="0 means untimed."
    )
    # Randomising option order per attempt discourages answer sharing.
    shuffle_questions = models.BooleanField(default=False)

    is_published = models.BooleanField(default=False, db_index=True)
    available_from = models.DateTimeField(null=True, blank=True)
    available_until = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = _("quiz")
        verbose_name_plural = _("quizzes")
        indexes = [
            models.Index(
                fields=["course", "is_published"], name="quiz_course_published_idx"
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(pass_percentage__gte=1) & Q(pass_percentage__lte=100),
                name="quiz_pass_percentage_range",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.course.title} -- {self.title}"

    @property
    def total_marks(self) -> int:
        """Configured total: sum of (question_count * marks_per_question) across rules."""
        total = 0
        for rule in self.section_rules.all():
            total += rule.question_count * rule.marks_per_question
        return total

    @property
    def question_count(self) -> int:
        """Configured number of questions a fresh attempt will sample."""
        total = 0
        for rule in self.section_rules.all():
            total += rule.question_count
        return total

    def is_available_now(self) -> bool:
        if not self.is_published:
            return False
        now = timezone.now()
        if self.available_from and self.available_from > now:
            return False
        if self.available_until and self.available_until < now:
            return False
        return True


class QuizSectionRule(models.Model):
    """How many questions (and marks each) a quiz draws from one subject."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="section_rules")
    subject = models.ForeignKey(
        Subject, on_delete=models.PROTECT, related_name="quiz_rules"
    )
    question_count = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    marks_per_question = models.PositiveIntegerField(
        default=1, validators=[MinValueValidator(1)]
    )
    ordering = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ("ordering", "id")
        verbose_name = _("quiz section rule")
        verbose_name_plural = _("quiz section rules")
        constraints = [
            models.UniqueConstraint(
                fields=["quiz", "subject"], name="unique_rule_per_quiz_subject"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.quiz.title} -- {self.subject.name} x{self.question_count}"


class Question(models.Model):
    """A single multiple-choice question living in the shared question bank."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subjects = models.ManyToManyField(Subject, related_name="questions", blank=True)
    text = models.TextField()
    explanation = models.TextField(
        blank=True, help_text="Shown after submission to support learning."
    )
    marks = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        help_text="Baseline/suggested marks; a quiz's rule sets the marks actually awarded.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive questions are never sampled into a new attempt.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = _("question")
        verbose_name_plural = _("questions")
        permissions = [
            ("manage_question_bank", "Can create/edit shared question bank"),
        ]

    def __str__(self) -> str:
        return self.text[:80]

    @property
    def correct_options(self):
        return self.options.filter(is_correct=True)


class Option(models.Model):
    """An answer choice.  ``is_correct`` is server-side only."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="options"
    )
    text = models.CharField(max_length=500)
    is_correct = models.BooleanField(default=False)
    ordering = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ("ordering", "id")
        verbose_name = _("option")
        verbose_name_plural = _("options")
        indexes = [
            models.Index(
                fields=["question", "ordering"], name="option_question_order_idx"
            ),
            models.Index(fields=["question", "is_correct"], name="option_correct_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["question", "ordering"],
                name="unique_option_ordering_per_question",
            ),
            # An option cannot be its own question's only correctness marker by
            # accident: exactly one correct option is required per question, which
            # this constraint can only *partially* express (DBs cannot count rows
            # in a CHECK), so the service layer validates the count on save while
            # the index keeps lookups fast.
        ]

    def __str__(self) -> str:
        return self.text[:60]


class QuizAttempt(models.Model):
    """One student attempt.  The score here is authoritative."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="attempts")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="quiz_attempts"
    )
    attempt_number = models.PositiveIntegerField(default=1)

    started_at = models.DateTimeField(default=timezone.now)
    submitted_at = models.DateTimeField(null=True, blank=True)

    score = models.PositiveIntegerField(default=0, db_index=True)
    max_score = models.PositiveIntegerField(default=0)
    percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    passed = models.BooleanField(default=False, db_index=True)

    # Anti-cheat: if the client claims a longer duration than the server measured,
    # the server value wins.  Kept for support/forensics.
    duration_seconds = models.PositiveIntegerField(default=0)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ("-started_at",)
        verbose_name = _("quiz attempt")
        verbose_name_plural = _("quiz attempts")
        indexes = [
            models.Index(
                fields=["user", "quiz", "-started_at"], name="attempt_user_quiz_idx"
            ),
            # Powers the leaderboard's per-student score aggregation.
            models.Index(
                fields=["user", "passed", "score"], name="attempt_user_score_idx"
            ),
            models.Index(fields=["quiz", "-score"], name="attempt_quiz_score_idx"),
        ]
        constraints = [
            # Attempt numbers are unique per student per quiz, so a retry can never
            # silently overwrite or duplicate a result.
            models.UniqueConstraint(
                fields=["quiz", "user", "attempt_number"],
                name="unique_attempt_number_per_user_quiz",
            ),
            models.CheckConstraint(
                condition=Q(percentage__gte=0) & Q(percentage__lte=100),
                name="attempt_percentage_range",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} -- {self.quiz_id} #{self.attempt_number} ({self.score}/{self.max_score})"


class AttemptQuestion(models.Model):
    """One question sampled into one attempt.  Frozen at sample time.

    Rewriting a ``QuizSectionRule``'s marks, or editing the bank ``Question``,
    must never retroactively change an already-graded attempt -- so the marks
    awarded for this slot are copied here, not looked up live.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attempt = models.ForeignKey(
        QuizAttempt, on_delete=models.CASCADE, related_name="attempt_questions"
    )
    question = models.ForeignKey(
        Question, on_delete=models.PROTECT, related_name="attempt_uses"
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.PROTECT, related_name="attempt_questions"
    )
    ordering = models.PositiveIntegerField(default=1)
    marks = models.PositiveIntegerField(validators=[MinValueValidator(1)])

    class Meta:
        ordering = ("ordering",)
        verbose_name = _("attempt question")
        verbose_name_plural = _("attempt questions")
        constraints = [
            models.UniqueConstraint(
                fields=["attempt", "question"], name="unique_question_per_attempt"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.attempt_id} -- {self.question_id}"


class QuizAnswer(models.Model):
    """A student's response to one question, with the grading outcome."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attempt = models.ForeignKey(
        QuizAttempt, on_delete=models.CASCADE, related_name="answers"
    )
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="answers"
    )
    # Nullable so an unanswered question is still recorded (important for review).
    selected_option = models.ForeignKey(
        Option, on_delete=models.SET_NULL, null=True, blank=True, related_name="answers"
    )

    is_correct = models.BooleanField(default=False)
    marks_awarded = models.PositiveIntegerField(default=0)

    answered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("answered_at",)
        verbose_name = _("quiz answer")
        verbose_name_plural = _("quiz answers")
        constraints = [
            # One answer row per question per attempt.
            models.UniqueConstraint(
                fields=["attempt", "question"],
                name="unique_answer_per_attempt_question",
            ),
        ]
        indexes = [
            models.Index(
                fields=["attempt", "is_correct"], name="answer_attempt_correct_idx"
            ),
            models.Index(fields=["question"], name="answer_question_idx"),
        ]

    def __str__(self) -> str:
        return (
            f"{self.attempt_id} -> {self.question_id}: {'ok' if self.is_correct else 'x'}"
        )
