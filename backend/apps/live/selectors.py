"""Read-only queryset helpers for live classes."""

from __future__ import annotations

from apps.live.models import LiveClass


def upcoming_live_classes_for_course(course, *, published_only: bool = True):
    queryset = LiveClass.objects.filter(course=course).order_by("scheduled_start")
    if published_only:
        queryset = queryset.filter(is_published=True)
    return queryset
