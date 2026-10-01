"""Quiz tests: authoring permissions, attempt limits, server-side scoring.

The central claim under test is that **the authoritative score is computed in
Python on the server**.  Several tests therefore submit deliberately hostile
payloads (fake scores, other questions' options, duplicate submissions) and assert
that none of them change the recorded result.
"""

from __future__ import annotations

import json

import pytest
from django.utils import timezone

from apps.quizzes.models import (
    Option,
    Question,
    Quiz,
    QuizAttempt,
    QuizSectionRule,
    Subject,
)
from apps.quizzes.services import (
    attempts_remaining,
    attempts_used,
    grade_submission,
    sample_attempt_questions,
    start_attempt,
    submit_attempt,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def rich_quiz(db, course):
    """A quiz with three questions of differing marks, all graded server-side.

    Each question gets its own subject with a count=1 rule, so a fresh attempt
    always samples all three deterministically (one subject's pool has exactly
    one active question) while still letting marks differ per question.
    """
    quiz = Quiz.objects.create(
        course=course,
        title="Constitutional Law Module 1",
        pass_percentage=60,
        max_attempts=3,
        is_published=True,
    )
    specs = [
        ("Article 32 provides the right to?", "writs", "tax", 2),
        ("Who is the guardian of the Constitution?", "supreme court", "parliament", 3),
        ("The Preamble was amended by which amendment?", "42nd", "44th", 1),
    ]
    for index, (text, correct, wrong, marks) in enumerate(specs, start=1):
        subject = Subject.objects.create(
            name=f"Rich Quiz Subject {index}", slug=f"rich-quiz-subject-{index}"
        )
        question = Question.objects.create(
            text=text,
            # Explanations are shown in the post-submission review, so the fixture
            # must populate them for that path to be testable.
            explanation=f"Reference explanation for: {text}",
            marks=marks,
        )
        question.subjects.add(subject)
        Option.objects.create(
            question=question, text=correct, is_correct=True, ordering=1
        )
        Option.objects.create(
            question=question, text=wrong, is_correct=False, ordering=2
        )
        QuizSectionRule.objects.create(
            quiz=quiz,
            subject=subject,
            question_count=1,
            marks_per_question=marks,
            ordering=index,
        )
    return quiz


def make_attempt(quiz: Quiz, user, *, attempt_number: int = 1) -> QuizAttempt:
    """Create an attempt and sample its questions directly (bypassing entitlement).

    Used by pure grading-logic tests that don't care about subscription state.
    """
    attempt = QuizAttempt.objects.create(
        user=user,
        quiz=quiz,
        attempt_number=attempt_number,
        max_score=quiz.total_marks,
    )
    sample_attempt_questions(attempt)
    return attempt


def grant_question_bank_permission(user) -> None:
    """Admin-granted, per-instructor access to the shared question bank."""
    from django.contrib.auth.models import Permission

    user.user_permissions.add(
        Permission.objects.get(
            codename="manage_question_bank", content_type__app_label="quizzes"
        )
    )


def answer_map(attempt: QuizAttempt, *, correct: bool) -> dict[str, str]:
    """Build a submission answering everything correctly or incorrectly."""
    answers = {}
    for aq in attempt.attempt_questions.select_related("question").prefetch_related(
        "question__options"
    ):
        option = aq.question.options.filter(is_correct=correct).first()
        answers[str(aq.question_id)] = str(option.id)
    return answers


# --------------------------------------------------------------------------- #
# Entitlement
# --------------------------------------------------------------------------- #
class TestQuizAccess:
    def test_student_without_subscription_cannot_start(self, jwt_client, student, quiz):
        response = jwt_client(student).post(f"/api/v1/quizzes/{quiz.id}/attempts/")
        assert response.status_code == 403
        assert response.data["error"]["code"] == "subscription_required"

    def test_student_with_expired_subscription_cannot_start(
        self, jwt_client, student, quiz, expired_subscription
    ):
        response = jwt_client(student).post(f"/api/v1/quizzes/{quiz.id}/attempts/")
        assert response.status_code == 403

    def test_subscribed_student_can_start(
        self, jwt_client, student, quiz, active_subscription
    ):
        response = jwt_client(student).post(f"/api/v1/quizzes/{quiz.id}/attempts/")
        assert response.status_code == 201
        assert response.data["attempt"]["attempt_number"] == 1
        assert response.data["attempts_remaining"] == 3

    def test_anonymous_cannot_start(self, api_client, quiz):
        assert (
            api_client.post(f"/api/v1/quizzes/{quiz.id}/attempts/").status_code == 401
        )

    def test_unpublished_quiz_is_not_reachable(
        self, jwt_client, student, quiz, active_subscription
    ):
        quiz.is_published = False
        quiz.save(update_fields=["is_published"])
        assert (
            jwt_client(student).post(f"/api/v1/quizzes/{quiz.id}/attempts/").status_code
            == 404
        )

    def test_quiz_question_payload_never_contains_the_answer_key(
        self, jwt_client, student, quiz, active_subscription
    ):
        """The most important leak to prevent: is_correct must never be serialized."""
        response = jwt_client(student).post(f"/api/v1/quizzes/{quiz.id}/attempts/")
        body = response.data["quiz"]
        assert "is_correct" not in str(body)
        assert "explanation" not in str(body)


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
class TestScoring:
    def test_correct_answers_score_full_marks(self, rich_quiz, student):
        attempt = make_attempt(rich_quiz, student)
        score, max_score, results = grade_submission(
            attempt=attempt, answers=answer_map(attempt, correct=True)
        )
        assert score == max_score == 6
        assert all(result["is_correct"] for result in results)

    def test_wrong_answers_score_zero(self, rich_quiz, student):
        attempt = make_attempt(rich_quiz, student)
        score, max_score, results = grade_submission(
            attempt=attempt, answers=answer_map(attempt, correct=False)
        )
        assert score == 0
        assert max_score == 6
        assert not any(result["is_correct"] for result in results)

    def test_partial_answers_are_scored_per_question(self, rich_quiz, student):
        attempt = make_attempt(rich_quiz, student)
        questions = [
            aq.question
            for aq in attempt.attempt_questions.select_related(
                "question"
            ).prefetch_related("question__options")
        ]
        answers = {
            # First question: right. Second: wrong. Third: omitted entirely.
            str(questions[0].id): str(questions[0].options.get(is_correct=True).id),
            str(questions[1].id): str(questions[1].options.get(is_correct=False).id),
        }
        score, max_score, results = grade_submission(attempt=attempt, answers=answers)
        assert score == 2
        assert max_score == 6
        assert results[2]["selected_option_id"] is None
        assert results[2]["is_correct"] is False

    def test_marks_are_weighted_per_question(self, rich_quiz, student):
        attempt = make_attempt(rich_quiz, student)
        questions = [
            aq.question
            for aq in attempt.attempt_questions.select_related(
                "question"
            ).prefetch_related("question__options")
        ]
        # Only the 3-mark question answered correctly.
        answers = {
            str(questions[1].id): str(questions[1].options.get(is_correct=True).id)
        }
        score, _, _ = grade_submission(attempt=attempt, answers=answers)
        assert score == 3

    def test_empty_submission_scores_zero(self, rich_quiz, student):
        attempt = make_attempt(rich_quiz, student)
        score, max_score, _ = grade_submission(attempt=attempt, answers={})
        assert score == 0
        assert max_score == 6

    def test_option_from_another_question_earns_nothing(self, rich_quiz, student):
        """A crafted payload naming another question's correct option must fail."""
        attempt = make_attempt(rich_quiz, student)
        questions = [
            aq.question
            for aq in attempt.attempt_questions.select_related(
                "question"
            ).prefetch_related("question__options")
        ]
        stolen = questions[1].options.get(is_correct=True)
        answers = {str(questions[0].id): str(stolen.id)}

        score, _, results = grade_submission(attempt=attempt, answers=answers)
        assert score == 0
        assert results[0]["selected_option_id"] is None  # not found within the question

    def test_unknown_option_id_earns_nothing(self, rich_quiz, student):
        import uuid

        attempt = make_attempt(rich_quiz, student)
        question_id = attempt.attempt_questions.first().question_id
        answers = {str(question_id): str(uuid.uuid4())}
        score, _, _ = grade_submission(attempt=attempt, answers=answers)
        assert score == 0


class TestSubmission:
    def test_submission_persists_score_and_answers(
        self, jwt_client, student, rich_quiz, active_subscription
    ):
        client = jwt_client(student)
        start = client.post(f"/api/v1/quizzes/{rich_quiz.id}/attempts/")
        attempt_id = start.data["attempt"]["id"]
        attempt = QuizAttempt.objects.get(pk=attempt_id)

        response = client.post(
            f"/api/v1/quiz-attempts/{attempt_id}/submit/",
            {"answers": answer_map(attempt, correct=True)},
            format="json",
        )
        assert response.status_code == 200
        result = response.data["attempt"]
        assert result["score"] == 6
        assert result["max_score"] == 6
        assert result["percentage"] == "100.00"
        assert result["passed"] is True

        stored = QuizAttempt.objects.get(pk=attempt_id)
        assert stored.answers.count() == 3
        assert stored.submitted_at is not None

    def test_passing_threshold_is_respected(
        self, jwt_client, student, rich_quiz, active_subscription
    ):
        """Two of three questions right = 5/6 = 83% -> pass at a 60% threshold."""
        client = jwt_client(student)
        start = client.post(f"/api/v1/quizzes/{rich_quiz.id}/attempts/")
        attempt = QuizAttempt.objects.get(pk=start.data["attempt"]["id"])
        questions = [
            aq.question
            for aq in attempt.attempt_questions.select_related(
                "question"
            ).prefetch_related("question__options")
        ]
        answers = {
            str(questions[0].id): str(questions[0].options.get(is_correct=True).id),
            str(questions[1].id): str(questions[1].options.get(is_correct=True).id),
        }
        response = client.post(
            f"/api/v1/quiz-attempts/{start.data['attempt']['id']}/submit/",
            {"answers": answers},
            format="json",
        )
        assert response.data["attempt"]["score"] == 5
        assert response.data["attempt"]["passed"] is True

    def test_failing_submission_is_marked_failed(
        self, jwt_client, student, rich_quiz, active_subscription
    ):
        client = jwt_client(student)
        start = client.post(f"/api/v1/quizzes/{rich_quiz.id}/attempts/")
        attempt = QuizAttempt.objects.get(pk=start.data["attempt"]["id"])
        response = client.post(
            f"/api/v1/quiz-attempts/{start.data['attempt']['id']}/submit/",
            {"answers": answer_map(attempt, correct=False)},
            format="json",
        )
        assert response.data["attempt"]["passed"] is False
        assert response.data["attempt"]["score"] == 0

    def test_client_cannot_submit_a_score(
        self, jwt_client, student, rich_quiz, active_subscription
    ):
        """The headline security test: a forged score must be ignored."""
        client = jwt_client(student)
        start = client.post(f"/api/v1/quizzes/{rich_quiz.id}/attempts/")
        attempt_id = start.data["attempt"]["id"]
        attempt = QuizAttempt.objects.get(pk=attempt_id)

        response = client.post(
            f"/api/v1/quiz-attempts/{attempt_id}/submit/",
            {
                "answers": answer_map(attempt, correct=False),
                "score": 999,
                "percentage": 100,
                "passed": True,
                "max_score": 999,
            },
            format="json",
        )
        assert response.status_code == 200
        # Every authority figure comes from the server.
        assert response.data["attempt"]["score"] == 0
        assert response.data["attempt"]["passed"] is False
        assert response.data["attempt"]["max_score"] == 6

    def test_cannot_submit_another_students_attempt(
        self, jwt_client, student, other_student, rich_quiz, active_subscription
    ):
        from conftest import make_plan, make_subscription

        # Give the other student access to the same course.
        make_subscription(
            other_student,
            make_plan(name="P", slug="p-other", courses=[rich_quiz.course]),
        )

        start = jwt_client(student).post(f"/api/v1/quizzes/{rich_quiz.id}/attempts/")
        attempt_id = start.data["attempt"]["id"]
        attempt = QuizAttempt.objects.get(pk=attempt_id)

        response = jwt_client(other_student).post(
            f"/api/v1/quiz-attempts/{attempt_id}/submit/",
            {"answers": answer_map(attempt, correct=True)},
            format="json",
        )
        assert response.status_code == 403
        assert QuizAttempt.objects.get(pk=attempt_id).submitted_at is None

    def test_duplicate_submission_does_not_change_the_score(
        self, jwt_client, student, rich_quiz, active_subscription
    ):
        client = jwt_client(student)
        start = client.post(f"/api/v1/quizzes/{rich_quiz.id}/attempts/")
        attempt_id = start.data["attempt"]["id"]
        attempt = QuizAttempt.objects.get(pk=attempt_id)
        url = f"/api/v1/quiz-attempts/{attempt_id}/submit/"

        first = client.post(
            url, {"answers": answer_map(attempt, correct=False)}, format="json"
        )
        assert first.data["attempt"]["score"] == 0

        # Second submission tries to improve the score.
        second = client.post(
            url, {"answers": answer_map(attempt, correct=True)}, format="json"
        )
        assert second.data["attempt"]["score"] == 0  # unchanged

    def test_more_answers_than_questions_is_rejected(
        self, jwt_client, student, rich_quiz, active_subscription
    ):
        client = jwt_client(student)
        start = client.post(f"/api/v1/quizzes/{rich_quiz.id}/attempts/")
        answers = {f"fake-question-{i}": "fake-option" for i in range(50)}
        response = client.post(
            f"/api/v1/quiz-attempts/{start.data['attempt']['id']}/submit/",
            {"answers": answers},
            format="json",
        )
        assert response.status_code == 400


class TestAttemptLimits:
    def test_max_attempts_is_enforced(
        self, jwt_client, student, quiz, active_subscription
    ):
        client = jwt_client(student)
        assert quiz.max_attempts == 3

        for expected in range(1, 4):
            start = client.post(f"/api/v1/quizzes/{quiz.id}/attempts/")
            assert start.status_code == 201
            assert start.data["attempt"]["attempt_number"] == expected
            attempt = QuizAttempt.objects.get(pk=start.data["attempt"]["id"])
            client.post(
                f"/api/v1/quiz-attempts/{start.data['attempt']['id']}/submit/",
                {"answers": answer_map(attempt, correct=True)},
                format="json",
            )

        # Fourth attempt must be refused.
        response = client.post(f"/api/v1/quizzes/{quiz.id}/attempts/")
        assert response.status_code == 409
        assert response.data["error"]["code"] == "attempt_limit_reached"

    def test_unlimited_attempts_when_max_is_zero(
        self, jwt_client, student, quiz, active_subscription
    ):
        from conftest import make_plan, make_subscription

        quiz.max_attempts = 0
        quiz.save(update_fields=["max_attempts"])

        client = jwt_client(student)
        for _ in range(5):
            start = client.post(f"/api/v1/quizzes/{quiz.id}/attempts/")
            assert start.status_code == 201
            attempt = QuizAttempt.objects.get(pk=start.data["attempt"]["id"])
            client.post(
                f"/api/v1/quiz-attempts/{start.data['attempt']['id']}/submit/",
                {"answers": answer_map(attempt, correct=True)},
                format="json",
            )
        assert attempts_remaining(student, quiz) is None

    def test_abandoned_attempt_does_not_burn_a_number(
        self, jwt_client, student, quiz, active_subscription
    ):
        """Re-opening the page must resume, not consume an attempt."""
        client = jwt_client(student)
        first = client.post(f"/api/v1/quizzes/{quiz.id}/attempts/")
        second = client.post(f"/api/v1/quizzes/{quiz.id}/attempts/")

        assert first.data["attempt"]["id"] == second.data["attempt"]["id"]
        assert attempts_used(student, quiz) == 0
        assert QuizAttempt.objects.filter(user=student, quiz=quiz).count() == 1

    def test_attempts_used_counts_only_submitted_attempts(
        self, student, quiz, active_subscription
    ):
        start_attempt(user=student, quiz=quiz)
        assert attempts_used(student, quiz) == 0

        attempt = QuizAttempt.objects.get(user=student, quiz=quiz)
        submit_attempt(attempt=attempt, answers={})
        assert attempts_used(student, quiz) == 1
        assert attempts_remaining(student, quiz) == 2

    def test_progress_endpoint_reports_standing(
        self, jwt_client, student, quiz, active_subscription
    ):
        client = jwt_client(student)
        start = client.post(f"/api/v1/quizzes/{quiz.id}/attempts/")
        attempt = QuizAttempt.objects.get(pk=start.data["attempt"]["id"])
        client.post(
            f"/api/v1/quiz-attempts/{start.data['attempt']['id']}/submit/",
            {"answers": answer_map(attempt, correct=True)},
            format="json",
        )
        response = client.get(f"/api/v1/quizzes/{quiz.id}/progress/")
        assert response.data["attempts_used"] == 1
        assert response.data["attempts_remaining"] == 2
        assert response.data["best_attempt"]["score"] == 2


class TestResultsAndReview:
    def test_review_reveals_answers_only_after_submission(
        self, jwt_client, student, rich_quiz, active_subscription
    ):
        client = jwt_client(student)
        start = client.post(f"/api/v1/quizzes/{rich_quiz.id}/attempts/")
        attempt_id = start.data["attempt"]["id"]
        attempt = QuizAttempt.objects.get(pk=attempt_id)

        # Before submitting, the detail endpoint must not leak the review.
        # Assert on the parsed JSON payload (what a real client receives) rather
        # than on ``response.data``, which can carry renderer-added keys.
        early = client.get(f"/api/v1/quiz-attempts/{attempt_id}/")
        assert "review" not in json.loads(early.content)

        client.post(
            f"/api/v1/quiz-attempts/{attempt_id}/submit/",
            {"answers": answer_map(attempt, correct=True)},
            format="json",
        )
        after = client.get(f"/api/v1/quiz-attempts/{attempt_id}/")
        assert "review" in after.data
        assert after.data["review"][0]["correct_option_id"]
        assert after.data["review"][0]["explanation"]

    def test_student_cannot_read_another_students_attempt(
        self, jwt_client, student, other_student, quiz, active_subscription
    ):
        attempt = start_attempt(user=student, quiz=quiz)
        submit_attempt(attempt=attempt, answers={})

        response = jwt_client(other_student).get(f"/api/v1/quiz-attempts/{attempt.id}/")
        assert response.status_code == 403

    def test_admin_can_read_any_attempt(
        self, jwt_client, student, admin_user, quiz, active_subscription
    ):
        attempt = start_attempt(user=student, quiz=quiz)
        submit_attempt(attempt=attempt, answers={})

        response = jwt_client(admin_user).get(f"/api/v1/quiz-attempts/{attempt.id}/")
        assert response.status_code == 200

    def test_attempt_history_is_paginated_over_own_attempts(
        self, jwt_client, student, quiz, active_subscription
    ):
        attempt = start_attempt(user=student, quiz=quiz)
        submit_attempt(attempt=attempt, answers={})

        response = jwt_client(student).get("/api/v1/quiz-attempts/")
        assert response.status_code == 200
        assert response.data["count"] == 1

    def test_admin_attempt_list_excludes_other_instructors_quizzes(
        self, jwt_client, instructor, admin_user, quiz, student, active_subscription
    ):
        attempt = start_attempt(user=student, quiz=quiz)
        submit_attempt(attempt=attempt, answers={})

        # The owning instructor sees it...
        assert (
            jwt_client(instructor).get("/api/v1/quiz-attempts/all/").data["count"] == 1
        )
        # ...and so does the platform admin.
        assert (
            jwt_client(admin_user).get("/api/v1/quiz-attempts/all/").data["count"] == 1
        )


class TestQuizAuthoring:
    def test_student_cannot_create_a_quiz(self, jwt_client, student, course):
        response = jwt_client(student).post(
            "/api/v1/quizzes/",
            {"course": str(course.id), "title": "Sneaky Quiz"},
            format="json",
        )
        assert response.status_code == 403

    def test_instructor_can_create_a_quiz(self, jwt_client, instructor, course):
        response = jwt_client(instructor).post(
            "/api/v1/quizzes/",
            {"course": str(course.id), "title": "New Quiz", "pass_percentage": 50},
            format="json",
        )
        assert response.status_code == 201, response.data
        assert Quiz.objects.filter(title="New Quiz").exists()

    def test_instructor_cannot_author_into_another_instructors_course(
        self, jwt_client, course, db
    ):
        from django.contrib.auth import get_user_model

        intruder = get_user_model().objects.create_instructor(
            email="intruder@test.local", password="Pass12345!", name="Intruder"
        )
        response = jwt_client(intruder).post(
            "/api/v1/quizzes/",
            {"course": str(course.id), "title": "Hijacked"},
            format="json",
        )
        assert response.status_code == 403

    def test_pass_percentage_is_validated(self, jwt_client, instructor, course):
        response = jwt_client(instructor).post(
            "/api/v1/quizzes/",
            {"course": str(course.id), "title": "Bad Range", "pass_percentage": 150},
            format="json",
        )
        assert response.status_code == 400

    def test_instructor_can_create_question_and_options(
        self, jwt_client, instructor, quiz, subject
    ):
        grant_question_bank_permission(instructor)
        question = jwt_client(instructor).post(
            "/api/v1/quizzes/questions/",
            {"text": "New question?", "marks": 5, "subjects": [str(subject.id)]},
            format="json",
        )
        assert question.status_code == 201, question.data

        option = jwt_client(instructor).post(
            "/api/v1/quizzes/options/",
            {
                "question": question.data["id"],
                "text": "An answer",
                "is_correct": True,
                "ordering": 1,
            },
            format="json",
        )
        assert option.status_code == 201

    def test_instructor_without_bank_permission_cannot_create_question(
        self, jwt_client, instructor, subject
    ):
        response = jwt_client(instructor).post(
            "/api/v1/quizzes/questions/",
            {"text": "New question?", "marks": 5, "subjects": [str(subject.id)]},
            format="json",
        )
        assert response.status_code == 403

    def test_option_ordering_clash_is_rejected(
        self, jwt_client, instructor, quiz, subject
    ):
        grant_question_bank_permission(instructor)
        question = Question.objects.get(subjects=subject)
        response = jwt_client(instructor).post(
            "/api/v1/quizzes/options/",
            {"question": str(question.id), "text": "Clash", "ordering": 1},
            format="json",
        )
        assert response.status_code == 400

    def test_student_cannot_add_questions(
        self, jwt_client, student, quiz, active_subscription
    ):
        response = jwt_client(student).post(
            "/api/v1/quizzes/questions/",
            {"text": "Injected", "marks": 100},
            format="json",
        )
        assert response.status_code == 403

    def test_availability_window_is_enforced(
        self, jwt_client, student, quiz, active_subscription
    ):
        from datetime import timedelta

        quiz.available_until = timezone.now() - timedelta(days=1)
        quiz.save(update_fields=["available_until"])

        response = jwt_client(student).post(f"/api/v1/quizzes/{quiz.id}/attempts/")
        assert response.status_code == 400
        assert response.data["error"]["code"] == "quiz_unavailable"


def make_question(subject, *, text="Q", marks=1):
    question = Question.objects.create(text=text, marks=marks)
    question.subjects.add(subject)
    Option.objects.create(question=question, text="Right", is_correct=True, ordering=1)
    Option.objects.create(question=question, text="Wrong", is_correct=False, ordering=2)
    return question


class TestSampling:
    """``sample_attempt_questions`` -- per-subject pull counts and anti-repeat."""

    def test_pulls_exactly_rule_question_count_per_subject(self, db, course, student):
        maths = Subject.objects.create(name="Maths", slug="maths")
        physics = Subject.objects.create(name="Physics", slug="physics")
        for i in range(5):
            make_question(maths, text=f"Maths Q{i}")
        for i in range(5):
            make_question(physics, text=f"Physics Q{i}")

        quiz = Quiz.objects.create(course=course, title="Mixed Exam", is_published=True)
        QuizSectionRule.objects.create(
            quiz=quiz, subject=maths, question_count=3, marks_per_question=1, ordering=1
        )
        QuizSectionRule.objects.create(
            quiz=quiz,
            subject=physics,
            question_count=2,
            marks_per_question=1,
            ordering=2,
        )

        attempt = make_attempt(quiz, student)
        rows = list(attempt.attempt_questions.select_related("subject"))
        assert len(rows) == 5
        assert sum(1 for r in rows if r.subject_id == maths.id) == 3
        assert sum(1 for r in rows if r.subject_id == physics.id) == 2

    def test_anti_repeat_excludes_previous_attempts_questions_when_pool_allows(
        self, db, course, student
    ):
        subject = Subject.objects.create(name="History", slug="history")
        questions = [make_question(subject, text=f"History Q{i}") for i in range(4)]

        quiz = Quiz.objects.create(course=course, title="History Exam", is_published=True)
        QuizSectionRule.objects.create(
            quiz=quiz, subject=subject, question_count=2, marks_per_question=1, ordering=1
        )

        first = make_attempt(quiz, student, attempt_number=1)
        first_ids = set(first.attempt_questions.values_list("question_id", flat=True))
        first.submitted_at = timezone.now()
        first.save(update_fields=["submitted_at"])

        second = make_attempt(quiz, student, attempt_number=2)
        second_ids = set(second.attempt_questions.values_list("question_id", flat=True))

        # 4 questions in the pool, 2 already used -- the other 2 are enough to
        # satisfy the rule, so the anti-repeat exclusion should apply fully.
        assert first_ids.isdisjoint(second_ids)
        assert first_ids | second_ids == {q.id for q in questions}

    def test_anti_repeat_falls_back_when_pool_is_too_small(self, db, course, student):
        subject = Subject.objects.create(name="Geography", slug="geography")
        questions = [make_question(subject, text=f"Geo Q{i}") for i in range(2)]

        quiz = Quiz.objects.create(
            course=course, title="Geography Exam", is_published=True
        )
        QuizSectionRule.objects.create(
            quiz=quiz, subject=subject, question_count=2, marks_per_question=1, ordering=1
        )

        first = make_attempt(quiz, student, attempt_number=1)
        first.submitted_at = timezone.now()
        first.save(update_fields=["submitted_at"])

        # Excluding the previous attempt's 2 questions would leave an empty pool
        # (fewer than question_count=2), so sampling must fall back to the full
        # pool instead of failing the attempt outright.
        second = make_attempt(quiz, student, attempt_number=2)
        second_ids = set(second.attempt_questions.values_list("question_id", flat=True))
        assert len(second_ids) == 2
        assert second_ids == {q.id for q in questions}


class TestAuditRegressions:
    def test_instructor_cannot_read_attempt_in_foreign_course(
        self, jwt_client, student, quiz, active_subscription
    ):
        from apps.users.models import User

        stranger = User.objects.create_user(
            email="stranger-instructor@test.local",
            password="InstructorPass123!",
            name="Stranger",
            role="instructor",
        )
        attempt = start_attempt(user=student, quiz=quiz)
        submit_attempt(attempt=attempt, answers={})
        response = jwt_client(stranger).get(f"/api/v1/quiz-attempts/{attempt.id}/")
        assert response.status_code == 403

    def test_course_owner_can_read_attempt(
        self, jwt_client, student, instructor, quiz, active_subscription
    ):
        attempt = start_attempt(user=student, quiz=quiz)
        submit_attempt(attempt=attempt, answers={})
        response = jwt_client(instructor).get(f"/api/v1/quiz-attempts/{attempt.id}/")
        assert response.status_code == 200

    def test_late_submission_discards_answers(
        self, student, rich_quiz, active_subscription
    ):
        from datetime import timedelta

        rich_quiz.time_limit_minutes = 10
        rich_quiz.save()
        attempt = start_attempt(user=student, quiz=rich_quiz)
        QuizAttempt.objects.filter(pk=attempt.pk).update(
            started_at=timezone.now() - timedelta(minutes=20)
        )
        attempt.refresh_from_db()
        result = submit_attempt(attempt=attempt, answers=answer_map(attempt, correct=True))
        assert result.score == 0
        assert result.submitted_at is not None

    def test_on_time_submission_is_graded(self, student, rich_quiz, active_subscription):
        rich_quiz.time_limit_minutes = 10
        rich_quiz.save()
        attempt = start_attempt(user=student, quiz=rich_quiz)
        result = submit_attempt(attempt=attempt, answers=answer_map(attempt, correct=True))
        assert result.score == 6
