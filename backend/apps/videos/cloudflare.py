"""Thin Cloudflare Stream API client.

Kept deliberately dumb: it knows how to talk to Cloudflare and nothing about
entitlements.  All authorization decisions happen in
``apps.subscriptions.services`` *before* this module is reached.

Trade-off: the official ``cloudflare`` SDK is heavier than this needs and its
Stream surface lags the REST API, so a small ``requests``-based client is used
instead.  It is the only place that reads ``CLOUDFLARE_API_TOKEN``.
"""

from __future__ import annotations

import json
from typing import Any

import requests
from django.conf import settings

from apps.core.logging import get_logger

logger = get_logger(__name__)

_API_BASE = "https://api.cloudflare.com/client/v4"
_TIMEOUT = 10


class CloudflareStreamError(Exception):
    """Raised when Cloudflare rejects a request or is unreachable."""


class CloudflareStreamClient:
    """Minimal wrapper over the Stream endpoints this project uses."""

    def __init__(
        self,
        account_id: str | None = None,
        api_token: str | None = None,
        customer_code: str | None = None,
    ) -> None:
        self.account_id = account_id or settings.CLOUDFLARE_ACCOUNT_ID
        self.api_token = api_token or settings.CLOUDFLARE_API_TOKEN
        self.customer_code = customer_code or settings.CLOUDFLARE_STREAM_CUSTOMER_CODE

    # ---- plumbing -------------------------------------------------------- #
    def _headers(self) -> dict[str, str]:
        if not self.api_token:
            raise CloudflareStreamError("CLOUDFLARE_API_TOKEN is not configured.")
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    def _url(self, path: str) -> str:
        if not self.account_id:
            raise CloudflareStreamError("CLOUDFLARE_ACCOUNT_ID is not configured.")
        return f"{_API_BASE}/accounts/{self.account_id}/stream{path}"

    def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        try:
            response = requests.request(
                method,
                self._url(path),
                headers=self._headers(),
                timeout=_TIMEOUT,
                **kwargs,
            )
        except requests.RequestException as exc:  # network failure
            logger.exception("Cloudflare Stream request failed", extra={"path": path})
            raise CloudflareStreamError("Could not reach Cloudflare Stream.") from exc

        try:
            payload = response.json()
        except ValueError:
            raise CloudflareStreamError(
                f"Unexpected response from Cloudflare (HTTP {response.status_code})."
            )

        if not response.ok or not payload.get("success", False):
            errors = payload.get("errors") or [{"message": response.text[:300]}]
            logger.error(
                "Cloudflare Stream API error",
                extra={"path": path, "status": response.status_code, "errors": errors},
            )
            raise CloudflareStreamError(
                errors[0].get("message", "Cloudflare Stream error.")
            )

        return payload["result"]

    # ---- operations ------------------------------------------------------ #
    def create_direct_upload(
        self, *, max_duration_seconds: int | None = None
    ) -> dict[str, Any]:
        """Create a one-time upload URL for the instructor's browser.

        A direct-upload URL means large files go straight from the instructor to
        Cloudflare and never transit (or get stored on) the Django server.
        """
        body: dict[str, Any] = {"maxDurationSeconds": max_duration_seconds or 3600}
        return self._request("POST", "/direct_upload", json=body)

    def get_video(self, video_id: str) -> dict[str, Any]:
        """Fetch metadata (status, duration, thumbnail, playback URLs)."""
        return self._request("GET", f"/{video_id}")

    def delete_video(self, video_id: str) -> bool:
        self._request("DELETE", f"/{video_id}")
        return True

    def update_video(
        self, video_id: str, *, require_signed_urls: bool = True
    ) -> dict[str, Any]:
        """Toggle the private/signed-URL flag on an asset.

        ``requireSignedURLs: true`` is the Cloudflare-side half of the security
        model: even if a student learned the raw video id, the CDN refuses to
        serve the stream without a valid signed token.
        """
        body: dict[str, Any] = {"requireSignedURLs": require_signed_urls}
        return self._request("POST", f"/{video_id}", json=body)

    def list_videos(self, *, status: str | None = None) -> list[dict[str, Any]]:
        params = {"status": status} if status else {}
        result = self._request("GET", "", params=params)
        return result if isinstance(result, list) else result.get("videos", [])


client = CloudflareStreamClient()


def parse_playback_urls(video: dict[str, Any]) -> dict[str, str]:
    """Normalise the playback fields Cloudflare returns.

    Never used for authorization -- the signed token produced in
    ``build_signed_playback`` is what actually unlocks the stream.
    """
    playback = video.get("playback") or {}
    hls = playback.get("hls") or video.get("hls") or ""
    dash = playback.get("dash") or video.get("dash") or ""
    return {"hls": hls, "dash": dash}


def dumps(value: dict[str, Any]) -> str:  # pragma: no cover - debug helper
    return json.dumps(value, indent=2, default=str)
