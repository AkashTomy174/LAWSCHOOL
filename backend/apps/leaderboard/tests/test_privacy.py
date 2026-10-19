"""AUTH3: the leaderboard is for signed-in users and never leaks contact details."""

import pytest

from apps.leaderboard.models import LeaderboardEntry, refresh_user_leaderboard

pytestmark = pytest.mark.django_db

ENTRY_FIELDS = {
    "rank", "user_id", "name", "avatar_url", "total_score", "quiz_score",
    "quizzes_passed", "lessons_completed", "courses_completed",
    "last_activity_at", "updated_at",
}


@pytest.fixture
def ranked(student):
    student.phone = "+919999900000"
    student.save()
    LeaderboardEntry.objects.update_or_create(user=student, defaults={"total_score": 10})
    return student


@pytest.mark.parametrize("path", ["/api/v1/leaderboard/top/", "/api/v1/leaderboard/", "/api/v1/leaderboard/me/"])
def test_anonymous_is_rejected(api_client, ranked, path):
    assert api_client.get(path).status_code in (401, 403)


@pytest.mark.parametrize("role", ["student", "instructor", "admin_user"])
def test_signed_in_roles_can_read(request, jwt_client, ranked, role):
    user = request.getfixturevalue(role)
    assert jwt_client(user).get("/api/v1/leaderboard/top/").status_code == 200


def test_response_field_allowlist_and_no_contact_data(jwt_client, ranked, other_student):
    response = jwt_client(other_student).get("/api/v1/leaderboard/top/")
    rows = response.data["results"]
    assert rows and all(set(row) == ENTRY_FIELDS for row in rows)
    text = str(response.data)
    assert ranked.email not in text and "9999900000" not in text


def test_blank_name_never_falls_back_to_email(jwt_client, ranked, other_student):
    ranked.name = ""
    ranked.save()
    text = str(jwt_client(other_student).get("/api/v1/leaderboard/").data)
    assert ranked.email not in text


def test_cached_response_not_served_to_anonymous(api_client, jwt_client, ranked, student):
    assert jwt_client(student).get("/api/v1/leaderboard/top/").status_code == 200  # warms cache
    assert api_client.get("/api/v1/leaderboard/top/").status_code in (401, 403)
