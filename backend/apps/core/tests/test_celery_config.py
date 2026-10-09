"""Celery wiring: every scheduled job points at a real task.

A typo in CELERY_BEAT_SCHEDULE fails silently in production (Beat publishes a
name no worker knows), so this pins the schedule against the registry, and
pins the idempotency the periodic jobs rely on.
"""

from __future__ import annotations

import pytest
from django.conf import settings

from config.celery import app


def test_every_scheduled_task_is_registered():
    app.loader.import_default_modules()
    registered = set(app.tasks)
    missing = {
        name: entry["task"]
        for name, entry in settings.CELERY_BEAT_SCHEDULE.items()
        if entry["task"] not in registered
    }
    assert not missing, f"Beat entries without a task: {missing}"


def test_schedule_covers_the_jobs_production_depends_on():
    tasks = {entry["task"] for entry in settings.CELERY_BEAT_SCHEDULE.values()}
    assert {
        "apps.core.tasks.sync_pending_videos",      # uploads become playable
        "apps.core.tasks.reconcile_payments",       # missed payment webhooks
        "apps.core.tasks.expire_subscriptions",     # status + expiry notices
        "apps.notifications.tasks.retry_failed_notification_emails",
    } <= tasks


@pytest.mark.django_db
def test_expiry_job_is_idempotent(student, plan):
    from conftest import make_subscription
    from apps.core.tasks import expire_subscriptions

    make_subscription(student, plan, starts_in_days=-10, ends_in_days=-1, payment_reference="x")
    assert expire_subscriptions() == 1
    assert expire_subscriptions() == 0  # a second run (or a duplicate beat) does nothing


@pytest.mark.django_db
def test_reconcile_job_with_nothing_stale_is_a_no_op():
    from apps.core.tasks import reconcile_payments

    assert reconcile_payments() == 0
