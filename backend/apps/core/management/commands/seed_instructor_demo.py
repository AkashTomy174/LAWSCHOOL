"""Add instructor-facing demo data on top of ``seed_demo``.

Live classes for the instructor's courses, active subscriptions for the demo
students, graded quiz attempts and video progress -- the things an instructor's
screens (live schedule, attempt lists, completion) have nothing to show without.

    python manage.py seed_demo && python manage.py seed_instructor_demo

Idempotent: live classes are keyed by (course, title); students that already
have attempts or progress are skipped.
"""

from __future__ import annotations

import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

LIVE_CLASSES = [
    # (course index, title, days from now, hour, provider, published)
    (0, "Doubt clearing: Fundamental Rights", -5, 18, "zoom", True),
    (0, "Live: Article 21 and its expansion", 2, 19, "zoom", True),
    (0, "Live: Basic Structure doctrine", 9, 19, "google_meet", True),
    (1, "Live: Bail under the BNSS", 4, 18, "google_meet", True),
    (1, "Mock trial walkthrough", 12, 17, "zoom", True),
    (0, "Unannounced revision session (draft)", 20, 20, "zoom", False),
]


class Command(BaseCommand):
    help = "Create live classes, subscriptions, quiz attempts and progress for the demo instructor."

    @transaction.atomic
    def handle(self, *args, **options):
        from apps.courses.models import Course, Lesson
        from apps.live.models import LiveClass
        from apps.quizzes import services as quiz_services
        from apps.quizzes.models import Quiz, QuizAttempt
        from apps.subscriptions.models import Plan
        from apps.subscriptions.services import active_subscriptions
        from apps.subscriptions.services_lifecycle import activate_subscription
        from apps.users.models import User
        from apps.videos.models import VideoProgress

        instructor = User.objects.filter(email="instructor@lawschool.test").first()
        if instructor is None:
            raise CommandError("Run `manage.py seed_demo` first.")
        courses = list(Course.objects.filter(instructor=instructor).order_by("created_at", "title"))
        if len(courses) < 2:
            raise CommandError("The demo instructor needs at least two courses; run seed_demo.")
        by_slug = {c.slug: c for c in courses}
        courses = [by_slug["constitutional-law-foundations"], by_slug["criminal-procedure-essentials"]]

        students = list(
            User.objects.filter(email__regex=r"^student\d*@lawschool\.test$").order_by("email")
        )
        rng = random.Random(42)  # deterministic scores between runs
        now = timezone.now()

        # --- live classes -------------------------------------------------
        for course_index, title, days, hour, provider, published in LIVE_CLASSES:
            start = (now + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0)
            LiveClass.objects.update_or_create(
                course=courses[course_index],
                title=title,
                defaults={
                    "description": f"{title} with Adv. Meera Krishnan. Bring your questions.",
                    "scheduled_start": start,
                    "duration_minutes": 60,
                    "meeting_provider": provider,
                    "meeting_url": "https://meet.example.com/lawschool-demo"
                    if provider == "google_meet"
                    else "https://zoom.example.com/j/1234567890",
                    "is_published": published,
                },
            )
        self.stdout.write(f"  + {len(LIVE_CLASSES)} live classes")

        # --- subscriptions: all-access for the first 8 students ------------
        plan = Plan.objects.get(slug="all-access")
        subscribed = 0
        for student in students[:8]:
            if not active_subscriptions(student):
                activate_subscription(user=student, plan=plan, payment_reference="demo_instructor_seed")
                subscribed += 1
        self.stdout.write(f"  + {subscribed} new subscriptions")

        # --- quiz attempts (graded through the real service) --------------
        quizzes = list(Quiz.objects.filter(course__in=courses, is_published=True))
        attempts = 0
        for student in students[:8]:
            for quiz in quizzes:
                if QuizAttempt.objects.filter(user=student, quiz=quiz).exists():
                    continue
                skill = rng.choice([0.3, 0.55, 0.7, 0.9])  # chance of picking the right option
                for _ in range(rng.choice([1, 1, 2])):
                    attempt = quiz_services.start_attempt(user=student, quiz=quiz)
                    answers = {}
                    for aq in attempt.attempt_questions.select_related("question").prefetch_related(
                        "question__options"
                    ):
                        options = list(aq.question.options.all())
                        right = next(o for o in options if o.is_correct)
                        pick = right if rng.random() < skill else rng.choice(options)
                        answers[str(aq.question.id)] = str(pick.id)
                    quiz_services.submit_attempt(
                        attempt=attempt, answers=answers, duration_seconds=rng.randint(90, 600)
                    )
                    attempts += 1
        self.stdout.write(f"  + {attempts} graded quiz attempts")

        # --- video progress -------------------------------------------------
        lessons = list(
            Lesson.objects.filter(section__course__in=courses, video__isnull=False).select_related("video")
        )
        progress = 0
        for student in students[:8]:
            for lesson in lessons:
                if rng.random() < 0.35:
                    continue  # not every student watches every lesson
                duration = lesson.video.duration_seconds or 600
                pct = rng.choice([10, 35, 60, 85, 100, 100])
                watched = duration * pct // 100
                _, created = VideoProgress.objects.get_or_create(
                    user=student,
                    video=lesson.video,
                    defaults={
                        "lesson": lesson,
                        "watched_seconds": watched,
                        "last_position": watched,
                        "completion_percentage": Decimal(pct),
                        "completed": pct >= 90,
                        "completed_at": now if pct >= 90 else None,
                    },
                )
                progress += created
        self.stdout.write(f"  + {progress} video progress rows")

        self.stdout.write(self.style.SUCCESS("Instructor demo data ready."))
