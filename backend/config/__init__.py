"""Django configuration package.

``DJANGO_SETTINGS_MODULE`` selects the environment:

* ``config.settings.development`` -- local work
* ``config.settings.production``  -- deployed
* ``config.settings.test``        -- pytest
"""

__all__ = ["celery_app"]

# Ensure the Celery app is loaded whenever Django starts so that @shared_task
# decorators in any app bind to the project app.
from .celery import app as celery_app  # noqa: E402,F401
