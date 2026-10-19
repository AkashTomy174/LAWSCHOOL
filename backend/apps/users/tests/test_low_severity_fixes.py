"""L1 (registration), L2 (logout), L4 (reset-link expiry), L5 (token claims)."""

from datetime import timedelta

import jwt
import pytest
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.db import IntegrityError
from freezegun import freeze_time
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users import services
from apps.users.models import User

pytestmark = pytest.mark.django_db

REGISTER = "/api/v1/auth/register/"
LOGOUT = "/api/v1/auth/logout/"
RESET = "/api/v1/auth/password/reset/"
CONFIRM = "/api/v1/auth/password/reset/confirm/"
LOGIN = "/api/v1/auth/login/"
PW = "Str0ng-Passphrase-9"


def _reg(email):
    return {"email": email, "name": "N", "password": PW, "password_confirm": PW}


class TestRegistrationAntiEnumeration:
    def test_new_and_existing_emails_are_indistinguishable(self, api_client, student):
        new = api_client.post(REGISTER, _reg("fresh@test.local"), format="json")
        old = api_client.post(REGISTER, _reg(student.email), format="json")
        assert (new.status_code, new.data) == (old.status_code, old.data)

    def test_existing_email_case_variant_is_also_neutral(self, api_client, student):
        r = api_client.post(REGISTER, _reg(student.email.upper()), format="json")
        assert r.status_code == 202 and User.objects.filter(email=student.email).count() == 1

    def test_validation_errors_do_not_depend_on_existence(self, api_client, student):
        weak = {**_reg(student.email), "password": "123", "password_confirm": "123"}
        a = api_client.post(REGISTER, weak, format="json")
        b = api_client.post(REGISTER, {**weak, "email": "nobody@test.local"}, format="json")
        assert a.status_code == b.status_code == 400
        assert a.data["error"]["details"].keys() == b.data["error"]["details"].keys()

    def test_new_registration_still_queues_verification_and_allows_login(self, api_client):
        api_client.post(REGISTER, _reg("onboard@test.local"), format="json")
        from apps.notifications.models import Notification

        assert Notification.objects.filter(
            user__email="onboard@test.local", kind="account_verification"
        ).exists()
        login = api_client.post(LOGIN, {"email": "onboard@test.local", "password": PW}, format="json")
        assert login.status_code == 200

    def test_existing_owner_is_sent_a_reset_email(self, api_client, student):
        from apps.notifications.models import Notification

        api_client.post(REGISTER, _reg(student.email), format="json")
        assert Notification.objects.filter(user=student, kind="password_reset").exists()

    def test_concurrent_duplicate_registration_is_handled(self, api_client, monkeypatch):
        """The other request wins the unique-constraint race between check and insert."""
        def lose_race(**kw):
            User.objects.create_user(email=kw["email"], password="Other-Passphrase-9", name="Winner")
            raise IntegrityError("duplicate key value violates unique constraint (email)")

        monkeypatch.setattr(services, "create_student", lose_race)
        # Make the pre-check miss, as it would for the loser of the race.
        calls = {"n": 0}
        real_filter = User.objects.filter

        def flaky_filter(*a, **kw):
            qs = real_filter(*a, **kw)
            calls["n"] += 1
            return qs.none() if calls["n"] == 1 else qs

        monkeypatch.setattr(User.objects, "filter", flaky_filter)
        r = api_client.post(REGISTER, _reg("race@test.local"), format="json")
        assert r.status_code == 202
        assert real_filter(email="race@test.local").count() == 1

    def test_unrelated_integrity_error_is_not_swallowed(self, api_client, monkeypatch):
        def broken(**kw):
            raise IntegrityError("some other constraint")

        monkeypatch.setattr(services, "create_student", broken)
        with pytest.raises(IntegrityError):
            api_client.post(REGISTER, _reg("broken@test.local"), format="json")
        assert not User.objects.filter(email="broken@test.local").exists()

    def test_password_reset_response_is_still_neutral(self, api_client, student):
        a = api_client.post(RESET, {"email": student.email}, format="json")
        b = api_client.post(RESET, {"email": "ghost@test.local"}, format="json")
        assert (a.status_code, a.data) == (b.status_code, b.data)


