"""Audit A1: blank/placeholder signing secrets and the JWT algorithm."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.conf import settings

from config.settings.base import secret_problem

BACKEND = Path(__file__).resolve().parents[3]
GOOD = "k3Jx9vQ2mZ8pL5rT1wY7nB4cD6fG0hA2sE9uI3oP8qR5tV1y"

# Minimal env that satisfies every other production startup requirement.
_BASE_ENV = {
    "DATABASE_URL": "postgres://u:p@localhost:5432/db",
    "REDIS_URL": "redis://localhost:6379/0",
    "CORS_ALLOWED_ORIGINS": "https://example.org",
    "RAZORPAY_KEY_ID": "k",
    "RAZORPAY_KEY_SECRET": "k",
    "RAZORPAY_WEBHOOK_SECRET": "k",
    "CLOUDFLARE_ACCOUNT_ID": "k",
    "CLOUDFLARE_API_TOKEN": "k",
    "CLOUDFLARE_STREAM_KEY_ID": "k",
    "CLOUDFLARE_STREAM_SIGNING_KEY": "k",
}


def _load_production(**overrides):
    """Import the production settings in a clean interpreter; return the result."""
    env = {k: v for k, v in os.environ.items() if k not in {"SECRET_KEY", "JWT_SECRET"}}
    env.update(_BASE_ENV)
    env["DJANGO_SETTINGS_MODULE"] = "config.settings.production"
    env.update(overrides)
    code = (
        "import django.conf, os;"
        "from config.settings import production as p;"
        "print('KEY', p.SIMPLE_JWT['SIGNING_KEY']==os.environ.get('JWT_SECRET') or "
        "p.SIMPLE_JWT['SIGNING_KEY']==os.environ['SECRET_KEY'])"
    )
    return subprocess.run(
        [sys.executable, "-c", code], cwd=BACKEND, env=env, capture_output=True, text=True
    )


class TestSecretProblem:
    @pytest.mark.parametrize("value", [None, "", "   ", "\t\n"])
    def test_empty_and_whitespace_rejected(self, value):
        assert secret_problem(value)

    @pytest.mark.parametrize(
        "value",
        [
            "change-me-to-a-long-random-string",
            "insecure-development-key-change-me-please-now",
            "your-secret-goes-here-and-is-long-enough-xx",
        ],
    )
    def test_placeholders_rejected(self, value):
        assert secret_problem(value) == "looks like a placeholder"

    def test_short_and_padded_rejected(self):
        assert "shorter" in secret_problem("a1b2c3")
        assert "whitespace" in secret_problem(" " + GOOD)

    def test_valid_secret_accepted_and_never_echoed(self):
        assert secret_problem(GOOD) is None
        assert GOOD not in (secret_problem("x" * 5) or "")


class TestProductionStartup:
    def test_valid_secrets_boot(self):
        result = _load_production(SECRET_KEY=GOOD, JWT_SECRET=GOOD[::-1])
        assert result.returncode == 0, result.stderr[-400:]

    def test_blank_jwt_secret_refuses_to_boot(self):
        result = _load_production(SECRET_KEY=GOOD, JWT_SECRET="")
        assert result.returncode != 0 and "JWT_SECRET" in result.stderr
        assert GOOD not in result.stderr

    def test_whitespace_jwt_secret_refuses_to_boot(self):
        result = _load_production(SECRET_KEY=GOOD, JWT_SECRET="   ")
        assert result.returncode != 0 and "JWT_SECRET" in result.stderr

    def test_placeholder_secret_key_refuses_to_boot(self):
        result = _load_production(SECRET_KEY="change-me-to-a-long-random-string")
        assert result.returncode != 0 and "SECRET_KEY" in result.stderr

    def test_unset_jwt_secret_falls_back_to_validated_secret_key(self):
        result = _load_production(SECRET_KEY=GOOD)
        assert result.returncode == 0 and "KEY True" in result.stdout

    def test_dockerfile_build_secret_passes_validation(self):
        text = (BACKEND / "Dockerfile").read_text()
        line = next(l for l in text.splitlines() if "SECRET_KEY=" in l and "RUN" in l)
        value = line.split("SECRET_KEY=")[1].split()[0]
        assert secret_problem(value) is None


class TestBlankJwtSecretInBaseSettings:
    def test_blank_env_value_is_treated_as_unset(self):
        env = {**os.environ, "JWT_SECRET": "", "SECRET_KEY": GOOD,
               "DJANGO_SETTINGS_MODULE": "config.settings.test"}
        out = subprocess.run(
            [sys.executable, "-c",
             "from config.settings.base import SIMPLE_JWT as J, SECRET_KEY as S;"
             "print(J['SIGNING_KEY']==S and bool(S))"],
            cwd=BACKEND, env=env, capture_output=True, text=True,
        )
        assert out.stdout.strip() == "True", out.stderr[-300:]


@pytest.mark.django_db
class TestJwtRoundTrip:
    def test_algorithm_is_explicit_hs256(self):
        assert settings.SIMPLE_JWT["ALGORITHM"] == "HS256"
        assert settings.SIMPLE_JWT["SIGNING_KEY"]

    def test_registration_and_login_work_and_tokens_are_hs256(self, api_client):
        import jwt

        payload = {
            "email": "newuser@test.local", "name": "New User",
            "password": "Str0ng-Passphrase-9", "password_confirm": "Str0ng-Passphrase-9",
        }
        reg = api_client.post("/api/v1/auth/register/", payload, format="json")
        assert reg.status_code == 202, reg.data
        login = api_client.post(
            "/api/v1/auth/login/",
            {"email": payload["email"], "password": payload["password"]},
            format="json",
        )
        assert login.status_code == 200
        header = jwt.get_unverified_header(login.data["access"])
        assert header["alg"] == "HS256"
        # A token forged with the "none" algorithm is rejected.
        forged = jwt.encode({"user_id": "x"}, None, algorithm="none")
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {forged}")
        assert api_client.get("/api/v1/auth/me/").status_code == 401
