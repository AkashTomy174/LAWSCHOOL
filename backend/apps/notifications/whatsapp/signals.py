"""Live-class change detection -> WhatsApp fan-out tasks.

``pre_save`` remembers what the row looked like before the edit; ``post_save``
compares and queues one fan-out per meaningful change.  Nothing here does I/O
beyond one SELECT -- the audience expansion happens in a Celery task after the
request's transaction commits.
"""

from __future__ import annotations

from functools import partial

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from apps.core.logging import get_logger
from apps.live.models import LiveClass

logger = get_logger(__name__)

_FIELDS = ("scheduled_start", "meeting_url", "is_published")


def _queue(event: str, live: LiveClass) -> None:
    from apps.notifications.tasks import fan_out_live_class_event
    from apps.notifications.whatsapp.events import class_snapshot

    snap = class_snapshot(live)
    transaction.on_commit(partial(_safe_delay, fan_out_live_class_event, event, snap))


def _safe_delay(task, *args) -> None:
    try:
        task.delay(*args)
    except Exception:
        logger.exception("Could not queue WhatsApp live-class fan-out")


@receiver(pre_save, sender=LiveClass)
def remember_previous_state(sender, instance: LiveClass, **kwargs) -> None:
    if not settings.WHATSAPP_ENABLED:
        return
    previous = None
    if instance.pk and not instance._state.adding:
        previous = (
            sender.objects.filter(pk=instance.pk).values(*_FIELDS).first()
        )
    instance._wa_previous = previous


@receiver(post_save, sender=LiveClass)
def announce_class_changes(sender, instance: LiveClass, created: bool, **kwargs) -> None:
    if not settings.WHATSAPP_ENABLED:
        return
    old = getattr(instance, "_wa_previous", None)
    if created or old is None:
        if instance.is_published:
            _queue("scheduled", instance)
        return
    if old["is_published"] and not instance.is_published:
        _queue("cancelled", instance)
        return
    if not old["is_published"] and instance.is_published:
        _queue("scheduled", instance)
        return
    if not instance.is_published:
        return
    if old["scheduled_start"] != instance.scheduled_start:
        _queue("rescheduled", instance)
    elif old["meeting_url"] != instance.meeting_url:
        _queue("link_updated", instance)


@receiver(post_delete, sender=LiveClass)
def announce_class_deleted(sender, instance: LiveClass, **kwargs) -> None:
    if settings.WHATSAPP_ENABLED and instance.is_published:
        try:
            _queue("cancelled", instance)
        except Exception:  # the course may be cascading away with it
            logger.warning("Skipped cancellation notice for deleted class")
