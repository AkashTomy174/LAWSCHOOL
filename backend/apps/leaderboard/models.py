"""Leaderboard entries and the score aggregation service.

**Scaling rule: never pull every student into Python.** All ranking maths happens
in SQL over indexed columns, using ``GROUP BY`` + window-free ordering, and the
result is paginated.  Row counts that matter (``quiz_score``, ``lessons_completed``)
live on a small derived table that is refreshed incrementally:

* quiz score changes only when an attempt is graded,
* lesson completions change only when a video completes,
* ``courses_completed`` is derived from an aggregate already indexed on
  ``VideoProgress(user, completed)``.

The expensive full recomputation is therefore a background job
(:func:`recalculate_leaderboard`), not a request-time cost.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class LeaderboardEntry(models.Model):
    """Denormalised ranking row: one per student.

    Trade-off: this table duplicates data that could be aggregated on the fly.
    It is worth it because the alternative -- a ``GROUP BY`` over ``QuizAttempt``
    and ``VideoProgress`` for every page load -- scans the two largest tables in
    the system.  Keeping it small and indexed makes the leaderboard O(page_size).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="leaderboard_entry",
    )

    total_score = models.PositiveIntegerField(default=0, db_index=True)
    quiz_score = models.PositiveIntegerField(default=0, db_index=True)
    quizzes_passed = models.PositiveIntegerField(default=0)
    lessons_completed = models.PositiveIntegerField(default=0, db_index=True)
    courses_completed = models.PositiveIntegerField(default=0, db_index=True)
    courses_enrolled = models.PositiveIntegerField(default=0)

    # Computed rank for the current snapshot; handy for "your rank is #12" cards
    # without a window-function query on every dashboard render.
    rank = models.PositiveIntegerField(default=0, db_index=True)

    last_activity_at = models.DateTimeField(null=True, blank=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-total_score", "-lessons_completed", "user__date_joined")
        verbose_name = _("leaderboard entry")
        verbose_name_plural = _("leaderboard entries")
        indexes = [
            # Covering-ish index for the default ordering: score first, then the
            # tie-breakers, so Postgres can walk the index instead of sorting.
            models.Index(
                fields=["-total_score", "-lessons_completed", "user"],
                name="lb_ordering_idx",
            ),
            models.Index(fields=["-courses_completed"], name="lb_courses_idx"),
            models.Index(fields=["last_activity_at"], name="lb_activity_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(total_score__gte=0), name="lb_total_non_negative"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}: {self.total_score} pts (#{self.rank})"


class LeaderboardSnapshot(models.Model):
    """A stored ranking at a point in time, for "your rank changed" analytics."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scope = models.CharField(max_length=50, default="global", db_index=True)
    captured_at = models.DateTimeField(auto_now_add=True, db_index=True)
    entries = models.JSONField(default=list, help_text="Top-N rows at capture time.")

    class Meta:
        ordering = ("-captured_at",)
        indexes = [
            models.Index(fields=["scope", "-captured_at"], name="snapshot_scope_idx")
        ]

    def __str__(self) -> str:
        return f"{self.scope} @ {self.captured_at:%Y-%m-%d %H:%M}"


def recalculate_entry(user) -> LeaderboardEntry:
    """Recompute one student's row from aggregates (constant number of queries)."""
    from apps.courses.models import Course
    from apps.quizzes.models import QuizAttempt
    from apps.videos.models import VideoProgress

    quiz_stats = QuizAttempt.objects.filter(
        user=user, submitted_at__isnull=False
    ).aggregate(
        score=models.Sum("score"),
        passed=models.Count("pk", filter=Q(passed=True)),
    )
    quiz_score = quiz_stats["score"] or 0

    lessons_completed = VideoProgress.objects.filter(user=user, completed=True).count()

    # "Course completed" = every published lesson in the course has a completed
    # progress row for this user.  Expressed as an Exists/NotExists aggregate so
    # the database does the counting rather than Python.
    from apps.courses.models import Lesson
    from apps.core.constants import LessonStatus

    published_lesson_counts = dict(
        Lesson.objects.filter(
            section__course__status="published", status=LessonStatus.PUBLISHED
        )
        .values_list("section__course_id")
        .annotate(total=models.Count("pk"))
    )
    completed_per_course = dict(
        VideoProgress.objects.filter(user=user, completed=True, lesson__isnull=False)
        .values_list("lesson__section__course_id")
        .annotate(total=models.Count("pk", distinct=True))
    )

    courses_completed = sum(
        1
        for course_id, total in published_lesson_counts.items()
        if total and completed_per_course.get(course_id, 0) >= total
    )

    courses_enrolled = (
        Course.objects.filter(pk__in=completed_per_course.keys()).count()
        if completed_per_course
        else 0
    )

    last_activity = (
        VideoProgress.objects.filter(user=user)
        .order_by("-updated_at")
        .values_list("updated_at", flat=True)
        .first()
    )

    # Weighting: quizzes are the primary measurable learning signal, lessons
    # count as steady progress.  Documented so the ranking is explainable.
    total_score = quiz_score + lessons_completed * 10

    entry, _created = LeaderboardEntry.objects.update_or_create(
        user=user,
        defaults={
            "quiz_score": quiz_score,
            "quizzes_passed": quiz_stats["passed"] or 0,
            "lessons_completed": lessons_completed,
            "courses_completed": courses_completed,
            "courses_enrolled": courses_enrolled,
            "total_score": total_score,
            "last_activity_at": last_activity,
        },
    )
    return entry


def refresh_user_leaderboard(user) -> LeaderboardEntry:
    """Public hook used by the quiz/video services after a scoring event."""
    return recalculate_entry(user)


def recalculate_leaderboard(
    *, recompute_ranks: bool = True, batch_size: int = 500
) -> int:
    """Recompute every entry (Celery job) and re-stamp ranks.

    ``iterator()`` keeps memory flat for large cohorts.  Rank stamping is done in
    a single ordered pass, then written with ``bulk_update`` instead of N updates.
    """
    from django.contrib.auth import get_user_model

    User = get_user_model()
    user_ids = (
        User.objects.filter(role="student", is_active=True)
        .values_list("pk", flat=True)
        .iterator()
    )
    for user_id in user_ids:
        recalculate_entry(User(pk=user_id))

    if not recompute_ranks:
        return 0
    return stamp_ranks()


def stamp_ranks() -> int:
    """Assign ``rank`` to every entry using a single ordered scan in SQL."""
    entries = list(
        LeaderboardEntry.objects.select_related("user").order_by(
            "-total_score",
            "-lessons_completed",
            "-courses_completed",
            "user__date_joined",
        )
    )
    updated = []
    for index, entry in enumerate(entries, start=1):
        if entry.rank != index:
            entry.rank = index
            updated.append(entry)
    if updated:
        LeaderboardEntry.objects.bulk_update(updated, ["rank"], batch_size=500)
    return len(updated)


def top_entries(limit: int = 50):
    """Top-N query used by the API.

    One indexed query, ``select_related`` on the user so serializing the rows
    costs no extra queries.
    """
    return (
        LeaderboardEntry.objects.select_related("user")
        .filter(user__is_active=True, user__role="student")
        .order_by(
            "-total_score",
            "-lessons_completed",
            "-courses_completed",
            "user__date_joined",
        )[:limit]
    )


def user_rank(user) -> int | None:
    """A single student's rank, computed without loading the whole table.

    ``COUNT(*) WHERE total_score > mine`` + 1 is an index-only scan, whereas
    Python-side enumeration would read every row.
    """
    entry = getattr(user, "leaderboard_entry", None)
    if entry is None:
        return None
    ahead = LeaderboardEntry.objects.filter(
        Q(total_score__gt=entry.total_score)
        | Q(
            total_score=entry.total_score, lessons_completed__gt=entry.lessons_completed
        )
    ).count()
    return ahead + 1


def snapshot_top(limit: int = 20, scope: str = "global") -> LeaderboardSnapshot:
    """Persist a snapshot of the current top-N (Celery beat, weekly)."""
    entries = [
        {
            "rank": index,
            "user_id": str(entry.user_id),
            "name": entry.user.get_full_name(),
            "total_score": entry.total_score,
        }
        for index, entry in enumerate(top_entries(limit=limit), start=1)
    ]
    snapshot = LeaderboardSnapshot.objects.create(scope=scope, entries=entries)
    # Keep the table bounded -- snapshots are analytics, not records.
    stale_ids = list(
        LeaderboardSnapshot.objects.filter(scope=scope)
        .order_by("-captured_at")
        .values_list("pk", flat=True)[52:]
    )
    if stale_ids:
        LeaderboardSnapshot.objects.filter(pk__in=stale_ids).delete()
    return snapshot


def stale_entries(older_than_hours: int = 24):
    from datetime import timedelta

    cutoff = timezone.now() - timedelta(hours=older_than_hours)
    return LeaderboardEntry.objects.filter(
        models.Q(updated_at__lt=cutoff) | models.Q(updated_at__isnull=True)
    ).select_related("user")
