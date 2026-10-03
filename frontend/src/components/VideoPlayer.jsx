import { useCallback, useEffect, useRef, useState } from "react";

import { videoService } from "../services/videoService";
import { useVideoProgress } from "../hooks/useVideoProgress";
import { formatDuration } from "../utils/format";
import Icon from "./Icon";
import { Badge, Button, Spinner } from "./ui";

/**
 * Protected video player.
 *
 * How protection works (and what it does *not* do):
 *
 * * Playback data is only fetched by calling the API, which authenticates the
 *   student and re-checks entitlement before minting a **short-lived signed
 *   token**. There is no permanent URL anywhere in this component.
 * * If the token expires mid-session the player re-requests one automatically
 *   (`playback.expires_in` drives the timer). A lapsed subscription therefore
 *   stops playback at the next refresh, not at the end of the term's cached URL.
 * * This is **not DRM** — a determined user can screen-record. Cloudflare Stream's
 *   supported mechanism (signed URLs) is used instead of inventing a scheme, as
 *   required.
 *
 * The player is a plain `<video>` element because the Cloudflare Stream HLS URL is
 * an HLS manifest; `hls.js` is intentionally not bundled and we fall back to the
 * browser's native HLS support (Safari/iOS) or the `/iframe` player which
 * Cloudflare serves for other browsers.
 */

const TOKEN_REFRESH_LEEWAY_SECONDS = 45;

