"""AUTH4: nobody can remove the final active administrator, or demote themselves."""

import pytest

from apps.users.models import LastAdminError, User

pytestmark = pytest.mark.django_db


@pytest.fixture
def second_admin(db):
    return User.objects.create_superuser(
        email="admin2@test.local", password="Str0ng-Passphrase-9", name="Admin Two"
    )


def _patch(client, user, **data):
    return client.patch(f"/api/v1/users/{user.pk}/", data, format="json")


def test_admin_cannot_demote_self_even_with_other_admins(jwt_client, admin_user, second_admin):
    r = _patch(jwt_client(admin_user), admin_user, role="student")
    assert r.status_code == 400
    admin_user.refresh_from_db()
    assert admin_user.role == "admin"


def test_admin_can_demote_another_admin_when_two_remain(jwt_client, admin_user, second_admin):
    second_admin.is_staff = False
    second_admin.is_superuser = False
    second_admin.save()
    r = _patch(jwt_client(admin_user), second_admin, role="instructor")
    assert r.status_code == 200
    second_admin.refresh_from_db()
    assert second_admin.role == "instructor"


def test_last_admin_cannot_be_demoted_by_another_privileged_path(admin_user):
    admin_user.role = "student"
    admin_user.is_staff = False
    admin_user.is_superuser = False
    with pytest.raises(LastAdminError):
        admin_user.save()
    admin_user.refresh_from_db()
    assert admin_user.role == "admin"


def test_last_admin_cannot_be_deactivated_or_deleted(admin_user):
    admin_user.is_active = False
    with pytest.raises(LastAdminError):
        admin_user.save()
    admin_user.refresh_from_db()
    with pytest.raises(LastAdminError):
        admin_user.delete()
    assert User.objects.filter(pk=admin_user.pk).exists()


def test_admin_may_be_removed_when_another_remains(admin_user, second_admin):
    second_admin.delete()
    assert User.objects.filter(pk=admin_user.pk).exists()


def test_sequential_demotions_stop_at_one(admin_user, second_admin):
    """Models the lock ordering of two concurrent requests: the second must fail."""
    first = User.objects.get(pk=admin_user.pk)
    second = User.objects.get(pk=second_admin.pk)
    for u in (first, second):
        u.role, u.is_staff, u.is_superuser = "student", False, False
    first.save()
    with pytest.raises(LastAdminError):
        second.save()


def test_non_admin_cannot_change_roles(jwt_client, student, other_student):
    assert _patch(jwt_client(student), other_student, role="admin").status_code == 403


def test_privilege_irrelevant_saves_skip_the_guard(admin_user):
    """last_login / password saves must not be blocked or slowed by the guard."""
    admin_user.save(update_fields=["last_login"])


def test_promotion_and_normal_edits_work(jwt_client, admin_user, student):
    assert _patch(jwt_client(admin_user), student, role="instructor").status_code == 200
    assert _patch(jwt_client(admin_user), student, is_active=False).status_code == 200


def test_django_admin_bulk_delete_reports_instead_of_500(admin_client_factory=None):
    from django.contrib import admin
    from django.contrib.messages.storage.fallback import FallbackStorage
    from django.test import RequestFactory

    only = User.objects.create_superuser(
        email="solo@test.local", password="Str0ng-Passphrase-9", name="Solo"
    )
    model_admin = admin.site._registry[User]
    request = RequestFactory().post("/admin/")
    request.user = only
    request.session = {}
    request._messages = FallbackStorage(request)
    model_admin.delete_queryset(request, User.objects.filter(pk=only.pk))
    assert User.objects.filter(pk=only.pk).exists()
