"""F2: the container HEALTHCHECK must pass under production ALLOWED_HOSTS."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[3]

ENV = {
    "DJANGO_SETTINGS_MODULE": "config.settings.production",
    "SECRET_KEY": "k3Jx9vQ2mZ8pL5rT1wY7nB4cD6fG0hA2sE9uI3oP8qR5tV1y",
    "DATABASE_URL": "postgres://u:p@localhost:1/x",
    "REDIS_URL": "redis://localhost:1/0",
    "CORS_ALLOWED_ORIGINS": "https://app.test",
    "ALLOWED_HOSTS": "api.test",
    **{k: "d" for k in ("RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET", "RAZORPAY_WEBHOOK_SECRET",
                        "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN",
                        "CLOUDFLARE_STREAM_KEY_ID", "CLOUDFLARE_STREAM_SIGNING_KEY")},
}

PROBE = """
import django, json, sys
django.setup()
from django.test import Client
host = sys.argv[1]
r = Client(HTTP_HOST=host).get('/health/')
print(json.dumps({'status': r.status_code}))
"""


def _status(host: str) -> int:
    out = subprocess.run(
        [sys.executable, "-c", PROBE, host], cwd=BACKEND,
        env={**os.environ, **ENV}, capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout.strip().splitlines()[-1])["status"]


def _healthcheck_host() -> str | None:
    text = (BACKEND / "Dockerfile").read_text()
    line = next(l for l in text.splitlines() if l.lstrip().startswith("CMD curl"))
    match = re.search(r'-H "Host: ([^"]+)"', line)
    return match.group(1) if match else None


def test_bare_localhost_probe_is_rejected_which_was_the_bug():
    """Reproduces the audit finding: Host 'localhost:8000' gets HTTP 400 in production."""
    assert _status("localhost:8000") == 400


def test_dockerfile_healthcheck_sends_an_allowed_host_and_passes():
    host = _healthcheck_host()
    assert host, "HEALTHCHECK must send an explicit Host header"
    assert _status(host) == 200


def test_unknown_hosts_are_still_rejected():
    assert _status("evil.example") == 400
