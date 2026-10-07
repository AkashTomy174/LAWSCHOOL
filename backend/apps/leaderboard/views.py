"""Leaderboard API views -- paginated, SQL-aggregated rankings."""

from __future__ import annotations

from django.core.cache import cache
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.pagination import StandardResultsSetPagination
from apps.core.permissions import IsAdminRole
from apps.leaderboard import models as lb
from apps.leaderboard.models import LeaderboardEntry, LeaderboardSnapshot
from apps.leaderboard.serializers import (
    LeaderboardEntrySerializer,
    LeaderboardSnapshotSerializer,
    MyRankSerializer,
)

# The global top-N changes slowly; caching it for a minute removes almost all
# database load from a page every student checks.
_CACHE_TTL = 60


def _my_standing(user) -> dict:
    """The caller's rank + scores; shared so every endpoint agrees on the numbers."""
    entry = getattr(user, "leaderboard_entry", None)
    total_students = LeaderboardEntry.objects.filter(
        user__role="student", user__is_active=True
    ).count()
    rank = lb.user_rank(user)
    return {
        "rank": rank,
        "total_score": entry.total_score if entry else 0,
        "quiz_score": entry.quiz_score if entry else 0,
        "lessons_completed": entry.lessons_completed if entry else 0,
        "courses_completed": entry.courses_completed if entry else 0,
        # Share of students ranked below the caller.
        "percentile": (
            round(((total_students - rank) / total_students) * 100, 2)
            if rank and total_students
            else None
        ),
    }


class LeaderboardView(generics.ListAPIView):
    """GET /api/v1/leaderboard/ -- paginated global ranking.

    The queryset is the denormalised ``LeaderboardEntry`` table ordered by indexed
    columns, so page N costs one indexed query plus one join to the user -- no
    aggregation over the attempt/progress tables happens at request time.
    """

    serializer_class = LeaderboardEntrySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    # The global DEFAULT_FILTER_BACKENDS include DRF's OrderingFilter, which would
    # silently re-sort this queryset ascending by whatever ``?ordering=`` value the
    # client sent (``quiz_score`` has no leading dash).  Ranking order is a domain
    # rule, not a client choice, so it is handled in ``get_queryset`` instead.
    filter_backends = []

    def get_queryset(self):
        queryset = LeaderboardEntry.objects.select_related("user").filter(
            user__is_active=True, user__role="student"
        )

        # Sort options map only onto indexed columns.  The attempt/progress tables
        # are never touched here -- the denormalised entry table is what keeps this
        # an O(page) query rather than an aggregate over the largest tables.
        sort_key = self.request.query_params.get("ordering")
        orderings = {
            "total_score": ("-total_score", "-lessons_completed", "-courses_completed"),
            "quiz_score": ("-quiz_score", "-total_score"),
            "lessons": ("-lessons_completed", "-total_score"),
            "courses": ("-courses_completed", "-total_score"),
            "name": ("user__name",),
        }
        order_by = orderings.get(sort_key, orderings["total_score"])
        return queryset.order_by(*order_by, "user__date_joined")

    def list(self, request, *args, **kwargs):
        # My rank is computed with COUNT queries, not by scanning the table.
        page_response = super().list(request, *args, **kwargs)
        page_response.data["me"] = _my_standing(request.user)
        return page_response


class LeaderboardTopView(APIView):
    """GET /api/v1/leaderboard/top/ -- cached top-N for the dashboard widget."""

    permission_classes = [IsAuthenticatedOrReadOnly]

    def get(self, request):
        try:
            limit = int(request.query_params.get("limit", 10))
        except ValueError:
            limit = 10
        # Clamped both ways: a negative slice raises inside the ORM (HTTP 500).
        limit = max(1, min(limit, 50))
        cache_key = f"leaderboard:top:{limit}"
        cached = cache.get(cache_key)
        if cached is None:
            cached = LeaderboardEntrySerializer(
                lb.top_entries(limit=limit), many=True, context={"request": request}
            ).data
            cache.set(cache_key, cached, _CACHE_TTL)
        return Response({"results": cached, "me": {"rank": lb.user_rank(request.user)}})


class MyRankView(APIView):
    """GET /api/v1/leaderboard/me/ -- the caller's own standing."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: MyRankSerializer})
    def get(self, request):
        return Response(_my_standing(request.user))


class LeaderboardSnapshotView(generics.ListAPIView):
    """GET /api/v1/leaderboard/snapshots/ -- historical top-N captures."""

    serializer_class = LeaderboardSnapshotSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        queryset = LeaderboardSnapshot.objects.all()
        if scope := self.request.query_params.get("scope"):
            queryset = queryset.filter(scope=scope)
        return queryset[:12]


class RecalculateLeaderboardView(APIView):
    """POST /api/v1/leaderboard/recalculate/ -- admin on-demand rebuild.

    Normally run by Celery beat; exposed so an admin can force a refresh after
    importing historical data.  Runs synchronously *only* because it is an
    explicit, rare admin action.
    """

    permission_classes = [IsAdminRole]

    def post(self, request):
        from apps.leaderboard.models import recalculate_leaderboard

        count = recalculate_leaderboard()
        cache.delete_many([f"leaderboard:top:{n}" for n in range(1, 51)])
        return Response({"detail": f"Recalculated {count} ranking rows."})
