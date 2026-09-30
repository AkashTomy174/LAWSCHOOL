# Data B: backfill Subject/QuizSectionRule/AttemptQuestion from pre-existing
# Quiz/Question/QuizAttempt/QuizAnswer rows, before the legacy Question.quiz
# and Question.ordering columns are dropped in 0005.
#
# Strategy: one Subject per existing Quiz (not per-course -- two quizzes in the
# same course must not have their question pools silently merged). Every
# question the quiz already had becomes tagged with that Subject, and a single
# QuizSectionRule is created to reproduce today's behaviour ("every question,
# every attempt"). Historical attempts get their AttemptQuestion rows backfilled
# from their QuizAnswer rows so grading/review keep working unchanged.

from collections import Counter

from django.db import migrations
from django.utils.text import slugify


def backfill(apps, schema_editor):
    Quiz = apps.get_model("quizzes", "Quiz")
    Question = apps.get_model("quizzes", "Question")
    Subject = apps.get_model("quizzes", "Subject")
    QuizSectionRule = apps.get_model("quizzes", "QuizSectionRule")
    QuizAttempt = apps.get_model("quizzes", "QuizAttempt")
    AttemptQuestion = apps.get_model("quizzes", "AttemptQuestion")

    for quiz in Quiz.objects.all():
        questions = list(Question.objects.filter(quiz=quiz).order_by("ordering"))
        if not questions:
            continue

        course_title = getattr(quiz.course, "title", "") if quiz.course_id else ""
        base_name = f"{course_title} -- {quiz.title}".strip(" -") or str(quiz.pk)
        name = base_name[:120]
        slug = slugify(base_name)[:140] or str(quiz.pk)

        # Idempotent: re-running (or a partial prior run) must not duplicate rows.
        subject, _created = Subject.objects.get_or_create(
            slug=slug, defaults={"name": name}
        )
        for question in questions:
            question.subjects.add(subject)

        marks_values = [q.marks for q in questions]
        common_marks, _count = Counter(marks_values).most_common(1)[0]
        if len(set(marks_values)) > 1:
            print(
                f"[backfill_subjects] quiz {quiz.pk} ({quiz.title!r}) had "
                f"non-uniform question marks {sorted(set(marks_values))}; "
                f"using the most common value ({common_marks}) for the new rule. "
                f"Review manually if this looks wrong."
            )

        QuizSectionRule.objects.get_or_create(
            quiz=quiz,
            subject=subject,
            defaults={
                "question_count": len(questions),
                "marks_per_question": common_marks,
                "ordering": 1,
            },
        )

        for attempt in QuizAttempt.objects.filter(quiz=quiz):
            answered_question_ids = set(
                attempt.answers.values_list("question_id", flat=True)
            )
            # Old attempts always covered every question in the quiz, answered or
            # not (an unanswered question still produced a QuizAnswer row with
            # selected_option=None) -- so backfill from the full question set to
            # match, not just the answered subset.
            for ordering, question in enumerate(questions, start=1):
                AttemptQuestion.objects.get_or_create(
                    attempt=attempt,
                    question=question,
                    defaults={
                        "subject": subject,
                        "ordering": ordering,
                        "marks": question.marks,
                    },
                )


def noop_reverse(apps, schema_editor):
    # Irreversible by design: reversing would need to guess which Subject/rule
    # rows were migration-created vs. hand-added afterwards. Roll back by
    # restoring a pre-migration backup instead.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("quizzes", "0003_schema_a_subject_rules_attemptquestion"),
    ]

    operations = [
        migrations.RunPython(backfill, noop_reverse),
    ]
