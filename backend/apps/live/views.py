"""Live class API: admin/instructor CRUD, student list, and the gated join link."""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsCourseOwnerOrAdmin, is_admin
from apps.courses.models import Course
from apps.live import services
from apps.live.models import LiveClass
from apps.live.serializers import LiveClassPublicSerializer, LiveClassSerializer


class LiveClassListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/v1/live-classes/manage/?course=<slug> -- admin/instructor CRUD."""

    serializer_class = LiveClassSerializer
    permission_classes = [IsCourseOwnerOrAdmin]
    pagination_class = None

    def get_queryset(self):
        queryset = LiveClass.objects.select_related("course", "instructor").order_by(
            "scheduled_start"
        )
        course_slug = self.request.query_params.get("course")
        if course_slug:
            queryset = queryset.filter(course__slug=course_slug)
        if not is_admin(self.request):
            queryset = queryset.filter(course__instructor=self.request.user)
        return queryset

    def perform_create(self, serializer):
        self.check_object_permissions(self.request, serializer.validated_data["course"])
        serializer.save()


class LiveClassDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /api/v1/live-classes/manage/<uuid>/."""

    serializer_class = LiveClassSerializer
    permission_classes = [IsCourseOwnerOrAdmin]

    def get_queryset(self):
        queryset = LiveClass.objects.select_related("course", "instructor")
        if not is_admin(self.request):
            queryset = queryset.filter(course__instructor=self.request.user)
        return queryset

    def perform_update(self, serializer):
        # Moving a live class needs ownership of the destination course too.
        if "course" in serializer.validated_data:
            self.check_object_permissions(
                self.request, serializer.validated_data["course"]
            )
        serializer.save()


class CourseLiveClassListView(generics.ListAPIView):
    """GET /api/v1/live-classes/?course=<slug> -- student-facing list, no meeting link."""

    serializer_class = LiveClassPublicSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        course_slug = self.request.query_params.get("course")
        course = get_object_or_404(Course, slug=course_slug) if course_slug else None
        queryset = LiveClass.objects.filter(is_published=True).select_related("course")
        if course:
            queryset = queryset.filter(course=course)
        return queryset.order_by("scheduled_start")


class LiveClassJoinView(APIView):
    """GET /api/v1/live-classes/<uuid>/join/ -- the meeting link, entitlement-gated."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        live_class = get_object_or_404(
            LiveClass.objects.select_related("course"), pk=pk, is_published=True
        )
        info = services.get_live_class_join_info(request.user, live_class)
        return Response(info)
