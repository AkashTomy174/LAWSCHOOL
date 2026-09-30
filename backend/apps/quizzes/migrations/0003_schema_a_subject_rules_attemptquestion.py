# Schema A: add Subject / QuizSectionRule / AttemptQuestion and the new Question
# fields, WITHOUT removing Question.quiz/ordering yet -- the data migration that
# follows (0004) needs to read those to backfill. They are dropped in 0005.

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('quizzes', '0002_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='AttemptQuestion',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('ordering', models.PositiveIntegerField(default=1)),
                ('marks', models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(1)])),
            ],
            options={
                'verbose_name': 'attempt question',
                'verbose_name_plural': 'attempt questions',
                'ordering': ('ordering',),
            },
        ),
        migrations.CreateModel(
            name='QuizSectionRule',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('question_count', models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(1)])),
                ('marks_per_question', models.PositiveIntegerField(default=1, validators=[django.core.validators.MinValueValidator(1)])),
                ('ordering', models.PositiveIntegerField(default=1)),
            ],
            options={
                'verbose_name': 'quiz section rule',
                'verbose_name_plural': 'quiz section rules',
                'ordering': ('ordering', 'id'),
            },
        ),
        migrations.CreateModel(
            name='Subject',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=120, unique=True)),
                ('slug', models.SlugField(max_length=140, unique=True)),
                ('description', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'subject',
                'verbose_name_plural': 'subjects',
                'ordering': ('name',),
            },
        ),
        migrations.AlterModelOptions(
            name='question',
            options={'ordering': ('-created_at',), 'permissions': [('manage_question_bank', 'Can create/edit shared question bank')], 'verbose_name': 'question', 'verbose_name_plural': 'questions'},
        ),
        migrations.AlterModelOptions(
            name='quizanswer',
            options={'ordering': ('answered_at',), 'verbose_name': 'quiz answer', 'verbose_name_plural': 'quiz answers'},
        ),
        migrations.AddField(
            model_name='question',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='question',
            name='is_active',
            field=models.BooleanField(default=True, help_text='Inactive questions are never sampled into a new attempt.'),
        ),
        migrations.AddField(
            model_name='question',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AlterField(
            model_name='question',
            name='marks',
            field=models.PositiveIntegerField(default=1, help_text="Baseline/suggested marks; a quiz's rule sets the marks actually awarded.", validators=[django.core.validators.MinValueValidator(1)]),
        ),
        migrations.AlterField(
            model_name='question',
            name='quiz',
            field=models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.CASCADE, related_name='legacy_questions', to='quizzes.quiz'),
        ),
        migrations.AddField(
            model_name='attemptquestion',
            name='attempt',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attempt_questions', to='quizzes.quizattempt'),
        ),
        migrations.AddField(
            model_name='attemptquestion',
            name='question',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='attempt_uses', to='quizzes.question'),
        ),
        migrations.AddField(
            model_name='quizsectionrule',
            name='quiz',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='section_rules', to='quizzes.quiz'),
        ),
        migrations.AddField(
            model_name='quizsectionrule',
            name='subject',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='quiz_rules', to='quizzes.subject'),
        ),
        migrations.AddField(
            model_name='attemptquestion',
            name='subject',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='attempt_questions', to='quizzes.subject'),
        ),
        migrations.AddField(
            model_name='question',
            name='subjects',
            field=models.ManyToManyField(blank=True, related_name='questions', to='quizzes.subject'),
        ),
        migrations.AddConstraint(
            model_name='quizsectionrule',
            constraint=models.UniqueConstraint(fields=('quiz', 'subject'), name='unique_rule_per_quiz_subject'),
        ),
        migrations.AddConstraint(
            model_name='attemptquestion',
            constraint=models.UniqueConstraint(fields=('attempt', 'question'), name='unique_question_per_attempt'),
        ),
    ]
