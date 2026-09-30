from __future__ import annotations

from rest_framework import serializers

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
        read_only_fields = ("id",)


class LiveClassPublicSerializer(serializers.ModelSerializer):
    """Student list shape.  ``meeting_url`` is deliberately absent.

    The join link is only ever returned by the dedicated join endpoint after
    the entitlement check, so a locked student cannot scrape it from a list.
    """

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
        )
        read_only_fields = fields
