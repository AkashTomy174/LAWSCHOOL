"""Quiz attempt lifecycle and **authoritative server-side scoring**.

The client submits only ``{question_id: option_id}`` pairs.  Every score, pass
flag and percentage is computed here from the database, so a tampered frontend
can at best submit wrong answers -- it can never submit a *score*.

Attempt flow::

    start_attempt()   -> creates QuizAttempt #n after checking limits
    submit_attempt()  -> grades answers, stores QuizAnswer rows, marks the attempt
    (leaderboard)     -> aggregates QuizAttempt rows in SQL
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.core.constants import CourseStatus
from apps.core.exceptions import ConflictError, DomainError, EntitlementError
from apps.core.logging import get_logger
from apps.quizzes.models import (
    AttemptQuestion,
    Option,
    Question,
    Quiz,
    QuizAnswer,
    QuizAttempt,
)
from apps.subscriptions.services import can_user_access_course

logger = get_logger(__name__)


def _locked_course_message(course, decision) -> dict:
    return {
        "detail": decision.detail,
        "reason": decision.reason,
        "course_slug": getattr(course, "slug", ""),
    }


def can_attempt_quiz(user, quiz: Quiz) -> None:
    """Raise unless the user may attempt ``quiz`` right now.

    Combines course entitlement with quiz availability and attempt limits -- the
    three reasons a quiz request is legitimately refused.
    """
    decision = can_user_access_course(user, quiz.course)
    if not decision:
        raise EntitlementError(
            _locked_course_message(quiz.course, decision), code=decision.reason
        )

    if not quiz.is_available_now():
        raise DomainError(
            {"detail": "This quiz is not currently open."}, code="quiz_unavailable"
        )

    if quiz.question_count == 0:
        raise DomainError(
            {"detail": "This quiz has no questions yet."}, code="quiz_empty"
        )

    if quiz.max_attempts and attempts_used(user, quiz) >= quiz.max_attempts:
        raise ConflictError(
            {
                "detail": f"You have used all {quiz.max_attempts} attempts for this quiz.",
                "attempts_allowed": quiz.max_attempts,
            },
            code="attempt_limit_reached",
        )


def attempts_used(user, quiz: Quiz) -> int:
    """Number of *submitted* attempts (an abandoned attempt should not burn one)."""
    return QuizAttempt.objects.filter(
        user=user, quiz=quiz, submitted_at__isnull=False
    ).count()


def attempts_remaining(user, quiz: Quiz) -> int | None:
    if not quiz.max_attempts:
        return None  # unlimited
    return max(0, quiz.max_attempts - attempts_used(user, quiz))


@transaction.atomic
def start_attempt(*, user, quiz: Quiz, ip_address: str | None = None) -> QuizAttempt:
    """Open a new attempt, enforcing entitlement, availability and limits."""
    can_attempt_quiz(user, quiz)

    # Reuse an in-flight attempt rather than burning a new number on a refresh.
    existing = (
        QuizAttempt.objects.select_for_update()
        .filter(user=user, quiz=quiz, submitted_at__isnull=True)
        .order_by("-attempt_number")
        .first()
    )
    if existing is not None:
        return existing

    last_number = (
        QuizAttempt.objects.filter(user=user, quiz=quiz)
        .order_by("-attempt_number")
        .values_list("attempt_number", flat=True)
        .first()
        or 0
    )

    attempt = QuizAttempt.objects.create(
        user=user,
        quiz=quiz,
        attempt_number=last_number + 1,
        started_at=timezone.now(),
        max_score=quiz.total_marks,
        ip_address=ip_address,
    )
    sample_attempt_questions(attempt)
    return attempt


def sample_attempt_questions(attempt: QuizAttempt) -> list[AttemptQuestion]:
    """Randomly draw this attempt's question set per the quiz's section rules.

    Called exactly once, when an attempt is first created (never on resume, so
    a page refresh cannot reshuffle a student's questions mid-attempt).
    """
    quiz = attempt.quiz

    previous_question_ids: set = set()
    previous_attempt = (
        QuizAttempt.objects.filter(
            user=attempt.user, quiz=quiz, submitted_at__isnull=False
        )
        .exclude(pk=attempt.pk)
        .order_by("-attempt_number")
        .first()
    )
    if previous_attempt is not None:
        previous_question_ids = set(
            previous_attempt.attempt_questions.values_list("question_id", flat=True)
        )

    ordering = 1
    rows: list[AttemptQuestion] = []
    for rule in quiz.section_rules.select_related("subject").order_by("ordering"):
        pool = Question.objects.filter(subjects=rule.subject, is_active=True)
        # ponytail: excluding the previous attempt's questions only when the
        # remaining pool is still big enough is a naive anti-repeat window (one
        # attempt back, not N). Widen it with a rolling "last K attempts" lookup
        # if the same questions start repeating within a few attempts.
        fresh_pool = pool.exclude(id__in=previous_question_ids)
        candidates = fresh_pool if fresh_pool.count() >= rule.question_count else pool

        picked = list(candidates.order_by("?")[: rule.question_count])
        for question in picked:
            rows.append(
                AttemptQuestion(
                    attempt=attempt,
                    question=question,
                    subject=rule.subject,
                    ordering=ordering,
                    marks=rule.marks_per_question,
                )
            )
            ordering += 1

    AttemptQuestion.objects.bulk_create(rows)
    return rows


def grade_submission(
    *, attempt: QuizAttempt, answers: dict[str, str]
) -> tuple[int, int, list[dict]]:
    """Score a submission without touching the database.

    ``answers`` maps ``question_id -> option_id``.  Returns
    ``(score, max_score, per_question_results)``.

    Scores against this attempt's own sampled question set
    (``AttemptQuestion``), never the live quiz/bank state, so later edits to a
    rule or a bank question cannot change an already-taken attempt's score.
    """
    attempt_questions = list(
        attempt.attempt_questions.select_related("question")
        .prefetch_related("question__options")
        .order_by("ordering")
    )
    if not attempt_questions:
        raise DomainError({"detail": "This quiz has no questions."}, code="quiz_empty")

    results: list[dict] = []
    score = 0
    max_score = 0

    for attempt_question in attempt_questions:
        question = attempt_question.question
        max_score += attempt_question.marks
        submitted_option_id = answers.get(str(question.id))
        selected = None
        is_correct = False

        if submitted_option_id:
            # Look the option up *within this question* -- a crafted payload naming
            # another question's option cannot earn marks.
            selected = next(
                (
                    opt
                    for opt in question.options.all()
                    if str(opt.id) == str(submitted_option_id)
                ),
                None,
            )
            if selected is not None and selected.is_correct:
                is_correct = True
                score += attempt_question.marks

        results.append(
            {
                "question_id": str(question.id),
                "selected_option_id": str(selected.id) if selected else None,
                "is_correct": is_correct,
                "marks_awarded": attempt_question.marks if is_correct else 0,
                "marks_possible": attempt_question.marks,
            }
        )

    return score, max_score, results


@transaction.atomic
def submit_attempt(
    *, attempt: QuizAttempt, answers: dict[str, str], duration_seconds: int = 0
) -> QuizAttempt:
    """Grade and persist a submission.

    Idempotency: resubmitting an already-submitted attempt returns the stored
    result instead of re-grading, so a retry cannot inflate a score.
    """
    attempt = (
        QuizAttempt.objects.select_for_update()
        .select_related("quiz", "user")
        .get(pk=attempt.pk)
    )

    if attempt.submitted_at is not None:
        logger.info(
            "Duplicate quiz submission ignored", extra={"attempt_id": str(attempt.pk)}
        )
        return attempt

    quiz = attempt.quiz
    # Re-check entitlement at submission time: a subscription can lapse mid-quiz.
    can_attempt_quiz(attempt.user, quiz)

    if len(answers) > attempt.attempt_questions.count():
        raise DomainError(
            {"detail": "More answers submitted than the quiz has questions."},
            code="invalid_submission",
        )

    score, max_score, results = grade_submission(attempt=attempt, answers=answers)
    percentage = (
        (Decimal(score) / Decimal(max_score) * 100) if max_score else Decimal("0")
    )
    percentage = percentage.quantize(Decimal("0.01"))

    QuizAnswer.objects.bulk_create(
        [
            QuizAnswer(
                attempt=attempt,
                question_id=result["question_id"],
                selected_option_id=result["selected_option_id"],
                is_correct=result["is_correct"],
                marks_awarded=result["marks_awarded"],
            )
            for result in results
        ]
    )

    attempt.score = score
    attempt.max_score = max_score
    attempt.percentage = percentage
    attempt.passed = percentage >= quiz.pass_percentage
    attempt.submitted_at = timezone.now()

    # Server-measured duration wins; a client claiming to have taken three hours
    # on a one-minute quiz is not evidence.
    server_duration = int((attempt.submitted_at - attempt.started_at).total_seconds())
    attempt.duration_seconds = (
        min(max(duration_seconds, 0), max(server_duration, 0))
        if duration_seconds
        else server_duration
    )

    attempt.save(
        update_fields=[
            "score",
            "max_score",
            "percentage",
            "passed",
            "submitted_at",
            "duration_seconds",
        ]
    )

    _notify_quiz_result(attempt)
    logger.info(
        "Quiz attempt graded",
        extra={
            "attempt_id": str(attempt.pk),
            "user_id": str(attempt.user_id),
            "score": attempt.score,
            "passed": attempt.passed,
        },
    )
    return attempt


def _notify_quiz_result(attempt: QuizAttempt) -> None:
    try:
        from apps.notifications.services import notify_user

        notify_user(
            user=attempt.user,
            kind="quiz_result",
            context={
                "quiz_title": attempt.quiz.title,
                "score": attempt.score,
                "max_score": attempt.max_score,
                "percentage": str(attempt.percentage),
                "passed": "passed" if attempt.passed else "not passed",
            },
        )
    except Exception:  # pragma: no cover - notifications are never fatal
        logger.exception(
            "Failed to queue quiz-result notification",
            extra={"attempt_id": str(attempt.pk)},
        )


def attempt_review(attempt: QuizAttempt) -> list[dict]:
    """Build the post-submission review payload.

    Safe to include correct answers here -- the attempt is already graded, so this
    cannot leak answers *before* submission.
    """
    answers = {
        answer.question_id: answer
        for answer in attempt.answers.select_related("selected_option", "question")
    }
    review = []
    attempt_questions = attempt.attempt_questions.select_related(
        "question"
    ).prefetch_related("question__options").order_by("ordering")
    for attempt_question in attempt_questions:
        question = attempt_question.question
        answer = answers.get(question.id)
        correct = next((opt for opt in question.options.all() if opt.is_correct), None)
        review.append(
            {
                "question_id": str(question.id),
                "question_text": question.text,
                "explanation": question.explanation,
                "selected_option_id": (
                    str(answer.selected_option_id)
                    if answer and answer.selected_option_id
                    else None
                ),
                "correct_option_id": str(correct.id) if correct else None,
                "is_correct": bool(answer and answer.is_correct),
                "marks_awarded": answer.marks_awarded if answer else 0,
                "marks_possible": attempt_question.marks,
            }
        )
    return review


def course_quiz_summary(user, course) -> dict:
    """Aggregate a student's best quiz performance in one course (single query)."""
    aggregate = QuizAttempt.objects.filter(
        user=user, quiz__course=course, submitted_at__isnull=False
    ).aggregate(total_score=Sum("score"), total_max=Sum("max_score"))
    return {
        "total_score": aggregate["total_score"] or 0,
        "total_max": aggregate["total_max"] or 0,
        "attempts": QuizAttempt.objects.filter(
            user=user, quiz__course=course, submitted_at__isnull=False
        ).count(),
    }
