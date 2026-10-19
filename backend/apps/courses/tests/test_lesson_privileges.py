"""AUTH1: free-preview is admin-only; publishing stays an instructor workflow."""

import pytest

pytestmark = pytest.mark.django_db


def _create(section, quiz, **extra):
    return {
        "section": str(section.pk),
        "title": "L",
        "ordering": 9,
        "quiz": str(quiz.pk),
        "status": "draft",
        **extra,
    }


def test_instructor_cannot_create_preview_lesson(auth_client, instructor, section, quiz):
    r = auth_client(instructor).post(
        "/api/v1/lessons/", _create(section, quiz, is_preview=True), format="json"
    )
    assert r.status_code == 400 and "is_preview" in str(r.json())


def test_instructor_cannot_flip_existing_lesson_to_preview(auth_client, instructor, lesson):
    r = auth_client(instructor).patch(
        f"/api/v1/lessons/{lesson.pk}/", {"is_preview": True}, format="json"
    )
    assert r.status_code == 400
    lesson.refresh_from_db()
    assert lesson.is_preview is False


def test_instructor_put_with_unchanged_preview_flag_is_fine(auth_client, instructor, lesson):
    r = auth_client(instructor).patch(
        f"/api/v1/lessons/{lesson.pk}/", {"is_preview": False, "title": "Renamed"}, format="json"
    )
    assert r.status_code == 200


def test_instructor_cannot_remove_preview_set_by_admin(auth_client, instructor, preview_lesson):
    r = auth_client(instructor).patch(
        f"/api/v1/lessons/{preview_lesson.pk}/", {"is_preview": False}, format="json"
    )
    assert r.status_code == 400


def test_instructor_can_still_publish_and_edit_own_lesson(auth_client, instructor, lesson):
    client = auth_client(instructor)
    assert client.patch(f"/api/v1/lessons/{lesson.pk}/", {"status": "published"}, format="json").status_code == 200
    assert client.patch(f"/api/v1/lessons/{lesson.pk}/", {"status": "draft", "title": "x"}, format="json").status_code == 200


def test_admin_can_set_preview(auth_client, admin_user, lesson):
    r = auth_client(admin_user).patch(
        f"/api/v1/lessons/{lesson.pk}/", {"is_preview": True}, format="json"
    )
    assert r.status_code == 200
    lesson.refresh_from_db()
    assert lesson.is_preview is True


def test_other_instructor_cannot_touch_lesson(auth_client, lesson, db):
    from apps.users.models import User

    other = User.objects.create_instructor(email="other-inst@test.local", password="Str0ng-Passphrase-9", name="O")
    r = auth_client(other).patch(f"/api/v1/lessons/{lesson.pk}/", {"status": "draft"}, format="json")
    assert r.status_code == 404


def test_student_cannot_write_lessons(auth_client, student, lesson):
    r = auth_client(student).patch(f"/api/v1/lessons/{lesson.pk}/", {"is_preview": True}, format="json")
    assert r.status_code == 403
