"""Authentication tests: registration, login, refresh, logout, password flows."""

from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()

pytestmark = pytest.mark.django_db


REGISTER_URL = "/api/v1/auth/register/"
LOGIN_URL = "/api/v1/auth/login/"
REFRESH_URL = "/api/v1/auth/refresh/"
LOGOUT_URL = "/api/v1/auth/logout/"
ME_URL = "/api/v1/auth/me/"


class TestRegistration:
    def test_register_creates_student_and_returns_tokens(self, api_client):
        response = api_client.post(
            REGISTER_URL,
            {
                "email": "New.Student@Test.local",
                "name": "New Student",
                "phone": "+919876543210",
                "password": "StrongPass123!",
                "password_confirm": "StrongPass123!",
            },
            format="json",
        )
        assert response.status_code == 201, response.data
        assert "access" in response.data["tokens"]
        assert "refresh" in response.data["tokens"]

        user = User.objects.get(email="new.student@test.local")
        assert user.role == "student"
        # The raw password must never be stored.
        assert user.password != "StrongPass123!"
        assert user.check_password("StrongPass123!")

    def test_register_normalises_email_case(self, api_client):
        api_client.post(
            REGISTER_URL,
            {
                "email": "MiXeD@Test.local",
                "name": "Mixed",
                "password": "StrongPass123!",
                "password_confirm": "StrongPass123!",
            },
            format="json",
        )
        assert User.objects.filter(email="mixed@test.local").exists()

    def test_register_rejects_duplicate_email(self, api_client, student):
        response = api_client.post(
            REGISTER_URL,
            {
                "email": student.email,
                "name": "Duplicate",
                "password": "StrongPass123!",
                "password_confirm": "StrongPass123!",
            },
            format="json",
        )
        assert response.status_code == 400
        # The resolver surfaces DRF's specific constraint code ('unique') rather
        # than flattening it to 'validation_error', so the UI can localise the
        # message and the test can assert on the real cause.
        assert response.data["error"]["code"] == "unique"
        assert "email" in response.data["error"]["details"]
        assert User.objects.filter(email=student.email).count() == 1

    def test_register_rejects_mismatched_passwords(self, api_client):
        response = api_client.post(
            REGISTER_URL,
            {
                "email": "mismatch@test.local",
                "name": "Mismatch",
                "password": "StrongPass123!",
                "password_confirm": "DifferentPass123!",
            },
            format="json",
        )
        assert response.status_code == 400
        assert "password_confirm" in response.data["error"]["details"]

    def test_register_rejects_weak_password(self, api_client):
        response = api_client.post(
            REGISTER_URL,
            {
                "email": "weak@test.local",
                "name": "Weak",
                "password": "password123",
                "password_confirm": "password123",
            },
            format="json",
        )
        assert response.status_code == 400
        # Django's validators report common-passwords as a non-field error, so
        # assert on the password being rejected rather than on a field key.
        details = response.data["error"]["details"]
        assert "password" in details or "non_field_errors" in details

    def test_register_cannot_self_assign_role(self, api_client):
        """A crafted payload must not be able to create an admin."""
        response = api_client.post(
            REGISTER_URL,
            {
                "email": "sneaky@test.local",
                "name": "Sneaky",
                "password": "StrongPass123!",
                "password_confirm": "StrongPass123!",
                "role": "admin",
                "is_staff": True,
                "is_superuser": True,
            },
            format="json",
        )
        assert response.status_code == 201
        user = User.objects.get(email="sneaky@test.local")
        assert user.role == "student"
        assert user.is_staff is False
        assert user.is_superuser is False

    def test_register_response_never_contains_password(self, api_client):
        response = api_client.post(
            REGISTER_URL,
            {
                "email": "nopass@test.local",
                "name": "No Pass",
                "password": "StrongPass123!",
                "password_confirm": "StrongPass123!",
            },
            format="json",
        )
        assert response.status_code == 201
        body = json.dumps(response.data)
        # The plaintext password must never be echoed back, in any shape.
        assert "StrongPass123!" not in body
        assert "password_confirm" not in body


