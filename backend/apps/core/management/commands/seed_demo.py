"""Seed the database with a realistic demo dataset.

Idempotent by design: running it twice updates rather than duplicating, so it is
safe to use from ``docker-compose up`` on every boot.

    python manage.py seed_demo
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.core.constants import CourseStatus, LessonStatus


class Command(BaseCommand):
    help = "Create demo users, plans, courses, sections, lessons, videos and quizzes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--students", type=int, default=12, help="How many demo students to create."
        )
        parser.add_argument(
            "--with-subscription",
            action="store_true",
            help="Give the demo student an active subscription.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        from apps.courses.models import Course, Lesson, Section
        from apps.quizzes.models import (
            Option,
            Question,
            Quiz,
            QuizSectionRule,
            Subject,
        )
        from apps.subscriptions.models import Plan
        from apps.users.models import User
        from apps.videos.models import Video

        self.stdout.write(self.style.MIGRATE_HEADING("Seeding LawSchool demo data..."))

        admin = self._user(
            User,
            email="admin@lawschool.test",
            name="Platform Admin",
            role="admin",
            password="AdminPass123!",
            is_staff=True,
            is_superuser=True,
        )
        instructor = self._user(
            User,
            email="instructor@lawschool.test",
            name="Adv. Meera Krishnan",
            role="instructor",
            password="Instructor123!",
            qualification="LL.M. (Constitutional Law), Advocate-on-Record",
        )
        student = self._user(
            User,
            email="student@lawschool.test",
            name="Rahul Sharma",
            role="student",
            password="StudentPass123!",
        )

        students = [student]
        for index in range(1, max(0, options["students"])):
            students.append(
                self._user(
                    User,
                    email=f"student{index}@lawschool.test",
                    name=f"Demo Student {index}",
                    role="student",
                    password="StudentPass123!",
                )
            )

        plans = self._plans(Plan)
        courses = self._courses(Course, instructor)
        self._videos_and_lessons(Video, Section, Lesson, courses)
        self._quizzes(Quiz, Question, Option, QuizSectionRule, Subject, courses)

        # Give every demo plan access to every published course (all-access tiers
        # plus one limited tier that only covers the first course).
        all_access = plans[1]
        limited = plans[0]
        limited.courses.set([courses[0]])

        if options["with_subscription"]:
            from apps.subscriptions.services_lifecycle import activate_subscription

            activate_subscription(
                user=student, plan=all_access, payment_reference="demo_seed"
            )

        self.stdout.write(self.style.SUCCESS("\nSeed complete. Sign in with:"))
        self.stdout.write("  Admin      : admin@lawschool.test / AdminPass123!")
        self.stdout.write("  Instructor : instructor@lawschool.test / Instructor123!")
        self.stdout.write("  Student    : student@lawschool.test / StudentPass123!")
        self.stdout.write(
            f"\n{len(students)} students, {len(courses)} courses, {len(plans)} plans."
        )

    # ------------------------------------------------------------------ #
    def _user(self, User, *, email, name, role, password, **extra):
        user, created = User.objects.get_or_create(
            email=email, defaults={"name": name, "role": role, **extra}
        )
        # Always reset the password so the documented demo credentials work.
        user.set_password(password)
        for key, value in extra.items():
            setattr(user, key, value)
        user.role = role
        user.name = name
        user.is_email_verified = True
        user.save()
        self.stdout.write(("  + created " if created else "  ~ updated ") + email)
        return user

    def _plans(self, Plan):
        definitions = [
            {
                "name": "Foundations",
                "slug": "foundations",
                "description": "Start your law journey with constitution and legal reasoning essentials.",
                "price": Decimal("1999.00"),
                "duration_days": 180,
                "ordering": 1,
            },
            {
                "name": "All Access",
                "slug": "all-access",
                "description": "Every course, every quiz, every leaderboard. The complete LawSchool library.",
                "price": Decimal("4999.00"),
                "duration_days": 365,
                "is_all_access": True,
                "is_featured": True,
                "ordering": 2,
            },
            {
                "name": "Judiciary Intensive",
                "slug": "judiciary-intensive",
                "description": "Two years of access with exam-focused modules and mock tests.",
                "price": Decimal("8999.00"),
                "duration_days": 730,
                "is_all_access": True,
                "ordering": 3,
            },
        ]
        plans = []
        for definition in definitions:
            plan, _ = Plan.objects.update_or_create(
                slug=definition["slug"], defaults=definition
            )
            plans.append(plan)
        self.stdout.write(f"  + {len(plans)} plans")
        return plans

    def _courses(self, Course, instructor):
        definitions = [
            {
                "title": "Constitutional Law Foundations",
                "slug": "constitutional-law-foundations",
                "subtitle": "Article by article, from Preamble to Fundamental Duties",
                "summary": "Master the Indian Constitution with structured, exam-ready modules.",
                "description": (
                    "A complete walkthrough of the Constitution of India: the Preamble, "
                    "Fundamental Rights, Directive Principles, and the federal structure. "
                    "Each section pairs a recorded lecture with a graded quiz."
                ),
                "price": Decimal("1999.00"),
                "level": "Beginner",
                "status": CourseStatus.PUBLISHED,
                "published_at": timezone.now() - timedelta(days=30),
            },
            {
                "title": "Criminal Procedure Essentials",
                "slug": "criminal-procedure-essentials",
                "subtitle": "CrPC to BNSS: procedure that decides outcomes",
                "summary": "From FIR to trial -- the procedural code explained through case law.",
                "description": (
                    "Procedure wins and loses more cases than substance. This course covers "
                    "investigation, arrest, bail, charge framing, trial and appeal, with the "
                    "2023 transitions to the BNSS highlighted throughout."
                ),
                "price": Decimal("2499.00"),
                "level": "Intermediate",
                "status": CourseStatus.PUBLISHED,
                "published_at": timezone.now() - timedelta(days=14),
            },
            {
                "title": "Contract Law Masterclass",
                "slug": "contract-law-masterclass",
                "subtitle": "Offer, acceptance, consideration and remedies in practice",
                "summary": "Draft, read and litigate contracts with confidence.",
                "description": (
                    "A practical contract law course built around real drafting exercises, "
                    "remedies analysis and landmark judgments."
                ),
                "price": Decimal("1499.00"),
                "level": "Beginner",
                "status": CourseStatus.DRAFT,
                "published_at": None,
            },
        ]
        courses = []
        for definition in definitions:
            course, _ = Course.objects.update_or_create(
                slug=definition["slug"],
                defaults={**definition, "instructor": instructor},
            )
            courses.append(course)
        self.stdout.write(f"  + {len(courses)} courses")
        return courses

    def _videos_and_lessons(self, Video, Section, Lesson, courses):
        sections_by_course = {
            courses[0].slug: [
                (
                    "Foundations of the Constitution",
                    [
                        "The Preamble",
                        "Fundamental Rights: Part III",
                        "Directive Principles",
                    ],
                ),
                (
                    "The Federal Structure",
                    ["Centre-State Relations", "Emergency Provisions"],
                ),
            ],
            courses[1].slug: [
                (
                    "Investigation",
                    ["FIR and Cognisable Offences", "Arrest and Custody"],
                ),
                ("Trial", ["Bail Jurisprudence", "Charge and Discharge"]),
            ],
        }

        created_videos = 0
        for course in courses[:2]:
            for section_index, (section_title, lesson_titles) in enumerate(
                sections_by_course.get(course.slug, []), start=1
            ):
                section, _ = Section.objects.update_or_create(
                    course=course,
                    ordering=section_index,
                    defaults={"title": section_title, "is_published": True},
                )
                for lesson_index, lesson_title in enumerate(lesson_titles, start=1):
                    cf_id = f"demo{abs(hash((course.slug, section_title, lesson_title))) % 10**12:012d}"
                    video, _ = Video.objects.update_or_create(
                        cloudflare_video_id=cf_id,
                        defaults={
                            "title": lesson_title,
                            "duration_seconds": 600 + lesson_index * 60,
                            "status": "ready",
                            "require_signed_urls": True,
                            "thumbnail_url": "",
                        },
                    )
                    created_videos += 1
                    Lesson.objects.update_or_create(
                        section=section,
                        ordering=lesson_index,
                        defaults={
                            "title": lesson_title,
                            "description": f"{lesson_title} -- recorded lecture with worked examples.",
                            "video": video,
                            "duration_seconds": video.duration_seconds,
                            "status": LessonStatus.PUBLISHED,
                            "is_preview": lesson_index == 1 and section_index == 1,
                        },
                    )
            course.refresh_aggregates()
        self.stdout.write(f"  + {created_videos} videos with lessons")

    def _quizzes(self, Quiz, Question, Option, QuizSectionRule, Subject, courses):
        definitions = [
            {
                "course": courses[0],
                "title": "Constitutional Law -- Module 1 Quiz",
                "questions": [
                    (
                        "Which Article of the Constitution deals with the Right to Constitutional Remedies?",
                        ["Article 32", "Article 19", "Article 21", "Article 14"],
                        "Article 32",
                        "Article 32 empowers the Supreme Court to issue writs, and Dr. Ambedkar called it the heart and soul of the Constitution.",
                    ),
                    (
                        "The Preamble declares India to be a:",
                        [
                            "Sovereign Socialist Secular Democratic Republic",
                            "Federal Monarchy",
                            "Unitary Republic",
                            "Confederation",
                        ],
                        "Sovereign Socialist Secular Democratic Republic",
                        "'Socialist' and 'Secular' were inserted by the 42nd Amendment, 1976.",
                    ),
                    (
                        "Fundamental Rights can be suspended during a National Emergency under which Article?",
                        ["Article 352", "Article 356", "Article 360", "Article 368"],
                        "Article 352",
                        "Article 352 governs the proclamation of National Emergency; most Fundamental Rights other than Articles 20 and 21 may be suspended.",
                    ),
                ],
            },
            {
                "course": courses[1],
                "title": "Criminal Procedure -- Bail Basics",
                "questions": [
                    (
                        "Under the BNSS, which provision governs bail for non-bailable offences?",
                        ["Section 480", "Section 436", "Section 439", "Section 167"],
                        "Section 480",
                        "The BNSS renumbered the bail provisions; Section 480 corresponds to the old Section 439 CrPC.",
                    ),
                    (
                        "A person arrested must be produced before a Magistrate normally within:",
                        ["24 hours", "48 hours", "72 hours", "7 days"],
                        "24 hours",
                        "Article 22(2) and Section 58 BNSS require production within 24 hours excluding journey time.",
                    ),
                ],
            },
        ]
        for definition in definitions:
            quiz, _ = Quiz.objects.update_or_create(
                course=definition["course"],
                title=definition["title"],
                defaults={
                    "description": "Auto-graded practice test. Best of your attempts counts for the leaderboard.",
                    "pass_percentage": 60,
                    "max_attempts": 3,
                    "is_published": True,
                },
            )
            # Questions live in the shared bank under a subject; a section rule
            # tells the quiz how many to draw from it.
            subject, _ = Subject.objects.update_or_create(
                slug=slugify(definition["title"])[:140],
                defaults={"name": definition["title"][:120]},
            )
            for text, options, correct, explanation in definition["questions"]:
                question, _ = Question.objects.update_or_create(
                    text=text,
                    defaults={"marks": 1, "explanation": explanation},
                )
                question.subjects.add(subject)
                for o_index, option_text in enumerate(options, start=1):
                    Option.objects.update_or_create(
                        question=question,
                        ordering=o_index,
                        defaults={
                            "text": option_text,
                            "is_correct": option_text == correct,
                        },
                    )
            QuizSectionRule.objects.update_or_create(
                quiz=quiz,
                subject=subject,
                defaults={
                    "question_count": len(definition["questions"]),
                    "marks_per_question": 1,
                    "ordering": 1,
                },
            )
        self.stdout.write(f"  + {len(definitions)} quizzes with questions and options")
