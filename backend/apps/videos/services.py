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


def _load_private_key_pem(raw: str) -> str:
    """Accept the key as Cloudflare returns it (base64 of the PEM) or as a PEM."""
    raw = raw.strip()
    if "BEGIN" in raw:
        return raw.replace("\\n", "\n")
    try:
        return base64.b64decode(raw, validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        raise CloudflareStreamError("Cloudflare Stream signing key is malformed.")


def build_signed_playback_token(
    *, video_uid: str, ttl_seconds: int | None = None, downloadable: bool = False
) -> tuple[str, datetime]:
    """Mint a Cloudflare Stream signed playback JWT.

    Returns ``(token, expires_at)``.  Cloudflare signing keys are RSA keys: the
    ``POST /stream/keys`` API returns a key ``id`` and a base64 ``pem`` private
    key, and tokens are **RS256** JWTs whose header ``kid`` is that id.  The
    private key never leaves the server; Cloudflare verifies with its public half.
    """
    import jwt

    ttl = ttl_seconds or settings.CLOUDFLARE_PLAYBACK_TOKEN_TTL
    key_id = settings.CLOUDFLARE_STREAM_KEY_ID
    raw_key = settings.CLOUDFLARE_STREAM_SIGNING_KEY
    if not key_id or not raw_key:
        raise CloudflareStreamError(
            "CLOUDFLARE_STREAM_KEY_ID / CLOUDFLARE_STREAM_SIGNING_KEY are not configured."
        )
    private_key = _load_private_key_pem(raw_key)

    now = datetime.now(tz=dt_timezone.utc)
    expires_at = now + timedelta(seconds=ttl)
    payload = {
        "sub": video_uid,
        "kid": key_id,
        "exp": int(expires_at.timestamp()),
        "nbf": int((now - timedelta(seconds=30)).timestamp()),
        # Least privilege: no downloads.
        "downloadable": bool(downloadable),
    }
    try:
        token = jwt.encode(
            payload, private_key, algorithm="RS256", headers={"kid": key_id}
        )
    except Exception as exc:  # bad PEM, wrong key type, missing crypto backend
        raise CloudflareStreamError("Cloudflare Stream signing key is malformed.") from exc

    from django.utils import timezone as django_timezone

    return token, django_timezone.localtime(expires_at)


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

        # Every update -- including the first -- may advance at most the drift
        # limit, and never faster than 2x playback speed since the last accepted
        # heartbeat.  Exempting the first update let one request at the final
        # second complete a lesson; without the clock bound a script could step
        # +drift in a tight loop.  Seeking ahead is simply not recorded.
        allowed_advance = settings.VIDEO_PROGRESS_MAX_DRIFT_SECONDS
        if progress.update_count:
            elapsed = (timezone.now() - progress.updated_at).total_seconds()
            allowed_advance = min(allowed_advance, int(elapsed * 2) + 5)
        if position > progress.last_position + allowed_advance:
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
        #
        # A first heartbeat can never complete a video: the first update is allowed
        # to land anywhere (resume/seek), so without this a single request naming
        # the final second would finish the lesson.  Completion also requires that
        # a playback token was actually issued to this user for this video.
        has_history = progress.update_count > 0
        was_issued_playback = PlaybackSession.objects.filter(
            user=user, video=video
        ).exists()
        if (
            has_history
            and was_issued_playback
            and ((completed and percentage >= 95) or percentage >= 98)
        ):
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
    owner=None,
) -> Video:
    """Create the Django-side metadata row for an existing Stream asset.

    The instructor uploads directly to Cloudflare (``create_direct_upload``) and
    then registers the resulting UID here; Django never receives the file.

    Signed URLs are always enforced -- paid content must never be reachable by its
    bare video id.  A non-admin may only register an asset that *they* uploaded
    (Cloudflare echoes back the ``creator`` we set at upload time), so one
    instructor cannot claim another's asset by guessing its UID.
    """
    from rest_framework.exceptions import PermissionDenied

    if owner is not None and getattr(owner, "role", None) != "admin" and not (
        owner.is_staff or owner.is_superuser
    ):
        try:
            remote = client.get_video(cloudflare_video_id)
        except CloudflareStreamError:
            raise PermissionDenied("Could not verify ownership of this video.")
        if str(remote.get("creator") or "") != str(owner.pk):
            raise PermissionDenied("You can only register videos you uploaded.")

    video = Video.objects.create(
        title=title,
        description=description,
        cloudflare_video_id=cloudflare_video_id,
        require_signed_urls=True,
    )
    try:
        client.update_video(cloudflare_video_id, require_signed_urls=True)
    except CloudflareStreamError:
        # Non-fatal: the row exists and the sync task can retry.  The playback
        # endpoint only ever hands out signed tokens and stays closed until the
        # asset is READY regardless.
        logger.exception(
            "Failed to mark Cloudflare asset as signed-only",
            extra={"video_id": str(video.pk)},
        )
    return sync_video_metadata(video)