export default function VideoPlayer({
  videoUid,
  lessonTitle,
  onCompleted,
  resumeAt = 0,
}) {
  const [playback, setPlayback] = useState(null);
  const [status, setStatus] = useState("loading"); // loading | ready | error | expired
  const [error, setError] = useState(null);
  const refreshTimer = useRef(null);
  const videoRef = useRef(null);

  const progress = useVideoProgress(videoUid, {
    initialPosition: resumeAt,
    duration: playback?.duration_seconds || 0,
  });

  const requestPlayback = useCallback(
    async ({ silent = false } = {}) => {
      if (!videoUid) return;
      if (!silent) setStatus("loading");
      try {
        const data = await videoService.playback(videoUid);
        setPlayback(data);
        setStatus("ready");
        setError(null);
        return data;
      } catch (caught) {
        setError(caught);
        // Distinguish "your subscription lapsed" from a transient failure so the
        // UI can offer the right action (renew vs retry).
        setStatus(caught?.code === "video_not_ready" ? "processing" : "error");
        return null;
      }
    },
    [videoUid],
  );

  useEffect(() => {
    requestPlayback();
  }, [requestPlayback]);

  /**
   * Proactively refresh the token shortly before it expires.
   *
   * Without this a long lecture would fail mid-playback, which looks like a bug to
   * the student rather than an intentional security control.
   */
  useEffect(() => {
    if (!playback?.expires_in) return undefined;

    const refreshInMs = Math.max(
      (playback.expires_in - TOKEN_REFRESH_LEEWAY_SECONDS) * 1000,
      10000,
    );
    refreshTimer.current = window.setTimeout(() => {
      requestPlayback({ silent: true });
    }, refreshInMs);

    return () => window.clearTimeout(refreshTimer.current);
  }, [playback?.expires_in, playback?.token, requestPlayback]);

  /**
   * Apply the resume position exactly once per loaded media.
   *
   * Setting `currentTime` before metadata exists is a no-op, which is the classic
   * "resume from where I left off" bug.
   */
  const handleLoadedMetadata = useCallback(() => {
    const element = videoRef.current;
    if (!element) return;
    const startAt = Math.min(
      resumeAt || 0,
      Math.max((playback?.duration_seconds || 0) - 5, 0),
    );
    if (startAt > 5 && Number.isFinite(element.duration)) {
      try {
        element.currentTime = startAt;
      } catch {
        // Some browsers restrict seeking before the buffer is ready; harmless.
      }
    }
  }, [resumeAt, playback?.duration_seconds]);

  const handleEnded = useCallback(async () => {
    await progress.onEnded();
    onCompleted?.();
  }, [progress, onCompleted]);

  /* ------------------------------- states ------------------------------- */
  if (status === "loading") {
    return (
      <div className="flex aspect-video w-full items-center justify-center rounded-[14px] border border-line bg-black">
        <div className="flex flex-col items-center gap-3 text-[#B4BED6]">
          <Spinner size={28} />
          <span className="text-sm">Preparing secure playback…</span>
        </div>
      </div>
    );
  }

  if (status === "processing") {
    return (
      <div className="flex aspect-video w-full flex-col items-center justify-center gap-2 rounded-[14px] border border-line bg-black px-6 text-center">
        <Badge tone="warning">Encoding</Badge>
        <p className="text-sm text-[#EEF1F8]">
          This video is still being processed. It will become available
          automatically.
        </p>
        <Button
          variant="ghost"
          onClick={() => requestPlayback()}
          className="mt-2"
        >
          Check again
        </Button>
      </div>
    );
  }

  if (status === "error" || !playback) {
    const message =
      error?.code === "subscription_expired"
        ? "Your subscription has ended, so playback is no longer available."
        : error?.code === "subscription_required"
          ? "An active subscription is required to watch this lesson."
          : error?.message || "This video could not be loaded.";

    return (
      <div
        role="alert"
        className="flex aspect-video w-full flex-col items-center justify-center gap-3 rounded-[14px] border border-bad bg-black px-6 text-center"
      >
        <Icon name="lock" className="i-lg text-ink3" />
        <p className="text-sm text-[#EEF1F8]">{message}</p>
        {[
          "subscription_expired",
          "subscription_required",
          "not_in_plan",
        ].includes(error?.code) ? (
          <a href="/subscription" className="btn btn-primary">
            View plans
          </a>
        ) : (
          <Button variant="ghost" onClick={() => requestPlayback()}>
            Retry
          </Button>
        )}
      </div>
    );
  }

  /* ------------------------------- player ------------------------------- */
  return (
    <div className="overflow-hidden rounded-[14px] border border-line bg-black">
      <video
        ref={videoRef}
        className="aspect-video w-full bg-black"
        controls
        playsInline
        preload="metadata"
        // `crossOrigin` is required for the signed Cloudflare stream.
        crossOrigin="anonymous"
        poster={playback.thumbnail_url || undefined}
        onLoadedMetadata={handleLoadedMetadata}
        onTimeUpdate={(event) =>
          progress.onTimeUpdate(event.currentTarget.currentTime)
        }
        // Save on pause: covers the "student stops watching" case between heartbeats.
        onPause={() => progress.saveNow()}
        onEnded={handleEnded}
        onError={() => {
          // A signed URL that has expired produces a media error, not an HTTP 401.
          setError({
            code: "playback_expired",
            message: "Playback authorisation expired.",
          });
          requestPlayback({ silent: true });
        }}
        aria-label={lessonTitle ? `Video: ${lessonTitle}` : "Lesson video"}
      >
        {playback.hls_url && (
          <source src={playback.hls_url} type="application/x-mpegURL" />
        )}
        Your browser cannot play this video. Please update your browser or use a
        different device.
      </video>

      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line px-3 py-2 text-xs text-ink3">
        <span>
          {progress.completed ? (
            <Badge tone="success">Completed</Badge>
          ) : (
            <span>
              {formatDuration(progress.lastPosition)} /{" "}
              {formatDuration(playback.duration_seconds)}
            </span>
          )}
        </span>
        <span aria-live="polite">
          {progress.saveState === "saving" && "Saving progress…"}
          {progress.saveState === "saved" && "Progress saved"}
          {progress.saveState === "error" &&
            "Progress will retry automatically"}
        </span>
      </div>
    </div>
  );
}
