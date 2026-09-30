import { useCallback, useEffect, useRef, useState } from "react";

import { videoService } from "../services/videoService";

/**
 * Progress reporting for the video player.
 *
 * Requirements this satisfies:
 * * send updates every 10-30s (here: 15s) rather than every second;
 * * send a final update when the video ends or the page is left;
 * * never send a value the server would reject — positions are clamped and the
 *   "furthest watched" value is monotonic;
 * * keep the last known position so playback resumes where the student stopped.
 */

const HEARTBEAT_MS = 15000;
/** How close to the end counts as "finished" for the completion signal. */
const COMPLETION_THRESHOLD_SECONDS = 2;

export function useVideoProgress(
  videoUid,
  { initialPosition = 0, duration = 0 } = {},
) {
  const [lastPosition, setLastPosition] = useState(initialPosition || 0);
  const [furthestPosition, setFurthestPosition] = useState(
    initialPosition || 0,
  );
  const [completed, setCompleted] = useState(false);
  const [saveState, setSaveState] = useState("idle"); // idle | saving | saved | error

  // Refs, not state: the interval callback and the unload handler must read the
  // current position without being re-created on every timeupdate.
  const currentPositionRef = useRef(initialPosition || 0);
  const furthestRef = useRef(initialPosition || 0);
  const lastSentRef = useRef(initialPosition || 0);
  const completedRef = useRef(false);
  const durationRef = useRef(duration || 0);
  const inFlightRef = useRef(false);

  useEffect(() => {
    durationRef.current = duration || 0;
  }, [duration]);

  const send = useCallback(
    async ({ force = false, markComplete = false } = {}) => {
      if (!videoUid) return;
      const position = Math.max(0, Math.round(currentPositionRef.current));

      // Skip no-op heartbeats but always honour a forced final update.
      if (!force && !markComplete && position === lastSentRef.current) return;
      if (inFlightRef.current && !force) return;

      // The server clamps against the real duration; clamp here too so we never
      // send a value that is obviously impossible.
      const ceiling = durationRef.current ? durationRef.current + 2 : position;
      const safePosition = Math.min(position, Math.ceil(ceiling));

      inFlightRef.current = true;
      setSaveState("saving");
      try {
        const result = await videoService.updateProgress(videoUid, {
          positionSeconds: safePosition,
          watchedSeconds: Math.max(furthestRef.current, safePosition),
          completed: markComplete || completedRef.current,
        });
        lastSentRef.current = position;
        setSaveState("saved");
        if (result?.completed) completedRef.current = true;
        return result;
      } catch {
        // A dropped heartbeat is not user-facing; the next one will catch up.
        setSaveState("error");
        return null;
      } finally {
        inFlightRef.current = false;
      }
    },
    [videoUid],
  );

  /** Called from the player's `timeupdate`. Cheap — no network. */
  const onTimeUpdate = useCallback((seconds) => {
    const value = Math.max(0, Number(seconds) || 0);
    currentPositionRef.current = value;
    setLastPosition(value);
    if (value > furthestRef.current) {
      furthestRef.current = value;
      setFurthestPosition(value);
    }
  }, []);

  /** Registered on the player's `ended` event and on page unload. */
  const onEnded = useCallback(async () => {
    completedRef.current = true;
    setCompleted(true);
    await send({ force: true, markComplete: true });
  }, [send]);

  // Heartbeat.
  useEffect(() => {
    if (!videoUid) return undefined;
    const interval = window.setInterval(() => send(), HEARTBEAT_MS);
    return () => window.clearInterval(interval);
  }, [videoUid, send]);

  /**
   * Final update when the student navigates away or closes the tab.
   *
   * `visibilitychange` fires reliably on mobile where `beforeunload` often does
   * not; `sendBeacon` would need a token the interceptor cannot attach, so a
   * plain (non-awaited) request is used — the server tolerates a lost request.
   */
  useEffect(() => {
    if (!videoUid) return undefined;

    const flush = () => {
      const nearEnd =
        durationRef.current > 0 &&
        currentPositionRef.current >=
          durationRef.current - COMPLETION_THRESHOLD_SECONDS;
      send({ force: true, markComplete: nearEnd });
    };

    const onVisibility = () => {
      if (document.visibilityState === "hidden") flush();
    };

    window.addEventListener("beforeunload", flush);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.removeEventListener("beforeunload", flush);
      document.removeEventListener("visibilitychange", onVisibility);
      flush();
    };
  }, [videoUid, send]);

  return {
    lastPosition,
    furthestPosition,
    completed,
    saveState,
    onTimeUpdate,
    onEnded,
    /** Manual save, e.g. when the student pauses. */
    saveNow: () => send({ force: true }),
  };
}

export default useVideoProgress;
