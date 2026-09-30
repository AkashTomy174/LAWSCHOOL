"""Course hierarchy.

::

    Course ──< Section ──< Lesson ──< (Video, Quiz)

Design notes
------------
* ``slug`` is the public identifier for courses so URLs stay readable; sections
  and lessons are addressed by UUID to avoid enumerable integers.
* ``ordering`` is a plain integer with a ``(parent, ordering)`` unique constraint
  -- cheaper and more predictable than ``django-ordered-model`` for a hierarchy
  that is edited rarely and read constantly.
* ``unlock_rule`` lives on Course so the entitlement service has a single place
  to decide "is this content gated?" -- no per-lesson special cases.
* ``price`` is ``DecimalField`` (never float) to avoid rounding errors in money.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Count, Q, Sum
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from apps.core.constants import CourseStatus, LessonStatus, UnlockRule
from apps.core.validators import validate_image_upload


class TimeStampedModel(models.Model):
    """Abstract base: ``created_at``/``updated_at`` on every domain table."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Course(TimeStampedModel):
    """A purchasable/entitled unit of learning."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200, db_index=True)
    slug = models.SlugField(max_length=220, unique=True, db_index=True)
    subtitle = models.CharField(max_length=300, blank=True)
    description = models.TextField()
    # Short summary used in list endpoints and cards (keeps payloads small).
    summary = models.CharField(max_length=500, blank=True)

    thumbnail = models.ImageField(
        upload_to="courses/thumbnails/%Y/%m/",
        blank=True,
        null=True,
        validators=[validate_image_upload],
        help_text="Card/hero image. Videos are never stored on this server.",
    )

    instructor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,  # never silently orphan a published course
        related_name="courses_taught",
        limit_choices_to={"role__in": ["instructor", "admin"]},
    )

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Display price in INR. Access is granted via subscription plans.",
    )
    status = models.CharField(
        max_length=20,
        choices=CourseStatus.choices,
        default=CourseStatus.DRAFT,
        db_index=True,
    )
    unlock_rule = models.CharField(
        max_length=20,
        choices=UnlockRule.choices,
        default=UnlockRule.SUBSCRIPTION,
        help_text="FREE courses are visible to any authenticated student.",
    )

    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    duration_minutes = models.PositiveIntegerField(
        default=0, help_text="Denormalised total; refreshed when lessons change."
    )
    lesson_count = models.PositiveIntegerField(default=0)
    language = models.CharField(max_length=50, default="English")
    level = models.CharField(max_length=50, blank=True)

    class Meta:
        ordering = ("-published_at", "-created_at")
        verbose_name = _("course")
        verbose_name_plural = _("courses")
        indexes = [
            models.Index(fields=["slug"], name="course_slug_idx"),
            models.Index(
                fields=["status", "published_at"], name="course_status_pub_idx"
            ),
            models.Index(fields=["instructor", "status"], name="course_instructor_idx"),
            models.Index(fields=["unlock_rule", "status"], name="course_unlock_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(price__gte=0), name="course_price_non_negative"
            ),
            models.CheckConstraint(
                condition=Q(status__in=[s.value for s in CourseStatus]),
                name="course_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(unlock_rule__in=[r.value for r in UnlockRule]),
                name="course_unlock_rule_valid",
            ),
        ]

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._unique_slug()
        if self.summary and len(self.summary) > 500:
            self.summary = self.summary[:500]
        super().save(*args, **kwargs)

    def _unique_slug(self) -> str:
        base = slugify(self.title)[:200] or "course"
        candidate = base
        counter = 2
        while Course.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
            candidate = f"{base}-{counter}"
            counter += 1
        return candidate

    @property
    def is_published(self) -> bool:
        return self.status == CourseStatus.PUBLISHED

    def get_absolute_url(self) -> str:
        return reverse("course-detail", kwargs={"slug": self.slug})

    def publish(self) -> None:
        """Flip to PUBLISHED, stamping ``published_at`` only on first publish."""
        self.status = CourseStatus.PUBLISHED
        if self.published_at is None:
            self.published_at = timezone.now()
        self.save(update_fields=["status", "published_at", "updated_at"])

    def refresh_aggregates(self) -> None:
        """Recompute denormalised counts/duration in one aggregate query.

        Called after lesson changes instead of annotating the list queryset on
        every request -- list pages then need no join at all.
        """
        from django.db.models import Count, Sum

        stats = self.sections.aggregate(
            total_duration=Sum("lessons__duration_seconds"),
            total_lessons=Count(
                "lessons", filter=Q(lessons__status=LessonStatus.PUBLISHED)
            ),
        )
        self.duration_minutes = int((stats["total_duration"] or 0) / 60)
        self.lesson_count = stats["total_lessons"] or 0
        self.save(update_fields=["duration_minutes", "lesson_count", "updated_at"])


class Section(TimeStampedModel):
    """An ordered chapter inside a course."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="sections"
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    ordering = models.PositiveIntegerField(default=1, db_index=True)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ("ordering", "created_at")
        verbose_name = _("section")
        verbose_name_plural = _("sections")
        indexes = [
            models.Index(
                fields=["course", "ordering"], name="section_course_order_idx"
            ),
        ]
        constraints = [
            # Two sections cannot share a position within the same course.
            models.UniqueConstraint(
                fields=["course", "ordering"], name="unique_section_ordering_per_course"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.course.title} -- {self.title}"


class Lesson(TimeStampedModel):
    """A single watchable unit: video first, quiz optional, text as fallback."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    section = models.ForeignKey(
        Section, on_delete=models.CASCADE, related_name="lessons"
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    # Media is referenced, never uploaded: Cloudflare Stream owns the bytes.
    video = models.OneToOneField(
        "videos.Video",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lesson",
        help_text="Cloudflare Stream metadata row; the file itself never touches Django.",
    )
    quiz = models.OneToOneField(
        "quizzes.Quiz",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lesson",
    )

    duration_seconds = models.PositiveIntegerField(
        default=0, help_text="Cached from the video row for cheap list rendering."
    )
    ordering = models.PositiveIntegerField(default=1, db_index=True)
    is_preview = models.BooleanField(
        default=False,
        help_text="Preview lessons are watchable without any subscription.",
    )
    status = models.CharField(
        max_length=20,
        choices=LessonStatus.choices,
        default=LessonStatus.DRAFT,
        db_index=True,
    )

    class Meta:
        ordering = ("ordering", "created_at")
        verbose_name = _("lesson")
        verbose_name_plural = _("lessons")
        indexes = [
            models.Index(
                fields=["section", "ordering"], name="lesson_section_order_idx"
            ),
            models.Index(
                fields=["status", "is_preview"], name="lesson_status_preview_idx"
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["section", "ordering"],
                name="unique_lesson_ordering_per_section",
            ),
            # A lesson must contain something the student can actually do.
            # Enforced at the DB level because "empty lesson" is a data-integrity
            # bug that would otherwise only surface as a broken page.
            models.CheckConstraint(
                condition=Q(video__isnull=False) | Q(quiz__isnull=False),
                name="lesson_requires_video_or_quiz",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.section.title} -- {self.title}"

    @property
    def course(self) -> Course:
        """Convenience hop used by serializers (select_related through section)."""
        return self.section.course

    @property
    def is_published(self) -> bool:
        return self.status == LessonStatus.PUBLISHED

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Keep the course's denormalised duration/lesson counts in sync.  This is
        # one extra aggregate per write, which is nothing compared to the cost of
        # joining on every course-list read.
        self.section.course.refresh_aggregates()
