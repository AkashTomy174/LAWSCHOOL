"""Maintenance tasks: subscription expiry, payment reconciliation, videos."""

from __future__ import annotations

from celery import shared_task

from apps.core.logging import get_logger

logger = get_logger(__name__)


@shared_task
def expire_subscriptions() -> int:
    """Flip lapsed ACTIVE subscriptions to EXPIRED and notify the owners.

    Runs hourly (see CELERY_BEAT_SCHEDULE).  Entitlement checks additionally
    verify the date window in SQL, so this job's only job is to keep stored state
    truthful and send the "renew" nudge.
    """
    from apps.core.constants import NotificationKind, SubscriptionStatus
    from apps.subscriptions.models import Subscription
    from apps.subscriptions.services_lifecycle import expire_lapsed_subscriptions

    expired_count = expire_lapsed_subscriptions()

    # Notify subscriptions that lapsed in the last hour (i.e. just now).
    from django.utils import timezone

    from apps.notifications.services import notify_user

    recent = Subscription.objects.filter(
        status=SubscriptionStatus.EXPIRED,
        end_date__gte=timezone.now() - timezone.timedelta(hours=2),
    ).select_related("user", "plan")
    for subscription in recent:
        try:
            notify_user(
                user=subscription.user,
                kind=NotificationKind.SUBSCRIPTION_EXPIRED,
                context={
                    "plan_name": subscription.plan.name,
                    "end_date": (
                        subscription.end_date.strftime("%d %b %Y")
                        if subscription.end_date
                        else ""
                    ),
                },
            )
        except Exception:  # pragma: no cover
            logger.exception(
                "Failed to notify expiry",
                extra={"subscription_id": str(subscription.pk)},
            )

    return expired_count


@shared_task
def send_expiry_reminders(days_before: int = 7) -> int:
    """Warn students whose subscription ends within ``days_before``."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.core.constants import NotificationKind, SubscriptionStatus
    from apps.notifications.services import notify_user
    from apps.subscriptions.models import Subscription

    now = timezone.now()
    window_end = now + timedelta(days=days_before)
    upcoming = Subscription.objects.filter(
        status=SubscriptionStatus.ACTIVE, end_date__gt=now, end_date__lte=window_end
    ).select_related("user", "plan")

    sent = 0
    for subscription in upcoming:
        try:
            notify_user(
                user=subscription.user,
                kind=NotificationKind.SUBSCRIPTION_EXPIRING,
                context={
                    "plan_name": subscription.plan.name,
                    "end_date": subscription.end_date.strftime("%d %b %Y"),
                },
            )
            sent += 1
        except Exception:  # pragma: no cover
            logger.exception(
                "Failed to send expiry reminder",
                extra={"subscription_id": str(subscription.pk)},
            )
    return sent


@shared_task
def reconcile_payments(older_than_minutes: int = 30) -> int:
    """Resolve payments stuck in CREATED after a missed webhook."""
    from apps.payments.services import reconcile_stale_payments

    return reconcile_stale_payments(older_than_minutes=older_than_minutes)


@shared_task
def sync_pending_videos(limit: int = 50) -> int:
    """Poll Cloudflare for assets stuck in PROCESSING/PENDING.

    Cloudflare's ``video.processed`` webhook is the primary signal; this task is
    the safety net for a dropped webhook so a lesson never stays unplayable.
    """
    from apps.core.constants import VideoStatus
    from apps.videos.models import Video
    from apps.videos.services import sync_video_metadata

    pending = Video.objects.filter(
        status__in=[VideoStatus.PENDING, VideoStatus.PROCESSING]
    )[:limit]

    synced = 0
    for video in pending:
        try:
            sync_video_metadata(video)
            synced += 1
        except Exception:  # pragma: no cover
            logger.exception("Video sync failed", extra={"video_id": str(video.pk)})
    return synced


@shared_task
def recalculate_leaderboard_task() -> int:
    """Rebuild every leaderboard row and re-stamp ranks."""
    from apps.leaderboard.models import recalculate_leaderboard

    return recalculate_leaderboard()


@shared_task
def finish_quiz_leaderboards(attempt_id: str) -> None:
    """Refresh a student's leaderboard row after a graded attempt."""
    from apps.leaderboard.models import refresh_user_leaderboard
    from apps.quizzes.models import QuizAttempt

    attempt = QuizAttempt.objects.select_related("user").filter(pk=attempt_id).first()
    if attempt:
        refresh_user_leaderboard(attempt.user)