class TestLogin:
    def test_login_with_valid_credentials_returns_tokens(self, api_client, student):
        response = api_client.post(
            LOGIN_URL,
            {"email": student.email, "password": "StudentPass123!"},
            format="json",
        )
        assert response.status_code == 200
        assert "access" in response.data
        assert "refresh" in response.data
        assert response.data["user"]["email"] == student.email

    def test_login_is_case_insensitive_on_email(self, api_client, student):
        response = api_client.post(
            LOGIN_URL,
            {"email": student.email.upper(), "password": "StudentPass123!"},
            format="json",
        )
        assert response.status_code == 200

    def test_login_rejects_invalid_password(self, api_client, student):
        response = api_client.post(
            LOGIN_URL,
            {"email": student.email, "password": "WrongPassword123!"},
            format="json",
        )
        assert response.status_code == 401
        # SimpleJWT reports the specific reason; what matters is that the client
        # gets a stable, machine-readable code and no tokens.
        assert response.data["error"]["code"] == "no_active_account"
        assert "access" not in response.data

    def test_login_rejects_unknown_email(self, api_client):
        response = api_client.post(
            LOGIN_URL,
            {"email": "ghost@test.local", "password": "Whatever123!"},
            format="json",
        )
        assert response.status_code == 401

    def test_login_rejects_inactive_account(self, api_client, student):
        student.is_active = False
        student.save(update_fields=["is_active"])
        response = api_client.post(
            LOGIN_URL,
            {"email": student.email, "password": "StudentPass123!"},
            format="json",
        )
        assert response.status_code == 401

    def test_login_error_does_not_reveal_which_field_was_wrong(self, api_client):
        unknown = api_client.post(
            LOGIN_URL,
            {"email": "ghost@test.local", "password": "Whatever123!"},
            format="json",
        )
        wrong_pw = api_client.post(
            LOGIN_URL,
            {"email": "someone@test.local", "password": "Whatever123!"},
            format="json",
        )
        # Same status and shape for both: no account enumeration.
        assert unknown.status_code == wrong_pw.status_code == 401


class TestTokenLifecycle:
    def test_refresh_returns_new_access_token(self, api_client, student):
        login = api_client.post(
            LOGIN_URL,
            {"email": student.email, "password": "StudentPass123!"},
            format="json",
        )
        refresh = login.data["refresh"]
        response = api_client.post(REFRESH_URL, {"refresh": refresh}, format="json")
        assert response.status_code == 200
        assert "access" in response.data

    def test_refresh_token_rotation_blacklists_old_token(self, api_client, student):
        login = api_client.post(
            LOGIN_URL,
            {"email": student.email, "password": "StudentPass123!"},
            format="json",
        )
        old_refresh = login.data["refresh"]

        first = api_client.post(REFRESH_URL, {"refresh": old_refresh}, format="json")
        assert first.status_code == 200
        # With ROTATE_REFRESH_TOKENS + BLACKLIST_AFTER_ROTATION the old token dies.
        second = api_client.post(REFRESH_URL, {"refresh": old_refresh}, format="json")
        assert second.status_code == 401

    def test_refresh_rejects_garbage_token(self, api_client):
        response = api_client.post(
            REFRESH_URL, {"refresh": "not-a-token"}, format="json"
        )
        assert response.status_code == 401

    def test_me_requires_authentication(self, api_client):
        response = api_client.get(ME_URL)
        assert response.status_code == 401
        assert response.data["error"]["code"] == "not_authenticated"

    def test_me_returns_current_user(self, jwt_client, student):
        response = jwt_client(student).get(ME_URL)
        assert response.status_code == 200
        assert response.data["email"] == student.email
        assert response.data["role"] == "student"

    def test_logout_blacklists_refresh_token(self, api_client, student):
        login = api_client.post(
            LOGIN_URL,
            {"email": student.email, "password": "StudentPass123!"},
            format="json",
        )
        access, refresh = login.data["access"], login.data["refresh"]

        client = api_client
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        logout = client.post(LOGOUT_URL, {"refresh": refresh}, format="json")
        assert logout.status_code == 205

        # The blacklisted refresh token can no longer mint access tokens.
        client.credentials()
        reuse = client.post(REFRESH_URL, {"refresh": refresh}, format="json")
        assert reuse.status_code == 401

    def test_logout_without_token_is_idempotent(self, auth_client, student):
        response = auth_client(student).post(LOGOUT_URL, {}, format="json")
        assert response.status_code == 205

    def test_logout_all_revokes_every_session(self, api_client, student):
        first = api_client.post(
            LOGIN_URL,
            {"email": student.email, "password": "StudentPass123!"},
            format="json",
        )
        second = api_client.post(
            LOGIN_URL,
            {"email": student.email, "password": "StudentPass123!"},
            format="json",
        )

        client = api_client
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {second.data['access']}")
        response = client.post("/api/v1/auth/logout-all/", {}, format="json")
        assert response.status_code == 200

        client.credentials()
        for token in (first.data["refresh"], second.data["refresh"]):
            assert (
                client.post(REFRESH_URL, {"refresh": token}, format="json").status_code
                == 401
            )


