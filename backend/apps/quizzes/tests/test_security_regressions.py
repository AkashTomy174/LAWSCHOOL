"""Regression tests for audit findings P2, P3 and AUTH2 (quiz integrity)."""

from __future__ import annotations

from datetime import timedelta
from unittest import mock

import pytest
from django.db import IntegrityError
from django.utils import timezone

from apps.core.exceptions import DomainError
from apps.quizzes.models import (
    AttemptQuestion,
    Option,
    Question,
    Quiz,
    QuizAttempt,
    QuizFixedQuestion,
    QuizSectionRule,
    Subject,
)
from apps.quizzes.services import start_attempt, submit_attempt
from apps.quizzes.tests.test_quizzes import (  # noqa: F401
    answer_map,
    make_attempt,
    make_question,
    rich_quiz,
)

pytestmark = pytest.mark.django_db


def _quiz(course, **kwargs):
    return Quiz.objects.create(course=course, title="Q", is_published=True, **kwargs)


class TestPinnedQuestionRobustness:
    def test_valid_pinned_question_is_served(self, course, student):
        subject = Subject.objects.create(name="A", slug="a")
        question = make_question(subject)
        quiz = _quiz(course)
        QuizFixedQuestion.objects.create(quiz=quiz, question=question, marks=2)
        attempt = make_attempt(quiz, student)
        row = attempt.attempt_questions.get()
        assert row.subject_id == subject.id and row.marks == 2
        assert attempt.max_score == 2

    def test_pinned_question_without_subject_is_skipped_not_500(self, course, student):
        subject = Subject.objects.create(name="B", slug="b")
        good, orphan = make_question(subject, text="good"), make_question(subject, text="orphan")
        quiz = _quiz(course)
        QuizFixedQuestion.objects.create(quiz=quiz, question=good, marks=1)
        QuizFixedQuestion.objects.create(quiz=quiz, question=orphan, marks=5)
        orphan.subjects.clear()
        attempt = make_attempt(quiz, student)
        assert list(attempt.attempt_questions.values_list("question_id", flat=True)) == [good.id]
        assert attempt.max_score == 1  # ceiling matches what was served

    def test_pinned_question_with_broken_options_is_skipped(self, course, student):
        subject = Subject.objects.create(name="C", slug="c")
        good, broken = make_question(subject, text="g"), make_question(subject, text="b")
        Option.objects.filter(question=broken, is_correct=True).update(is_correct=False)
        quiz = _quiz(course)
        for q in (good, broken):
            QuizFixedQuestion.objects.create(quiz=quiz, question=q, marks=1)
        attempt = make_attempt(quiz, student)
        assert attempt.attempt_questions.count() == 1

    def test_no_eligible_questions_raises_domain_error(self, course, student):
        subject = Subject.objects.create(name="D", slug="d")
        question = make_question(subject)
        quiz = _quiz(course)
        QuizFixedQuestion.objects.create(quiz=quiz, question=question, marks=1)
        question.subjects.clear()
        with pytest.raises(DomainError):
            make_attempt(quiz, student)

    def test_start_attempt_rolls_back_when_no_usable_questions(
        self, course, student, active_subscription
    ):
        subject = Subject.objects.create(name="E", slug="e")
        question = make_question(subject)
        quiz = _quiz(course)
        QuizFixedQuestion.objects.create(quiz=quiz, question=question, marks=1)
        question.subjects.clear()
        with pytest.raises(DomainError):
            start_attempt(user=student, quiz=quiz)
        assert not QuizAttempt.objects.filter(quiz=quiz).exists()

    def test_attempt_rolled_back_on_unexpected_db_error(
        self, course, student, active_subscription
    ):
        subject = Subject.objects.create(name="F", slug="f")
        quiz = _quiz(course)
        QuizSectionRule.objects.create(quiz=quiz, subject=subject, question_count=1)
        make_question(subject)
        with mock.patch(
            "apps.quizzes.services.AttemptQuestion.objects.bulk_create",
            side_effect=IntegrityError("boom"),
        ):
            with pytest.raises(Exception):
                start_attempt(user=student, quiz=quiz)
        assert not QuizAttempt.objects.filter(quiz=quiz, submitted_at__isnull=False).exists()
        assert not AttemptQuestion.objects.exists()

    def test_cannot_remove_last_subject_from_pinned_question(
        self, jwt_client, instructor, course
    ):
        subject = Subject.objects.create(name="G", slug="g")
        question = make_question(subject)
        question.created_by = instructor
        question.save()
        QuizFixedQuestion.objects.create(quiz=_quiz(course), question=question, marks=1)
        response = jwt_client(instructor).patch(
            f"/api/v1/quizzes/questions/{question.id}/", {"subjects": []}, format="json"
        )
        assert response.status_code == 400
        assert question.subjects.count() == 1

    def test_scoring_unchanged_for_normal_quiz(self, rich_quiz, student):
        attempt = make_attempt(rich_quiz, student)
        assert attempt.max_score == 6


