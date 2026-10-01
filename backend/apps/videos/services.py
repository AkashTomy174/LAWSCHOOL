"""Protected playback token minting and progress tracking.

Security model (defence in depth):

1. **Django authenticates** the request (JWT) and rejects anonymous callers.
2. **``can_user_access_video``** -- the single entitlement service -- decides
   whether this student may watch *this* lesson right now.
3. Only then is a **short-lived signed token** (default 5 minutes) minted with
   the Cloudflare Stream signing key, which never reaches the browser.
4. Cloudflare refuses to serve the stream without that token, so an expired
   subscription cannot keep playing from a cached URL.

Every issued token is recorded in ``PlaybackSession`` for audit and rate-limit
analysis.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone as dt_timezone

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from apps.core.constants import VideoStatus
from apps.core.exceptions import (
    EntitlementError,
    PlaybackUnavailableError,
    VideoNotReadyError,
)
from apps.core.logging import get_logger
from apps.core.network import client_ip
from apps.subscriptions.services import can_user_access_video
from apps.videos.cloudflare import CloudflareStreamError, client, parse_playback_urls
from apps.videos.models import PlaybackSession, Video, VideoProgress

logger = get_logger(__name__)

# Students may not request tokens faster than this (per user) -- a legitimate
# player refreshes once every few minutes, so 30/10min is generous.
_PLAYBACK_TOKEN_BUDGET = 30
_PLAYBACK_TOKEN_WINDOW = 600

# Progress updates are throttled per user to absorb the 10-30s heartbeat.
_PROGRESS_UPDATE_BUDGET = 120
_PROGRESS_UPDATE_WINDOW = 600


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def build_signed_playback_token(
    *, video_uid: str, ttl_seconds: int | None = None, downloadable: bool = False
) -> tuple[str, datetime]:
    """Mint a Cloudflare Stream signed playback JWT.

    Returns ``(token, expires_at)``.  Implemented with the standard library so
    the signing path has no third-party dependency to keep patched; the algorithm
    is fixed by Cloudflare (HS256 over a JWT with ``kid`` = signing key id).
    """
    ttl = ttl_seconds or settings.CLOUDFLARE_PLAYBACK_TOKEN_TTL
    signing_key = settings.CLOUDFLARE_STREAM_SIGNING_KEY
    if not signing_key:
        raise CloudflareStreamError("CLOUDFLARE_STREAM_SIGNING_KEY is not configured.")

    # Cloudflare issues signing keys as "<key_id>:<key_secret>"; the kid goes in
    # the JWT header and the secret is used for the HMAC.
    key_id, _, secret = signing_key.partition(":")
    if not secret:
        raise CloudflareStreamError("Cloudflare Stream signing key is malformed.")

    now = datetime.now(tz=dt_timezone.utc)
    expires_at = now + timedelta(seconds=ttl)

    header = {"alg": "HS256", "typ": "JWT", "kid": key_id}
    payload = {
        "sub": video_uid,
        "kid": key_id,
        "exp": int(expires_at.timestamp()),
        "nbf": int((now - timedelta(seconds=30)).timestamp()),
        "iat": int(now.timestamp()),
        # Least privilege: no downloads, no second-user sharing.
        "downloadable": bool(downloadable),
    }

    signing_input = (
        f"{_b64url(json.dumps(header, separators=(',', ':')).encode())}."
        f"{_b64url(json.dumps(payload, separators=(',', ':')).encode())}"
    )
    signature = hmac.new(
        secret.encode("utf-8"), signing_input.encode("utf-8"), hashlib.sha256
    ).digest()

    # ``expires_at`` is already tz-aware (it came from ``datetime.now(tz=utc)``),
    # so it must be converted rather than re-aware'd -- ``django.utils.timezone
    # .make_aware`` rejects a datetime that already carries tzinfo.
    from django.utils import timezone as django_timezone

    return f"{signing_input}.{_b64url(signature)}", django_timezone.localtime(
        expires_at
    )


def _enforce_rate_limit(user, *, scope: str, budget: int, window: int) -> None:
    """Fixed-window limiter on Redis.

    Chosen over a sliding window because token requests are cheap and the goal is
    to stop scripted harvesting, not to shape traffic precisely.
    """
    key = f"ratelimit:{scope}:{user.pk}:{int(timezone.now().timestamp()) // window}"
    added = cache.add(key, 1, window)
    if added:
        return
    try:
        count = cache.incr(key)
    except ValueError:  # key expired between add and incr
        cache.set(key, 1, window)
        return
    if count > budget:
        logger.warning(
            "Playback/progress rate limit exceeded",
            extra={"user_id": str(user.pk), "scope": scope},
        )
        raise EntitlementError(
            {"detail": "Too many requests. Please slow down."}, code="rate_limited"
        )


def issue_playback_token(*, user, video: Video, request=None) -> dict:
    """Authorize and return playback information for ``video``.

    This function is the *only* way playback credentials leave the system.
    """
    decision = can_user_access_video(user, video)
    if not decision:
        logger.warning(
            "Playback denied",
            extra={
                "user_id": str(user.pk),
                "video_id": str(video.pk),
                "reason": decision.reason,
            },
        )
        raise EntitlementError({"detail": decision.detail}, code=decision.reason)

    if video.status != VideoStatus.READY:
        raise VideoNotReadyError()

    _enforce_rate_limit(
        user,
        scope="playback",
        budget=_PLAYBACK_TOKEN_BUDGET,
        window=_PLAYBACK_TOKEN_WINDOW,
    )

    # A misconfigured or rotated Cloudflare signing key is an *operational* problem,
    # not the student's fault.  Convert it into a clean 503 (with the detail logged
    # server-side) instead of letting the exception escape as an unhandled 500 -- in
    # DEBUG that would render a full stack trace, and in production it would be an
    # opaque error page.  The student sees "temporarily unavailable"; we see why.
    try:
        token, expires_at = build_signed_playback_token(
            video_uid=video.cloudflare_video_id,
            ttl_seconds=settings.CLOUDFLARE_PLAYBACK_TOKEN_TTL,
            downloadable=False,
        )
    except CloudflareStreamError:
        logger.exception(
            "Could not mint a Cloudflare Stream playback token",
            extra={"user_id": str(user.pk), "video_id": str(video.pk)},
        )
        raise PlaybackUnavailableError()

    ip_address = user_agent = None
    if request is not None:
        ip_address = client_ip(request)
        user_agent = (request.META.get("HTTP_USER_AGENT") or "")[:300]

    PlaybackSession.objects.create(
        user=user,
        video=video,
        ip_address=ip_address,
        user_agent=user_agent or "",
        # Store a fingerprint, never the token itself.
        token_fingerprint=hashlib.sha256(token.encode()).hexdigest()[:32],
        expires_at=expires_at,
    )

    customer = settings.CLOUDFLARE_STREAM_CUSTOMER_CODE
    return {
        "video_uid": str(video.playback_uid),
        # The iframe/customer-code URL is inert without the signed token.
        "hls_url": (
            f"https://customer-{customer}.cloudflarestream.com/{token}/manifest/video.m3u8"
            if customer
            else ""
        ),
        "dash_url": (
            f"https://customer-{customer}.cloudflarestream.com/{token}/manifest/video.mpd"
            if customer
            else ""
        ),
        "thumbnail_url": video.thumbnail_url,
        "duration_seconds": video.duration_seconds,
        "token": token,
        "token_expires_at": expires_at,
        "expires_in": settings.CLOUDFLARE_PLAYBACK_TOKEN_TTL,
    }


def update_video_progress(
    *,
    user,
    video: Video,
    position_seconds: int,
    watched_seconds: int | None = None,
    completed: bool = False,
) -> VideoProgress:
    """Upsert playback progress after validating the numbers server-side.

    Anti-cheat rules:
    * ``position_seconds`` may not exceed the real video duration (+ small slack).
    * A single update may not advance further than
      ``VIDEO_PROGRESS_MAX_DRIFT_SECONDS`` beyond the stored position -- this blocks
      a script that jumps straight to 100%.
    * Progress is monotonic: it never goes backwards.
    """
    decision = can_user_access_video(user, video)
    if not decision:
        raise EntitlementError({"detail": decision.detail}, code=decision.reason)

    _enforce_rate_limit(
        user,
        scope="progress",
        budget=_PROGRESS_UPDATE_BUDGET,
        window=_PROGRESS_UPDATE_WINDOW,
    )

    duration = max(0, video.duration_seconds or 0)
    # Allow a couple of seconds of player rounding, but never more than the asset.
    ceiling = duration + 5 if duration else position_seconds
    position = max(0, min(int(position_seconds), ceiling))

    with transaction.atomic():
        progress, _created = VideoProgress.objects.select_for_update().get_or_create(
            user=user, video=video, defaults={"lesson": getattr(video, "lesson", None)}
        )

        drift_limit = settings.VIDEO_PROGRESS_MAX_DRIFT_SECONDS
        # The drift guard blocks a script jumping straight to the end, but it must
        # not punish legitimate behaviour:
        #   * the *first* update (stored position 0) is allowed to be anywhere --
        #     students resume mid-video and seek in the player, and a real rebuild
        #     of "watched" time is derived from the player's own increments;
        #   * ``update_count == 0`` therefore means "no history yet".
        is_first_update = progress.update_count == 0 and progress.last_position == 0
        if not is_first_update and position > progress.last_position + drift_limit:
            logger.warning(
                "Suspicious progress jump rejected",
                extra={
                    "user_id": str(user.pk),
                    "video_id": str(video.pk),
                    "stored": progress.last_position,
                    "submitted": position,
                },
            )
            position = progress.last_position

        progress.last_position = max(progress.last_position, position)
        if watched_seconds is not None:
            progress.watched_seconds = max(
                progress.watched_seconds, min(int(watched_seconds), ceiling)
            )

        percentage = 0.0
        if duration:
            percentage = round(min(100.0, (progress.last_position / duration) * 100), 2)
        progress.completion_percentage = percentage

        # Completion requires either an explicit end-of-video signal or >=98%
        # actual playback -- the flag alone is not trusted when the percentage
        # contradicts it.
        if (completed and percentage >= 95) or percentage >= 98:
            if not progress.completed:
                progress.mark_completed()
        progress.update_count += 1
        progress.save()

    return progress


def invalidate_video_cache(video: Video) -> None:  # pragma: no cover - hook point
    cache.delete(f"video:meta:{video.pk}")


def sync_video_metadata(video: Video) -> Video:
    """Pull status/duration/thumbnail from Cloudflare.

    Called by the manual sync endpoint and by a periodic task; nothing pushes
    status changes to us, so this is how an asset flips to READY.
    """
    try:
        payload = client.get_video(video.cloudflare_video_id)
    except CloudflareStreamError as exc:
        logger.warning(
            "Could not sync video metadata",
            extra={"video_id": str(video.pk), "error": str(exc)},
        )
        return video

    status_map = {
        "ready": VideoStatus.READY,
        "inprogress": VideoStatus.PROCESSING,
        "queued": VideoStatus.PROCESSING,
        "error": VideoStatus.FAILED,
    }
    video.status = status_map.get(payload.get("status", ""), video.status)
    video.duration_seconds = int(payload.get("duration") or video.duration_seconds or 0)
    video.thumbnail_url = payload.get("thumbnail") or video.thumbnail_url
    video.processing_error = (
        str((payload.get("status") or {}).get("errorReasonText") or "")
        if isinstance(payload.get("status"), dict)
        else ""
    )
    video.last_synced_at = timezone.now()
    video.save(
        update_fields=[
            "status",
            "duration_seconds",
            "thumbnail_url",
            "processing_error",
            "last_synced_at",
            "updated_at",
        ]
    )
    return video


def register_video(
    *,
    title: str,
    cloudflare_video_id: str,
    description: str = "",
    require_signed_urls: bool = True,
) -> Video:
    """Create the Django-side metadata row for an existing Stream asset.

    The instructor uploads directly to Cloudflare (``create_direct_upload``) and
    then registers the resulting UID here; Django never receives the file.
    """
    video = Video.objects.create(
        title=title,
        description=description,
        cloudflare_video_id=cloudflare_video_id,
        require_signed_urls=require_signed_urls,
    )
    if require_signed_urls:
        try:
            client.update_video(cloudflare_video_id, require_signed_urls=True)
        except CloudflareStreamError:
            # Non-fatal: the row exists and a reconciliation task can retry.  The
            # playback endpoint stays closed until the asset is READY regardless.
            logger.exception(
                "Failed to mark Cloudflare asset as signed-only",
                extra={"video_id": str(video.pk)},
            )
    return sync_video_metadata(video)
