"""Admins can deactivate accounts; nobody can grant privileges through the API.

Regression: ``AdminUserSerializer`` documented "activation state" but did not
expose ``is_active``, so the admin API could not deactivate an account.
"""

from __future__ import annotations

import pytest

from apps.users.models import User


def _login(client, email, password):
    return client.post("/api/v1/auth/login/", {"email": email, "password": password}, format="json")


def _refresh_of(body):
    return body.get("refresh") or body["tokens"]["refresh"]


class TestDeactivation:
    def test_admin_deactivates_and_existing_sessions_end(self, api_client, auth_client, admin_user, student):
        refresh = _refresh_of(_login(api_client, student.email, "StudentPass123!").json())

        response = auth_client(admin_user).patch(
            f"/api/v1/users/{student.pk}/", {"is_active": False}, format="json"
        )
        assert response.status_code == 200, response.data
        assert response.json()["is_active"] is False

        assert _login(api_client, student.email, "StudentPass123!").status_code in (400, 401)
        assert api_client.post("/api/v1/auth/refresh/", {"refresh": refresh}, format="json").status_code == 401

    def test_admin_can_reactivate(self, api_client, auth_client, admin_user, student):
        User.objects.filter(pk=student.pk).update(is_active=False)
        response = auth_client(admin_user).patch(
            f"/api/v1/users/{student.pk}/", {"is_active": True}, format="json"
        )
        assert response.status_code == 200
        assert _login(api_client, student.email, "StudentPass123!").status_code == 200

    def test_admin_cannot_deactivate_themselves(self, auth_client, admin_user):
        response = auth_client(admin_user).patch(
            f"/api/v1/users/{admin_user.pk}/", {"is_active": False}, format="json"
        )
        assert response.status_code == 400
        admin_user.refresh_from_db()
        assert admin_user.is_active

    @pytest.mark.parametrize("who", ["student", "instructor"])
    def test_non_admins_cannot_deactivate(self, request, auth_client, who, other_student):
        response = auth_client(request.getfixturevalue(who)).patch(
            f"/api/v1/users/{other_student.pk}/", {"is_active": False}, format="json"
        )
        assert response.status_code == 403
        other_student.refresh_from_db()
        assert other_student.is_active


class TestNoPrivilegeEscalation:
    def test_profile_update_ignores_privilege_fields(self, auth_client, student):
        auth_client(student).patch(
            "/api/v1/auth/me/",
            {"role": "admin", "is_staff": True, "is_superuser": True, "is_active": False},
            format="json",
        )
        student.refresh_from_db()
        assert student.role == "student"
        assert not student.is_staff and not student.is_superuser and student.is_active

    def test_admin_api_cannot_grant_django_staff_or_superuser(self, auth_client, admin_user, student):
        """``is_staff`` makes a user a full platform admin (``is_admin``), so it is
        only grantable from the Django admin by a superuser, never via the API."""
        auth_client(admin_user).patch(
            f"/api/v1/users/{student.pk}/", {"is_staff": True, "is_superuser": True}, format="json"
        )
        student.refresh_from_db()
        assert not student.is_staff and not student.is_superuser