class TestProtectedDeletes:
    def _owned_question(self, instructor, subject):
        question = make_question(subject)
        question.created_by = instructor
        question.save()
        return question

    def test_pinned_question_delete_is_409(self, jwt_client, instructor, course):
        subject = Subject.objects.create(name="H", slug="h")
        question = self._owned_question(instructor, subject)
        QuizFixedQuestion.objects.create(quiz=_quiz(course), question=question, marks=1)
        response = jwt_client(instructor).delete(f"/api/v1/quizzes/questions/{question.id}/")
        assert response.status_code == 409
        assert response.data["error"]["code"] == "protected_resource"
        assert "Traceback" not in str(response.data)
        assert Question.objects.filter(pk=question.pk).exists()

    def test_attempted_question_delete_keeps_history(
        self, jwt_client, instructor, course, student
    ):
        subject = Subject.objects.create(name="I", slug="i")
        question = self._owned_question(instructor, subject)
        quiz = _quiz(course)
        QuizSectionRule.objects.create(quiz=quiz, subject=subject, question_count=1)
        attempt = make_attempt(quiz, student)
        response = jwt_client(instructor).delete(f"/api/v1/quizzes/questions/{question.id}/")
        assert response.status_code == 409
        assert attempt.attempt_questions.count() == 1

    def test_subject_used_by_rule_delete_is_409(self, jwt_client, admin_user, course):
        subject = Subject.objects.create(name="J", slug="j")
        QuizSectionRule.objects.create(quiz=_quiz(course), subject=subject, question_count=1)
        response = jwt_client(admin_user).delete(f"/api/v1/quizzes/subjects/{subject.id}/")
        assert response.status_code == 409
        assert Subject.objects.filter(pk=subject.pk).exists()

    def test_unreferenced_resources_still_delete(self, jwt_client, admin_user):
        subject = Subject.objects.create(name="K", slug="k")
        question = make_question(subject)
        client = jwt_client(admin_user)
        assert client.delete(f"/api/v1/quizzes/questions/{question.id}/").status_code == 204
        assert client.delete(f"/api/v1/quizzes/subjects/{subject.id}/").status_code == 204


class TestSubmitSurvivesQuizChanges:
    def _open_attempt(self, quiz, student):
        return start_attempt(user=student, quiz=quiz)

    def test_unpublished_after_start_still_grades(self, rich_quiz, student, active_subscription):
        attempt = self._open_attempt(rich_quiz, student)
        Quiz.objects.filter(pk=rich_quiz.pk).update(is_published=False)
        result = submit_attempt(attempt=attempt, answers=answer_map(attempt, correct=True))
        assert result.submitted_at and result.score == 6 and result.passed

    def test_window_closing_after_start_still_grades(
        self, rich_quiz, student, active_subscription
    ):
        attempt = self._open_attempt(rich_quiz, student)
        Quiz.objects.filter(pk=rich_quiz.pk).update(
            available_until=timezone.now() - timedelta(minutes=1)
        )
        result = submit_attempt(attempt=attempt, answers=answer_map(attempt, correct=True))
        assert result.score == 6

    def test_rules_removed_after_start_use_frozen_snapshot(
        self, rich_quiz, student, active_subscription
    ):
        attempt = self._open_attempt(rich_quiz, student)
        rich_quiz.section_rules.all().delete()
        result = submit_attempt(attempt=attempt, answers=answer_map(attempt, correct=True))
        assert (result.score, result.max_score) == (6, 6)

    def test_rule_marks_changed_after_start_do_not_change_score(
        self, rich_quiz, student, active_subscription
    ):
        attempt = self._open_attempt(rich_quiz, student)
        rich_quiz.section_rules.update(marks_per_question=50)
        result = submit_attempt(attempt=attempt, answers=answer_map(attempt, correct=True))
        assert result.score == 6

    def test_late_submission_still_graded_as_unanswered(
        self, rich_quiz, student, active_subscription
    ):
        Quiz.objects.filter(pk=rich_quiz.pk).update(time_limit_minutes=5)
        rich_quiz.refresh_from_db()
        attempt = self._open_attempt(rich_quiz, student)
        QuizAttempt.objects.filter(pk=attempt.pk).update(
            started_at=timezone.now() - timedelta(minutes=10)
        )
        result = submit_attempt(attempt=attempt, answers=answer_map(attempt, correct=True))
        assert result.score == 0

    def test_duplicate_submission_is_idempotent(self, rich_quiz, student, active_subscription):
        attempt = self._open_attempt(rich_quiz, student)
        first = submit_attempt(attempt=attempt, answers=answer_map(attempt, correct=True))
        again = submit_attempt(attempt=attempt, answers={})
        assert again.score == first.score == 6
        assert attempt.answers.count() == 3

    def test_cannot_submit_another_students_attempt(
        self, rich_quiz, student, other_student, jwt_client, active_subscription
    ):
        attempt = self._open_attempt(rich_quiz, student)
        response = jwt_client(other_student).post(
            f"/api/v1/quiz-attempts/{attempt.id}/submit/", {"answers": {}}, format="json"
        )
        assert response.status_code == 403
        attempt.refresh_from_db()
        assert attempt.submitted_at is None

    def test_start_gates_still_apply_to_new_attempts(
        self, rich_quiz, student, active_subscription
    ):
        Quiz.objects.filter(pk=rich_quiz.pk).update(is_published=False)
        rich_quiz.refresh_from_db()
        with pytest.raises(DomainError):
            start_attempt(user=student, quiz=rich_quiz)
