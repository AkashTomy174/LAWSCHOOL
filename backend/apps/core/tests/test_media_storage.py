"""Production media storage: object storage when configured, a loud warning when not.

Uploads (avatars, course thumbnails) used to land on the container disk, which
is wiped on every deploy, and with DEBUG off Django never served /media/ at all.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

BASE_ENV = {
    "DJANGO_SETTINGS_MODULE": "config.settings.production",
    "SECRET_KEY": "k3Jx9vQ2mZ8pL5rT1wY7nB4cD6fG0hA2sE9uI3oP8qR5tV1y",
    "DATABASE_URL": "postgres://u:p@localhost:1/x",
    "REDIS_URL": "redis://localhost:1/0",
    "CORS_ALLOWED_ORIGINS": "https://app.test",
    "EMAIL_HOST": "smtp.test",
    **{k: "d" for k in ("RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET", "RAZORPAY_WEBHOOK_SECRET",
                        "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN",
                        "CLOUDFLARE_STREAM_KEY_ID", "CLOUDFLARE_STREAM_SIGNING_KEY")},
}
S3_ENV = {
    "AWS_STORAGE_BUCKET_NAME": "media",
    "AWS_S3_ENDPOINT_URL": "https://storage.example.com",
    "AWS_S3_REGION_NAME": "auto",
    "AWS_ACCESS_KEY_ID": "key-id",
    "AWS_SECRET_ACCESS_KEY": "secret",
}


def _production(extra_env, code):
    env = {**os.environ, **BASE_ENV, **extra_env}
    for key in S3_ENV:
        if key not in extra_env:
            env.pop(key, None)
    result = subprocess.run(
        [sys.executable, "-c", "import django, json; django.setup(); " + code],
        env=env, capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


_INSPECT = (
    "from django.conf import settings as s; from apps.core.checks import check_media_storage; "
    "print(json.dumps({'storage': s.STORAGES['default'], "
    "'warnings': [w.id for w in check_media_storage(None)]}))"
)


def test_without_a_bucket_production_warns():
    out = _production({}, _INSPECT)
    assert out["storage"]["BACKEND"].endswith("FileSystemStorage")
    assert out["warnings"] == ["lawschool.W003"]


def test_with_a_bucket_uploads_go_to_private_object_storage():
    out = _production(S3_ENV, _INSPECT)
    storage = out["storage"]
    assert storage["BACKEND"] == "storages.backends.s3.S3Storage"
    options = storage["OPTIONS"]
    assert options["bucket_name"] == "media"
    assert options["endpoint_url"] == "https://storage.example.com"
    assert options["querystring_auth"] is True       # signed, expiring URLs
    assert options["default_acl"] is None             # bucket stays private
    assert options["file_overwrite"] is False         # no clobbering by name
    assert out["warnings"] == []
