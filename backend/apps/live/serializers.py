from __future__ import annotations

from django.utils import timezone
from rest_framework import serializers

from apps.live import services
from apps.live.models import LiveClass


class LiveClassSerializer(serializers.ModelSerializer):
    """Admin/instructor CRUD shape -- includes the meeting link."""

    class Meta:
        model = LiveClass
        fields = (
            "id",
            "course",
            "title",
            "description",
            "scheduled_start",
            "duration_minutes",
            "meeting_provider",
            "meeting_url",
            "instructor",
            "is_published",
        )
        # Derived from the course on save (see LiveClass.save).
        read_only_fields = ("id", "instructor")


class LiveClassPublicSerializer(serializers.ModelSerializer):
    """Student list shape.  ``meeting_url`` is deliberately absent.

    The join link is only ever returned by the dedicated join endpoint after
    the entitlement check, so a locked student cannot scrape it from a list.
    """

    course_title = serializers.CharField(source="course.title", read_only=True)
    course_slug = serializers.CharField(source="course.slug", read_only=True)
    instructor_name = serializers.CharField(
        source="instructor.name", read_only=True, default=""
    )
    ends_at = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    can_join = serializers.SerializerMethodField()

    class Meta:
        model = LiveClass
        fields = (
            "id",
            "course",
            "course_title",
            "course_slug",
            "instructor_name",
            "title",
            "description",
            "scheduled_start",
            "duration_minutes",
            "ends_at",
            "meeting_provider",
            "status",
            "can_join",
        )
        read_only_fields = fields

    # Status uses one server timestamp per response so rows cannot disagree.
    def _now(self):
        return self.context.setdefault("now", timezone.now())

    def get_ends_at(self, obj):
        return serializers.DateTimeField().to_representation(services.class_end(obj))

    def get_status(self, obj) -> str:
        return services.class_status(obj, self._now())

    def get_can_join(self, obj) -> bool:
        return services.can_join_now(obj, self._now())
