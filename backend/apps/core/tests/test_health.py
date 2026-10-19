"""Liveness vs readiness probes.

``/health/`` answers whenever the process runs.  ``/health/ready/`` also proves
the database answers (503 if not); the cache is reported but optional, because
the app now runs without it.  Neither leaks error details.
"""

from __future__ import annotations

from unittest import mock

import pytest
from django.db.utils import OperationalError


def test_liveness_needs_nothing(client):
    response = client.get("/health/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.django_db
def test_ready_when_database_and_cache_answer(client):
    response = client.get("/health/ready/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"database": "ok", "cache": "ok"}}


@pytest.mark.django_db
def test_not_ready_without_the_database(client):
    with mock.patch("config.urls._database_ok", side_effect=OperationalError("secret dsn")):
        response = client.get("/health/ready/")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable" and body["checks"]["database"] == "error"
    assert "secret" not in response.content.decode()


@pytest.mark.django_db
def test_cache_outage_is_reported_but_not_fatal(client, settings):
    settings.CACHES = {"default": {"BACKEND": "apps.core.tests.test_cache_outage.BrokenCache"}}
    response = client.get("/health/ready/")
    assert response.status_code == 200
    assert response.json()["checks"] == {"database": "ok", "cache": "error"}


def test_production_settings_let_railways_healthcheck_through():
    """Railway probes over plain HTTP with Host ``healthcheck.railway.app``.
    Production must neither reject that host nor redirect /health/ to HTTPS."""
    import json
    import os
    import subprocess
    import sys

    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings.production",
        "SECRET_KEY": "k3Jx9vQ2mZ8pL5rT1wY7nB4cD6fG0hA2sE9uI3oP8qR5tV1y", "DATABASE_URL": "postgres://u:p@localhost:1/x",
        "REDIS_URL": "redis://localhost:1/0", "CORS_ALLOWED_ORIGINS": "https://app.test",
        "ALLOWED_HOSTS": "api.test",
        **{k: "d" for k in ("RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET", "RAZORPAY_WEBHOOK_SECRET",
                            "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN",
                            "CLOUDFLARE_STREAM_KEY_ID", "CLOUDFLARE_STREAM_SIGNING_KEY")},
    }
    code = (
        "import django, json; django.setup(); from django.conf import settings as s; "
        "print(json.dumps({'hosts': s.ALLOWED_HOSTS, 'exempt': s.SECURE_REDIRECT_EXEMPT, "
        "'redirect': s.SECURE_SSL_REDIRECT}))"
    )
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True)
    config = json.loads(out.stdout.strip().splitlines()[-1])
    assert "healthcheck.railway.app" in config["hosts"] and "api.test" in config["hosts"]
    assert config["redirect"] is True
    import re

    assert any(re.match(p, "health/ready/") for p in config["exempt"])
    assert not any(re.match(p, "api/v1/courses/") for p in config["exempt"])
