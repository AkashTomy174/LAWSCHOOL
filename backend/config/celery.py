"""Celery application factory.

The app is created here (and imported from ``config/__init__.py``) so that
``@shared_task`` decorators across the project bind to one instance.
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

app = Celery("lawschool")

# Read CELERY_* settings from Django settings, namespaced with CELERY_.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Discover tasks in every installed app's tasks.py.
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self) -> None:  # pragma: no cover - diagnostic helper
    """Trivial task used to confirm a worker is consuming the queue."""
    print(f"Request: {self.request!r}")
