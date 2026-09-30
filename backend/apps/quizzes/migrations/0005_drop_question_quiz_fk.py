# Schema C: drop the legacy Question.ordering / Question.quiz columns now that
# 0004 has backfilled every quiz into Subject + QuizSectionRule + AttemptQuestion.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("quizzes", "0004_backfill_subjects"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="question",
            name="unique_question_ordering_per_quiz",
        ),
        migrations.RemoveIndex(
            model_name="question",
            name="question_quiz_order_idx",
        ),
        migrations.RemoveField(
            model_name="question",
            name="ordering",
        ),
        migrations.RemoveField(
            model_name="question",
            name="quiz",
        ),
    ]
