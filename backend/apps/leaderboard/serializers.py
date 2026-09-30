"""Leaderboard serializers."""

from __future__ import annotations

from rest_framework import serializers

from apps.leaderboard.models import LeaderboardEntry, LeaderboardSnapshot


class LeaderboardEntrySerializer(serializers.ModelSerializer):
    """Public ranking row.

    Only display fields are exposed.  Email addresses and ids of *other* students
    are reduced to a display name + UUID so the leaderboard is not a data leak.
    """

    user_id = serializers.UUIDField(source="user.id", read_only=True)
    name = serializers.SerializerMethodField()
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = LeaderboardEntry
        fields = (
            "rank",
            "user_id",
            "name",
            "avatar_url",
            "total_score",
            "quiz_score",
            "quizzes_passed",
            "lessons_completed",
            "courses_completed",
            "last_activity_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_name(self, obj: LeaderboardEntry) -> str:
        return obj.user.get_full_name()

    def get_avatar_url(self, obj: LeaderboardEntry) -> str | None:
        if not obj.user.avatar:
            return None
        request = self.context.get("request")
        url = obj.user.avatar.url
        return request.build_absolute_uri(url) if request else url


class LeaderboardSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaderboardSnapshot
        fields = ("id", "scope", "captured_at", "entries")
        read_only_fields = fields


class MyRankSerializer(serializers.Serializer):
    """The caller's own position, returned alongside the top-N page."""

    rank = serializers.IntegerField(allow_null=True)
    total_score = serializers.IntegerField()
    quiz_score = serializers.IntegerField()
    lessons_completed = serializers.IntegerField()
    courses_completed = serializers.IntegerField()
    percentile = serializers.FloatField(allow_null=True)
