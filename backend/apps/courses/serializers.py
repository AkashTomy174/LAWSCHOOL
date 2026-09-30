"""Course, section and lesson serializers.

A single rule governs these: **a locked lesson must not leak its video**.  The
playback identifiers live on :class:`VideoSerializer`, which is only ever reached
through ``/api/v1/videos/<uid>/playback/`` *after* the entitlement service has
approved the request.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import serializers
from apps.core.constants import CourseStatus
from apps.courses.models import Course, Lesson, Section
from apps.users.serializers import PublicUserSerializer

User = get_user_model()


class InstructorBriefSerializer(PublicUserSerializer):
    class Meta(PublicUserSerializer.Meta):
        fields = ("id", "name", "avatar", "qualification")


class LessonListSerializer(serializers.ModelSerializer):
    """Lesson row for course-details and section lists.

    ``is_locked`` is computed by the view using the bulk entitlement helper, so
    rendering a 30-lesson course costs no extra queries.
    """

    is_locked = serializers.SerializerMethodField()
    is_completed = serializers.SerializerMethodField()
    duration_display = serializers.SerializerMethodField()
    quiz_id = serializers.UUIDField(source="quiz.id", read_only=True, default=None)
    has_video = serializers.SerializerMethodField()

    class Meta:
        model = Lesson
        fields = (
            "id",
            "title",
            "description",
            "ordering",
            "is_preview",
            "status",
            "duration_seconds",
            "duration_display",
            "is_locked",
            "is_completed",
            "has_video",
            "quiz_id",
        )

    def _locked_ids(self) -> set:
        return self.context.get("locked_lesson_ids") or set()

    def get_is_locked(self, obj: Lesson) -> bool:
        if obj.is_preview:
            return False
        return obj.id in self._locked_ids()

    def get_is_completed(self, obj: Lesson) -> bool:
        completed = self.context.get("completed_lesson_ids") or set()
        return obj.id in completed

    def get_duration_display(self, obj: Lesson) -> str:
        minutes, seconds = divmod(obj.duration_seconds or 0, 60)
        return f"{minutes}:{seconds:02d}"

    def get_has_video(self, obj: Lesson) -> bool:
        # Presence flag only -- never the Cloudflare id or a playback URL.
        return bool(obj.video_id)


class SectionSerializer(serializers.ModelSerializer):
    lessons = serializers.SerializerMethodField()

    class Meta:
        model = Section
        fields = ("id", "title", "description", "ordering", "is_published", "lessons")

    def get_lessons(self, obj: Section) -> list:
        lessons = getattr(obj, "visible_lessons", None)
        if lessons is None:
            lessons = obj.lessons.all()
        return LessonListSerializer(lessons, many=True, context=self.context).data


class CourseListSerializer(serializers.ModelSerializer):
    """Card representation used by ``/api/v1/courses/`` and the dashboard."""

    instructor = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role__in=["instructor", "admin"]),
        required=False,
        allow_null=True,
    )
    thumbnail_url = serializers.SerializerMethodField()
    is_accessible = serializers.SerializerMethodField()
    access_reason = serializers.SerializerMethodField()
    progress_percentage = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = (
            "id",
            "title",
            "slug",
            "subtitle",
            "summary",
            "thumbnail_url",
            "instructor",
            "price",
            "status",
            "unlock_rule",
            "level",
            "language",
            "duration_minutes",
            "lesson_count",
            "published_at",
            "is_accessible",
            "access_reason",
            "progress_percentage",
        )

    def get_thumbnail_url(self, obj: Course) -> str | None:
        if not obj.thumbnail:
            return None
        request = self.context.get("request")
        url = obj.thumbnail.url
        return request.build_absolute_uri(url) if request else url

    def get_is_accessible(self, obj: Course) -> bool:
        accessible = self.context.get("accessible_course_ids")
        if accessible is None:
            return False
        return obj.id in accessible

    def get_access_reason(self, obj: Course) -> str:
        if obj.unlock_rule == "free":
            return "free_course"
        return (
            "active_subscription"
            if self.get_is_accessible(obj)
            else "subscription_required"
        )

    def get_progress_percentage(self, obj: Course) -> float:
        progress = self.context.get("course_progress") or {}
        return progress.get(obj.id, 0.0)


class CourseDetailSerializer(CourseListSerializer):
    """Course page payload: full sections + lessons.

    Deliberately does **not** include video playback data -- see the module
    docstring.  Watching is a separate, authorized call.
    """

    sections = serializers.SerializerMethodField()
    quiz_count = serializers.SerializerMethodField()

    class Meta(CourseListSerializer.Meta):
        fields = CourseListSerializer.Meta.fields + (
            "description",
            "sections",
            "quiz_count",
            "created_at",
            "updated_at",
        )

    def get_sections(self, obj: Course) -> list:
        sections = getattr(obj, "visible_sections", None)
        if sections is None:
            sections = obj.sections.filter(is_published=True)
        return SectionSerializer(sections, many=True, context=self.context).data

    def get_quiz_count(self, obj: Course) -> int:
        return len(getattr(obj, "published_quizzes", []) or [])


class SectionWriteSerializer(serializers.ModelSerializer):
    """Instructor-facing write serializer for sections."""

    class Meta:
        model = Section
        fields = ("id", "course", "title", "description", "ordering", "is_published")
        read_only_fields = ("id",)

    def validate_ordering(self, value: int) -> int:
        if value < 1:
            raise serializers.ValidationError("Ordering must be 1 or greater.")
        return value

    def validate(self, attrs: dict) -> dict:
        course = attrs.get("course") or getattr(self.instance, "course", None)
        ordering = attrs.get("ordering", getattr(self.instance, "ordering", None))
        if course and ordering:
            clash = Section.objects.filter(course=course, ordering=ordering)
            if self.instance:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise serializers.ValidationError(
                    {
                        "ordering": "Another section in this course already uses that position."
                    }
                )
        return attrs


class LessonWriteSerializer(serializers.ModelSerializer):
    """Instructor-facing write serializer for lessons.

    ``duration_seconds`` is not client-writable: it is synced from the Cloudflare
    asset so a typo cannot desync the course total.
    """

    class Meta:
        model = Lesson
        fields = (
            "id",
            "section",
            "title",
            "description",
            "video",
            "quiz",
            "ordering",
            "is_preview",
            "status",
        )
        read_only_fields = ("id", "video")
        extra_kwargs = {
            "video": {"required": False},
            "quiz": {"required": False},
        }

    def validate(self, attrs: dict) -> dict:
        section = attrs.get("section") or getattr(self.instance, "section", None)
        ordering = attrs.get("ordering", getattr(self.instance, "ordering", None))
        if section and ordering:
            clash = Lesson.objects.filter(section=section, ordering=ordering)
            if self.instance:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise serializers.ValidationError(
                    {
                        "ordering": "Another lesson in this section already uses that position."
                    }
                )
        return attrs


class CourseWriteSerializer(serializers.ModelSerializer):
    """Instructor/admin course create + update.

    ``instructor`` is optional: it defaults to the caller (see ``create``) and is
    constrained to instructor/admin accounts.  Making it read-only would break
    admin workflows, so it is a constrained writable field instead.
    """

    instructor = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role__in=["instructor", "admin"]),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Course
        fields = (
            "id",
            "title",
            "slug",
            "subtitle",
            "description",
            "summary",
            "thumbnail",
            "instructor",
            "price",
            "status",
            "unlock_rule",
            "language",
            "level",
        )
        read_only_fields = ("id", "slug")

    def validate_price(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("Price cannot be negative.")
        return value

    def validate_thumbnail(self, value):
        if value is None:
            return value
        from apps.core.validators import validate_image_upload

        if hasattr(value, "size"):
            validate_image_upload(value)
        return value

    def validate_status(self, value: str) -> str:
        if value not in CourseStatus.values:
            raise serializers.ValidationError("Unknown course status.")
        return value

    def validate(self, attrs: dict) -> dict:
        request = self.context.get("request")
        instructor = attrs.get("instructor") or getattr(
            self.instance, "instructor", None
        )
        # An instructor may only ever author their own courses; only an admin can
        # assign someone else as the instructor of record.
        if request and instructor and not _is_admin(request.user):
            if instructor.pk != request.user.pk:
                raise serializers.ValidationError(
                    {"instructor": "You can only create courses under your own name."}
                )
        return attrs

    def create(self, validated_data: dict) -> Course:
        request = self.context.get("request")
        if request and not validated_data.get("instructor"):
            validated_data["instructor"] = request.user
        return super().create(validated_data)


def _is_admin(user) -> bool:
    return bool(user and (user.role == "admin" or user.is_staff or user.is_superuser))