class TestLogoutOwnership:
    def _tokens(self, user):
        refresh = RefreshToken.for_user(user)
        return str(refresh), refresh["jti"]

    def _blacklisted(self, jti):
        from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken

        return BlacklistedToken.objects.filter(token__jti=jti).exists()

    def test_own_token_is_blacklisted(self, jwt_client, student):
        raw, jti = self._tokens(student)
        assert jwt_client(student).post(LOGOUT, {"refresh": raw}, format="json").status_code == 205
        assert self._blacklisted(jti)

    def test_another_users_token_is_not_blacklisted_and_looks_identical(
        self, jwt_client, student, other_student
    ):
        raw, jti = self._tokens(other_student)
        own_raw, _ = self._tokens(student)
        foreign = jwt_client(student).post(LOGOUT, {"refresh": raw}, format="json")
        own = jwt_client(student).post(LOGOUT, {"refresh": own_raw}, format="json")
        assert (foreign.status_code, foreign.data) == (own.status_code, own.data)
        assert not self._blacklisted(jti)

    def test_invalid_expired_and_already_blacklisted_tokens(self, jwt_client, student):
        client = jwt_client(student)
        assert client.post(LOGOUT, {"refresh": "garbage"}, format="json").status_code == 205
        expired = RefreshToken.for_user(student)
        expired.set_exp(lifetime=-timedelta(seconds=5))  # already past its expiry
        assert client.post(LOGOUT, {"refresh": str(expired)}, format="json").status_code == 205
        raw2, _ = self._tokens(student)
        client.post(LOGOUT, {"refresh": raw2}, format="json")
        assert client.post(LOGOUT, {"refresh": raw2}, format="json").status_code == 205

    def test_logout_requires_authentication(self, api_client, student):
        raw, jti = self._tokens(student)
        assert api_client.post(LOGOUT, {"refresh": raw}, format="json").status_code == 401
        assert not self._blacklisted(jti)

    def test_rotation_and_refresh_still_work(self, api_client, student):
        login = api_client.post(LOGIN, {"email": student.email, "password": "StudentPass123!"}, format="json")
        r = api_client.post("/api/v1/auth/refresh/", {"refresh": login.data["refresh"]}, format="json")
        assert r.status_code == 200 and r.data["refresh"] != login.data["refresh"]
        again = api_client.post("/api/v1/auth/refresh/", {"refresh": login.data["refresh"]}, format="json")
        assert again.status_code == 401  # rotated-out token is dead


class TestResetLinkExpiry:
    def _link(self, user):
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        return uid, services.password_reset_token.make_token(user)

    def _confirm(self, api_client, uid, token, password="Brand-New-Passphrase-77"):
        return api_client.post(
            CONFIRM,
            {"uid": uid, "token": token, "new_password": password, "new_password_confirm": password},
            format="json",
        )

    def test_valid_unexpired_token_works(self, api_client, student):
        uid, token = self._link(student)
        assert self._confirm(api_client, uid, token).status_code == 200

    def test_expired_token_is_rejected_after_one_hour(self, api_client, student, settings):
        settings.PASSWORD_RESET_LINK_SECONDS = 3600
        with freeze_time("2030-01-01 10:00:00") as clock:
            uid, token = self._link(student)
            clock.tick(3600 - 60)
            assert services.password_reset_token.check_token(student, token)
            clock.tick(180)
            r = self._confirm(api_client, uid, token)
        assert r.status_code == 400 and r.data["error"]["code"] == "invalid_token"

    def test_token_cannot_be_reused(self, api_client, student):
        uid, token = self._link(student)
        assert self._confirm(api_client, uid, token).status_code == 200
        assert self._confirm(api_client, uid, token, "Another-Passphrase-88").status_code == 400

    def test_password_change_invalidates_outstanding_link(self, api_client, student):
        uid, token = self._link(student)
        student.set_password("Changed-Elsewhere-55")
        student.save()
        assert self._confirm(api_client, uid, token).status_code == 400

    def test_links_issued_by_djangos_default_generator_remain_compatible(self, student):
        token = default_token_generator.make_token(student)
        assert services.password_reset_token.check_token(student, token)

    def test_verification_links_keep_the_longer_default_window(self, student):
        with freeze_time("2030-01-01") as clock:
            token = services.email_verification_token.make_token(student)
            clock.tick(2 * 24 * 3600)
            assert services.email_verification_token.check_token(student, token)

    def test_garbage_tokens_are_rejected(self, student):
        for bad in ("", "x", "zzzz-yyyy", "-"):
            assert not services.password_reset_token.check_token(student, bad)


class TestTokenClaims:
    def test_access_token_carries_no_email_or_name(self, api_client, student):
        r = api_client.post(LOGIN, {"email": student.email, "password": "StudentPass123!"}, format="json")
        for key in ("access", "refresh"):
            claims = jwt.decode(r.data[key], options={"verify_signature": False})
            assert "email" not in claims and "name" not in claims
            assert claims["user_id"] == str(student.pk)
        assert r.data["user"]["email"] == student.email  # SPA still gets the profile

    def test_authorization_does_not_depend_on_removed_claims(self, jwt_client, student):
        assert jwt_client(student).get("/api/v1/auth/me/").status_code == 200


class TestResetEmailWording:
    def test_email_states_the_real_expiry(self, api_client, student, settings):
        settings.PASSWORD_RESET_LINK_SECONDS = 1800
        from apps.notifications.models import Notification

        api_client.post(RESET, {"email": student.email}, format="json")
        body = Notification.objects.filter(user=student, kind="password_reset").first().body
        assert "30 minutes" in body and "24 hours" not in body


class TestPaymentAdminCannotBypassStateMachine:
    def test_every_field_is_read_only_and_delete_is_blocked(self, admin_user):
        from django.contrib import admin
        from django.test import RequestFactory

        from apps.payments.models import Payment

        model_admin = admin.site._registry[Payment]
        request = RequestFactory().get("/admin/")
        request.user = admin_user
        assert {"status", "amount", "user", "plan", "subscription"} <= set(
            model_admin.get_readonly_fields(request)
        )
        assert model_admin.has_delete_permission(request) is False
        assert model_admin.has_add_permission(request) is False
