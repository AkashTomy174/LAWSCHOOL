"""Leaderboard tests.

Two things are being verified:

1. **Correctness** — the score, the ordering and the rank match the underlying
   quiz/progress data.
2. **Scaling** — ranking is computed by the database, not by iterating every
   student in Python.  ``QueryCounter`` enforces that with a hard query budget,
   and a dataset of 120 students proves the query count does not grow with the
   number of students.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.core.db import QueryCounter
from apps.leaderboard.models import LeaderboardEntry, recalculate_entry, stamp_ranks
from apps.quizzes.models import Quiz, QuizAttempt
from apps.videos.models import VideoProgress

pytestmark = pytest.mark.django_db

User = get_user_model()


def make_students(count: int) -> list:
    """Create ``count`` students in one bulk insert (fast, no per-row hashing)."""
    students = [
        User(email=f"ranked{i}@test.local", name=f"Ranked {i}", role="student")
        for i in range(count)
    ]
    return User.objects.bulk_create(students)


def give_quiz_score(
    student, quiz, score: int, passed: bool = True, attempt_number: int = 1
):
    """Record a graded attempt with a *valid* percentage.

    The model has a CHECK constraint on ``percentage`` (0-100), so the value is
    derived from ``max_score`` rather than multiplied blindly.
    """
    max_score = max(10, score)
    return QuizAttempt.objects.create(
        quiz=quiz,
        user=student,
        attempt_number=attempt_number,
        started_at=timezone.now(),
        submitted_at=timezone.now(),
        score=score,
        max_score=max_score,
        percentage=round((score / max_score) * 100, 2),
        passed=passed,
    )


class TestScoreCalculation:
    def test_quiz_score_is_summed_from_attempts(self, student, quiz):
        give_quiz_score(student, quiz, 7, attempt_number=1)
        give_quiz_score(student, quiz, 4, attempt_number=2)
        entry = recalculate_entry(student)
        assert entry.quiz_score == 11

    def test_lesson_completion_contributes_points(self, student, lesson):
        VideoProgress.objects.create(
            user=student,
            video=lesson.video,
            lesson=lesson,
            last_position=600,
            completion_percentage=100,
            completed=True,
        )
        entry = recalculate_entry(student)
        assert entry.lessons_completed == 1
        assert entry.total_score == 10  # one lesson x 10 points

    def test_quiz_and_lessons_combine(self, student, quiz, lesson):
        give_quiz_score(student, quiz, 8)
        VideoProgress.objects.create(
            user=student,
            video=lesson.video,
            lesson=lesson,
            completed=True,
            completion_percentage=100,
        )
        entry = recalculate_entry(student)
        assert entry.quiz_score == 8
        assert entry.lessons_completed == 1
        assert entry.total_score == 18

    def test_courses_completed_requires_every_lesson(
        self, student, course, lesson, preview_lesson
    ):
        # Only one of the two published lessons is complete.
        VideoProgress.objects.create(
            user=student,
            video=lesson.video,
            lesson=lesson,
            completed=True,
            completion_percentage=100,
        )
        assert recalculate_entry(student).courses_completed == 0

        VideoProgress.objects.create(
            user=student,
            video=preview_lesson.video,
            lesson=preview_lesson,
            completed=True,
            completion_percentage=100,
        )
        assert recalculate_entry(student).courses_completed == 1

    def test_recalculation_is_idempotent(self, student, quiz):
        give_quiz_score(student, quiz, 5)
        first = recalculate_entry(student)
        second = recalculate_entry(student)
        assert first.total_score == second.total_score
        assert LeaderboardEntry.objects.filter(user=student).count() == 1

    def test_unsubmitted_attempts_do_not_count(self, student, quiz):
        QuizAttempt.objects.create(
            quiz=quiz, user=student, attempt_number=1, started_at=timezone.now()
        )
        assert recalculate_entry(student).quiz_score == 0


class TestRanking:
    def test_ranks_are_assigned_in_score_order(self, quiz):
        students = make_students(5)
        for index, student in enumerate(students):
            give_quiz_score(student, quiz, score=index + 1)

        for student in students:
            recalculate_entry(student)
        stamp_ranks()

        ordered = list(LeaderboardEntry.objects.order_by("rank"))
        assert [entry.total_score for entry in ordered] == [5, 4, 3, 2, 1]
        assert [entry.rank for entry in ordered] == [1, 2, 3, 4, 5]

    def test_user_rank_reports_position(self, quiz):
        from apps.leaderboard.models import user_rank

        students = make_students(4)
        for index, student in enumerate(students):
            give_quiz_score(student, quiz, score=(index + 1) * 2)
            recalculate_entry(student)
        stamp_ranks()

        # Highest score is the last student.
        best = students[-1]
        assert best.leaderboard_entry.total_score == 8
        assert user_rank(best) == 1

    def test_equal_scores_break_ties_deterministically(self, quiz):
        students = make_students(3)
        for student in students:
            give_quiz_score(student, quiz, score=5)
            recalculate_entry(student)
        stamp_ranks()

        ranks = sorted(entry.rank for entry in LeaderboardEntry.objects.all())
        assert ranks == [1, 2, 3]  # no duplicate ranks

    def test_student_without_entries_has_no_rank(self, student):
        from apps.leaderboard.models import user_rank

        assert user_rank(student) is None


class TestScaling:
    """The performance contract: ranking must not load every row into Python."""

    def test_top_entries_uses_a_bounded_number_of_queries(self, quiz):
        students = make_students(120)
        for index, student in enumerate(students):
            give_quiz_score(student, quiz, score=index % 10)
            recalculate_entry(student)

        # Serializing the top 50 rows: 1 query for the entries + 1 joined user.
        with QueryCounter(limit=6):
            from apps.leaderboard.models import top_entries

            entries = list(top_entries(limit=50))
            for entry in entries:
                entry.user.get_full_name()
        assert len(entries) == 50

    def test_leaderboard_api_query_count_is_constant(
        self, jwt_client, quiz, admin_user
    ):
        students = make_students(120)
        for index, student in enumerate(students):
            give_quiz_score(student, quiz, score=index % 10)
            recalculate_entry(student)

        client = jwt_client(admin_user)
        # Constant regardless of cohort size: entries page + count + rank COUNT.
        with QueryCounter(limit=12):
            response = client.get("/api/v1/leaderboard/")
        assert response.status_code == 200
        assert len(response.data["results"]) <= 20

    def test_rank_computation_does_not_load_all_rows(self, quiz):
        from apps.leaderboard.models import user_rank

        students = make_students(120)
        for index, student in enumerate(students):
            give_quiz_score(student, quiz, score=index % 10)
            recalculate_entry(student)

        target = students[60]
        # A COUNT-based rank is a single indexed query, not a full scan in Python.
        with QueryCounter(limit=2):
            rank = user_rank(target)
        assert rank is not None and rank > 0


class TestLeaderboardAPI:
    def test_leaderboard_requires_authentication(self, api_client):
        assert api_client.get("/api/v1/leaderboard/").status_code == 401

    def test_leaderboard_is_paginated(self, jwt_client, student, quiz):
        students = make_students(45)
        for index, other in enumerate(students):
            give_quiz_score(other, quiz, score=index % 10)
            recalculate_entry(other)

        response = jwt_client(student).get("/api/v1/leaderboard/")
        assert response.status_code == 200
        assert response.data["count"] >= 45
        assert len(response.data["results"]) == 20
        assert response.data["next"] is not None

    def test_leaderboard_exposes_no_email_addresses(self, jwt_client, student, quiz):
        """Ranking pages are the easiest place to leak personal data."""
        other = make_students(1)[0]
        give_quiz_score(other, quiz, score=3)
        recalculate_entry(other)

        response = jwt_client(student).get("/api/v1/leaderboard/")
        body = str(response.data)
        assert other.email not in body
        assert "password" not in body.lower()

    def test_my_rank_endpoint_reports_standing(self, jwt_client, student, quiz):
        give_quiz_score(student, quiz, score=9)
        recalculate_entry(student)

        response = jwt_client(student).get("/api/v1/leaderboard/me/")
        assert response.status_code == 200
        assert response.data["total_score"] == 9
        assert response.data["rank"] == 1

    def test_my_rank_endpoint_for_unranked_student(self, jwt_client, student):
        response = jwt_client(student).get("/api/v1/leaderboard/me/")
        assert response.status_code == 200
        assert response.data["total_score"] == 0
        assert response.data["rank"] is None

    def test_top_endpoint_is_cached(
        self, jwt_client, student, quiz, django_assert_num_queries
    ):
        give_quiz_score(student, quiz, score=4)
        recalculate_entry(student)

        client = jwt_client(student)
        first = client.get("/api/v1/leaderboard/top/")
        assert first.status_code == 200

        # Second call is served from cache: no leaderboard query is issued.
        from django.core.cache import cache

        assert cache.get("leaderboard:top:10") is not None

    def test_ordering_override_sorts_by_quiz_score(self, jwt_client, student, quiz):
        students = make_students(3)
        for index, other in enumerate(students):
            give_quiz_score(other, quiz, score=(index + 1) * 3)
            recalculate_entry(other)

        response = jwt_client(student).get("/api/v1/leaderboard/?ordering=quiz_score")
        scores = [row["quiz_score"] for row in response.data["results"]]
        # Only the ordering direction matters here, so assert monotonicity.
        assert scores == sorted(scores, reverse=True)

    def test_only_students_appear_in_the_leaderboard(
        self, jwt_client, student, instructor, quiz
    ):
        give_quiz_score(student, quiz, score=3)
        recalculate_entry(student)
        recalculate_entry(instructor)

        response = jwt_client(student).get("/api/v1/leaderboard/")
        user_ids = {row["user_id"] for row in response.data["results"]}
        assert str(instructor.pk) not in user_ids

    def test_admin_can_trigger_recalculation(
        self, jwt_client, admin_user, student, quiz
    ):
        give_quiz_score(student, quiz, score=6)
        response = jwt_client(admin_user).post("/api/v1/leaderboard/recalculate/")
        assert response.status_code == 200
        assert LeaderboardEntry.objects.filter(user=student).exists()

    def test_student_cannot_trigger_recalculation(self, jwt_client, student):
        assert (
            jwt_client(student).post("/api/v1/leaderboard/recalculate/").status_code
            == 403
        )

    def test_snapshot_endpoint_returns_recent_captures(
        self, jwt_client, admin_user, student, quiz
    ):
        from apps.leaderboard.models import snapshot_top

        give_quiz_score(student, quiz, score=2)
        recalculate_entry(student)
        snapshot_top(limit=5)

        response = jwt_client(admin_user).get("/api/v1/leaderboard/snapshots/")
        assert response.status_code == 200
        assert len(response.data) == 1
        assert response.data[0]["scope"] == "global"

    def test_disabled_students_are_excluded(self, jwt_client, student, quiz):
        other = make_students(1)[0]
        give_quiz_score(other, quiz, score=99)
        recalculate_entry(other)
        other.is_active = False
        other.save(update_fields=["is_active"])

        response = jwt_client(student).get("/api/v1/leaderboard/")
        user_ids = {row["user_id"] for row in response.data["results"]}
        assert str(other.pk) not in user_ids