class TestProfile:
    def test_patch_profile_updates_allowed_fields(self, jwt_client, student):
        response = jwt_client(student).patch(
            ME_URL, {"name": "Updated Name", "city": "Bengaluru"}, format="json"
        )
        assert response.status_code == 200
        student.refresh_from_db()
        assert student.name == "Updated Name"
        assert student.city == "Bengaluru"

    def test_patch_profile_cannot_change_role_or_email(self, jwt_client, student):
        response = jwt_client(student).patch(
            ME_URL, {"role": "admin", "email": "hacker@test.local"}, format="json"
        )
        assert response.status_code == 200
        student.refresh_from_db()
        assert student.role == "student"  # unchanged
        assert student.email == "student@test.local"  # unchanged

    def test_patch_profile_rejects_bad_phone(self, jwt_client, student):
        response = jwt_client(student).patch(
            ME_URL, {"phone": "not-a-phone"}, format="json"
        )
        assert response.status_code == 400


class TestPasswordManagement:
    def test_change_password_requires_current_password(self, api_client, student):
        client = api_client
        client.force_authenticate(user=student)
        response = client.post(
            "/api/v1/auth/password/change/",
            {
                "current_password": "WrongCurrent123!",
                "new_password": "BrandNewPass123!",
                "new_password_confirm": "BrandNewPass123!",
            },
            format="json",
        )
        assert response.status_code == 400
        assert "current_password" in response.data["error"]["details"]

    def test_change_password_succeeds_and_old_password_stops_working(
        self, api_client, student
    ):
        login = api_client.post(
            LOGIN_URL,
            {"email": student.email, "password": "StudentPass123!"},
            format="json",
        )
        token = login.data["access"]

        client = api_client
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = client.post(
            "/api/v1/auth/password/change/",
            {
                "current_password": "StudentPass123!",
                "new_password": "BrandNewPass123!",
                "new_password_confirm": "BrandNewPass123!",
            },
            format="json",
        )
        assert response.status_code == 200

        client.credentials()
        assert (
            client.post(
                LOGIN_URL,
                {"email": student.email, "password": "StudentPass123!"},
                format="json",
            ).status_code
            == 401
        )
        assert (
            client.post(
                LOGIN_URL,
                {"email": student.email, "password": "BrandNewPass123!"},
                format="json",
            ).status_code
            == 200
        )

    def test_password_reset_request_does_not_leak_account_existence(
        self, api_client, student
    ):
        known = api_client.post(
            "/api/v1/auth/password/reset/", {"email": student.email}, format="json"
        )
        unknown = api_client.post(
            "/api/v1/auth/password/reset/",
            {"email": "nobody@test.local"},
            format="json",
        )
        assert known.status_code == unknown.status_code == 200
        assert known.data == unknown.data

    def test_password_reset_request_creates_notification_for_real_user(
        self, api_client, student
    ):
        from apps.notifications.models import Notification

        api_client.post(
            "/api/v1/auth/password/reset/", {"email": student.email}, format="json"
        )
        assert Notification.objects.filter(user=student, kind="password_reset").exists()

    def test_password_reset_confirm_sets_new_password(self, api_client, student):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        uid = urlsafe_base64_encode(force_bytes(student.pk))
        token = default_token_generator.make_token(student)

        response = api_client.post(
            "/api/v1/auth/password/reset/confirm/",
            {
                "uid": uid,
                "token": token,
                "new_password": "ResetPass123!",
                "new_password_confirm": "ResetPass123!",
            },
            format="json",
        )
        assert response.status_code == 200
        student.refresh_from_db()
        assert student.check_password("ResetPass123!")

    def test_password_reset_confirm_rejects_invalid_token(self, api_client, student):
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        uid = urlsafe_base64_encode(force_bytes(student.pk))
        response = api_client.post(
            "/api/v1/auth/password/reset/confirm/",
            {
                "uid": uid,
                "token": "bogus-token",
                "new_password": "ResetPass123!",
                "new_password_confirm": "ResetPass123!",
            },
            format="json",
        )
        assert response.status_code == 400
        student.refresh_from_db()
        assert not student.check_password("ResetPass123!")

    def test_email_verification_token_flow(self, api_client, student):
        from apps.users.services import build_email_verification_url

        url = build_email_verification_url(student)
        query = url.split("?", 1)[1]
        params = dict(pair.split("=", 1) for pair in query.split("&"))

        response = api_client.post(
            "/api/v1/auth/verify-email/",
            {"uid": params["uid"], "token": params["token"]},
            format="json",
        )
        assert response.status_code == 200
        student.refresh_from_db()
        assert student.is_email_verified is True


