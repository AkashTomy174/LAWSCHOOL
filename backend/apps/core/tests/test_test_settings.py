"""The test settings must never follow ``DATABASE_URL`` (which ``backend/.env`` sets)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[3]


def _test_settings(**env_overrides) -> str:
    """Import ``config.settings.test`` in a clean interpreter; return engine|name|secret."""
    env = {k: v for k, v in os.environ.items() if k != "TEST_DATABASE_URL"}
    env.update(DJANGO_SETTINGS_MODULE="config.settings.test", **env_overrides)
    code = (
        "from django.conf import settings as s;"
        "d = s.DATABASES['default'];"
        "print(d['ENGINE'], d['NAME'], s.RAZORPAY_KEY_SECRET,"
        " s.STORAGES['staticfiles']['BACKEND'].rsplit('.', 1)[-1], sep='|')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=BACKEND, env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_database_url_does_not_redirect_the_suite():
    out = _test_settings(
        DATABASE_URL="postgres://dev:dev@localhost:5432/lawschool",
        RAZORPAY_KEY_SECRET="from-dev-env",
        DEBUG="False",  # as in CI, where no collectstatic has run
    )
    assert out == "django.db.backends.sqlite3|:memory:|rzp-sec-test|StaticFilesStorage"


def test_test_database_url_opts_in_explicitly():
    out = _test_settings(TEST_DATABASE_URL="postgres://ci:ci@localhost:5432/lawschool_test")
    engine, name, *_ = out.split("|")
    assert engine == "django.db.backends.postgresql"
    assert name == "lawschool_test"
