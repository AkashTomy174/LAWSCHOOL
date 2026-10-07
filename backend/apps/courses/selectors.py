"""Course read selectors.

Every queryset used by a list/detail endpoint is defined here with explicit
``select_related``/``prefetch_related`` so the N+1 situation is auditable in one
file rather than scattered across views.
"""

from __future__ import annotations

from django.db.models import Count, Prefetch, Q, QuerySet

from apps.core.constants import CourseStatus, LessonStatus, UserRole
from apps.core.permissions import is_admin_user
from apps.courses.models import Course, Lesson, Section


def published_courses(
    *, search: str | None = None, instructor_id=None
) -> QuerySet[Course]:
    """Course list queryset: one join to instructor, no per-row queries."""
    queryset = (
        Course.objects.select_related("instructor")
        .filter(status=CourseStatus.PUBLISHED)
        .order_by("-published_at", "-created_at")
    )
    if instructor_id:
        queryset = queryset.filter(instructor_id=instructor_id)
    if search:
        queryset = queryset.filter(
            Q(title__icontains=search)
            | Q(summary__icontains=search)
            | Q(description__icontains=search)
        )
    return queryset


def visible_courses(user) -> QuerySet[Course]:
    """Every course ``user`` may *read*.  The single course-visibility rule.

    * admins: every course
    * instructors: published courses plus the ones they teach (their drafts)
    * students and anonymous visitors: published courses only

    An instructor's role alone never reveals drafts; ownership does.  This decides
    whether a course can be looked up at all.  Whether its content may be consumed
    is still ``can_user_access_course``'s call.
    """
    queryset = Course.objects.select_related("instructor")
    if is_admin_user(user):
        return queryset
    published = Q(status=CourseStatus.PUBLISHED)
    if user is not None and getattr(user, "role", None) == UserRole.INSTRUCTOR:
        return queryset.filter(published | Q(instructor=user))
    return queryset.filter(published)


def all_courses_for_staff(
    user, *, status: str | None = None, search: str | None = None
) -> QuerySet[Course]:
    """The ``?scope=all`` listing: every course the caller may see, drafts included."""
    queryset = visible_courses(user).order_by("-created_at")
    if status:
        queryset = queryset.filter(status=status)
    if search:
        queryset = queryset.filter(
            Q(title__icontains=search) | Q(slug__icontains=search)
        )
    return queryset


def course_detail(slug: str, *, user) -> Course | None:
    """Detail queryset with sections, lessons and quizzes prefetched.

    A fixed number of queries serves a whole course page regardless of size:
    1 (course) + 1 (sections) + 1 (lessons) + 1 (quizzes).

    Only courses visible to ``user`` (see ``visible_courses``) are found; anything
    else returns ``None``, exactly like a slug that does not exist.
    """
    from apps.quizzes.models import Quiz

    visible_lessons = (
        Lesson.objects.select_related("video", "quiz")
        .filter(status=LessonStatus.PUBLISHED)
        .order_by("ordering")
    )
    return (
        visible_courses(user)
        .filter(slug=slug)
        .prefetch_related(
            Prefetch(
                "sections",
                queryset=Section.objects.filter(is_published=True)
                .order_by("ordering")
                .prefetch_related(
                    Prefetch(
                        "lessons", queryset=visible_lessons, to_attr="visible_lessons"
                    )
                ),
                to_attr="visible_sections",
            ),
            Prefetch(
                "quizzes",
                queryset=Quiz.objects.filter(is_published=True).only(
                    "id", "course_id", "title", "pass_percentage", "max_attempts"
                ),
                to_attr="published_quizzes",
            ),
        )
        .first()
    )


def lessons_for_course(course: Course) -> list[Lesson]:
    """Flat lesson list for a course, resolved from the prefetched sections.

    Reusing the prefetched objects (instead of a fresh query) is what keeps the
    lesson page and the video player from re-reading the tree.
    """
    lessons: list[Lesson] = []
    # ``is None`` rather than ``or``: an empty prefetched list is a real answer,
    # and falling back to ``section.lessons.all()`` would include draft lessons.
    sections = getattr(course, "visible_sections", None)
    if sections is None:
        sections = course.sections.filter(is_published=True).order_by("ordering")
    for section in sections:
        visible = getattr(section, "visible_lessons", None)
        if visible is None:
            visible = section.lessons.filter(status=LessonStatus.PUBLISHED).order_by(
                "ordering"
            )
        lessons.extend(visible)
    return lessons


def lesson_with_context(lesson_id) -> Lesson | None:
    """Single lesson with its section, course, video and quiz joined."""
    return (
        Lesson.objects.select_related("section", "section__course", "video", "quiz")
        .filter(pk=lesson_id)
        .first()
    )


def course_catalogue_stats() -> dict:
    """Cheap counts for the admin dashboard (single aggregate query)."""
    return Course.objects.aggregate(
        total=Count("id"),
        published=Count("id", filter=Q(status=CourseStatus.PUBLISHED)),
        drafts=Count("id", filter=Q(status=CourseStatus.DRAFT)),
    )