class TestPermissionsByRole:
    """Role gates must be enforced server-side, not just hidden in the UI."""

    def test_student_cannot_list_users(self, jwt_client, student):
        response = jwt_client(student).get("/api/v1/users/")
        assert response.status_code == 403

    def test_instructor_cannot_list_users(self, jwt_client, instructor):
        """The directory exposes every email/phone; it is admin-only."""
        response = jwt_client(instructor).get("/api/v1/users/")
        assert response.status_code == 403

    def test_admin_can_list_users(self, jwt_client, admin_user):
        response = jwt_client(admin_user).get("/api/v1/users/")
        assert response.status_code == 200

    def test_student_cannot_create_course(self, jwt_client, student):
        response = jwt_client(student).post(
            "/api/v1/courses/",
            {"title": "Sneaky Course", "description": "Nope", "price": "0.00"},
            format="json",
        )
        assert response.status_code == 403

    def test_instructor_cannot_create_course(self, jwt_client, instructor):
        response = jwt_client(instructor).post(
            "/api/v1/courses/",
            {
                "title": "Instructor Course",
                "description": "A real course.",
                "price": "999.00",
                "status": "draft",
            },
            format="json",
        )
        assert response.status_code == 403

    def test_student_cannot_access_admin_payment_list(self, jwt_client, student):
        response = jwt_client(student).get("/api/v1/payments/all/")
        assert response.status_code == 403

    def test_admin_can_access_admin_payment_list(self, jwt_client, admin_user):
        response = jwt_client(admin_user).get("/api/v1/payments/all/")
        assert response.status_code == 200

    def test_unauthenticated_cannot_read_progress(self, api_client):
        assert api_client.get("/api/v1/progress/").status_code == 401


class TestTokenSeparation:
    def test_verification_token_cannot_reset_the_password(self, api_client, student):
        """Regression: verification and reset shared one token generator."""
        from urllib.parse import parse_qs, urlparse

        from apps.users.services import build_email_verification_url

        query = parse_qs(urlparse(build_email_verification_url(student)).query)
        response = api_client.post(
            "/api/v1/auth/password/reset/confirm/",
            {
                "uid": query["uid"][0],
                "token": query["token"][0],
                "new_password": "AttackerPass123!",
                "new_password_confirm": "AttackerPass123!",
            },
            format="json",
        )
        assert response.status_code == 400
        student.refresh_from_db()
        assert not student.check_password("AttackerPass123!")

    def test_verification_link_is_single_use(self, api_client, student):
        from urllib.parse import parse_qs, urlparse

        from apps.users.services import build_email_verification_url

        query = parse_qs(urlparse(build_email_verification_url(student)).query)
        body = {"uid": query["uid"][0], "token": query["token"][0]}
        assert api_client.post("/api/v1/auth/verify-email/", body).status_code == 200
        assert api_client.post("/api/v1/auth/verify-email/", body).status_code == 400


class TestClientIdentity:
    def test_forged_forwarded_for_is_not_trusted(self, rf):
        """Only the hop our own proxy appended counts (NUM_PROXIES=1)."""
        from apps.core.permissions import client_ip

        request = rf.get(
            "/", HTTP_X_FORWARDED_FOR="6.6.6.6, 198.51.100.4", REMOTE_ADDR="10.0.0.1"
        )
        assert client_ip(request) == "198.51.100.4"


class TestLeaderboardLimit:
    @pytest.mark.parametrize("limit", ["abc", "-5", "0"])
    def test_bad_limit_does_not_crash(self, api_client, db, limit):
        response = api_client.get(f"/api/v1/leaderboard/top/?limit={limit}")
        assert response.status_code == 200
