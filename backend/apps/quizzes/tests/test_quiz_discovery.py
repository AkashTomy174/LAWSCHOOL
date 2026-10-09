"""Students can find a course's quizzes, and starting one stays fully guarded.

Regression: course pages returned only ``quiz_count``, so the UI had nothing to
link to and a student could only reach a quiz by typing its URL.
"""

from __future__ import annotations

import pytest

from apps.quizzes.models import Quiz


def _course_quizzes(client, course):
    response = client.get(f"/api/v1/courses/{course.slug}/")
    assert response.status_code == 200
    return response.json()["quizzes"]


class TestDiscovery:
    def test_course_detail_lists_published_quizzes(self, auth_client, student, course, quiz):
        Quiz.objects.create(course=course, title="Draft quiz", is_published=False)
        quizzes = _course_quizzes(auth_client(student), course)
        assert [q["title"] for q in quizzes] == ["Module 1 Quiz"]
        assert set(quizzes[0]) == {
            "id", "title", "description", "pass_percentage",
            "max_attempts", "time_limit_minutes",
        }

    def test_listing_never_carries_questions_or_answers(self, api_client, course, quiz):
        body = api_client.get(f"/api/v1/courses/{course.slug}/").content.decode()
        assert "Article 32 deals with?" not in body
        assert "is_correct" not in body and "Writs" not in body

    def test_draft_course_quizzes_stay_hidden(self, auth_client, student, draft_course):
        Quiz.objects.create(course=draft_course, title="Hidden", is_published=True)
        response = auth_client(student).get(f"/api/v1/courses/{draft_course.slug}/")
        assert response.status_code == 404


class TestProgressAndResume:
    def test_reports_an_in_progress_attempt(
        self, auth_client, student, quiz, active_subscription
    ):
        client = auth_client(student)
        assert client.get(f"/api/v1/quizzes/{quiz.id}/progress/").json()["in_progress_attempt"] is None

        started = client.post(f"/api/v1/quizzes/{quiz.id}/attempts/")
        assert started.status_code == 201
        attempt_id = started.json()["attempt"]["id"]
        progress = client.get(f"/api/v1/quizzes/{quiz.id}/progress/").json()
        assert progress["in_progress_attempt"]["id"] == attempt_id

        # Starting again resumes the same attempt rather than burning a new one.
        again = client.post(f"/api/v1/quizzes/{quiz.id}/attempts/").json()
        assert again["attempt"]["id"] == attempt_id

        client.post(f"/api/v1/quiz-attempts/{attempt_id}/submit/", {"answers": {}}, format="json")
        progress = client.get(f"/api/v1/quizzes/{quiz.id}/progress/").json()
        assert progress["in_progress_attempt"] is None
        assert progress["attempts_used"] == 1

    def test_another_students_attempt_is_not_reported(
        self, auth_client, student, other_student, quiz, active_subscription
    ):
        auth_client(student).post(f"/api/v1/quizzes/{quiz.id}/attempts/")
        progress = auth_client(other_student).get(f"/api/v1/quizzes/{quiz.id}/progress/").json()
        assert progress["in_progress_attempt"] is None


class TestStartIsGuarded:
    def test_unsubscribed_student_cannot_start(self, auth_client, student, quiz):
        response = auth_client(student).post(f"/api/v1/quizzes/{quiz.id}/attempts/")
        assert response.status_code == 403

    def test_unpublished_quiz_cannot_be_started(self, auth_client, student, quiz, active_subscription):
        Quiz.objects.filter(pk=quiz.pk).update(is_published=False)
        assert auth_client(student).post(f"/api/v1/quizzes/{quiz.id}/attempts/").status_code == 404

    def test_attempt_payload_hides_the_answer_key(self, auth_client, student, quiz, active_subscription):
        body = auth_client(student).post(f"/api/v1/quizzes/{quiz.id}/attempts/").json()
        options = body["quiz"]["questions"][0]["options"]
        assert {o["text"] for o in options} == {"Writs", "Taxes"}
        assert all("is_correct" not in o for o in options)
        assert "explanation" not in str(body["quiz"]["questions"])

    def test_students_cannot_read_each_others_attempts(
        self, auth_client, student, other_student, quiz, active_subscription
    ):
        attempt_id = auth_client(student).post(f"/api/v1/quizzes/{quiz.id}/attempts/").json()["attempt"]["id"]
        other = auth_client(other_student)
        assert other.get(f"/api/v1/quiz-attempts/{attempt_id}/").status_code == 403
        assert other.post(
            f"/api/v1/quiz-attempts/{attempt_id}/submit/", {"answers": {}}, format="json"
        ).status_code == 403
