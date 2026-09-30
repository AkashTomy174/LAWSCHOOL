"""Celery app is defined in ``config/celery.py``.

Importing it here guarantees the app is loaded when Django starts, so
``@shared_task`` decorators bind to the project app.
"""

from config.celery import app as celery_app

__all__ = ("celery_app",)
