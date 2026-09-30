"""ASGI entrypoint.

Kept in place so the API can later move to websockets (live leaderboard /
notification push) without changing the deployment topology.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

application = get_asgi_application()
