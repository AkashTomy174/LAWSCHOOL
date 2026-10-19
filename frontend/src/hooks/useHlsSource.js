import { useEffect, useRef } from "react";

const NATIVE_HLS_TYPE = "application/vnd.apple.mpegurl";

/**
 * Attach an HLS manifest URL to a <video> element.
 *
 * * Safari/iOS (and any browser that reports native HLS support) just gets `src`.
 * * Everything else (Firefox, most Chromium builds) lazy-loads hls.js, so the
 *   library is only downloaded when it is actually needed and never for Safari.
 * * The URL embeds a short-lived signed token. When it changes (token refresh) the
 *   previous source is torn down and the new one resumes from the same position.
 * * Nothing here logs or stores the URL, and every instance is destroyed on
 *   unmount / URL change so no network loop outlives the component.
 *
 * `onError(code)` receives "unsupported" or "fatal" and never the URL.
 */
export default function useHlsSource(videoRef, url, { onError } = {}) {
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !url) return undefined;

    let cancelled = false;
    let hls = null;
    const resumeAt = Number.isFinite(video.currentTime) ? video.currentTime : 0;

    const restorePosition = () => {
      if (resumeAt > 1) {
        try {
          video.currentTime = resumeAt;
        } catch {
          // Seeking before the buffer is ready is harmless to skip.
        }
      }
    };

    if (video.canPlayType?.(NATIVE_HLS_TYPE)) {
      video.src = url;
      video.addEventListener("loadedmetadata", restorePosition, { once: true });
      return () => {
        cancelled = true;
        video.removeEventListener("loadedmetadata", restorePosition);
      };
    }

    import("hls.js")
      .then(({ default: Hls }) => {
        if (cancelled) return;
        if (!Hls.isSupported()) {
          onErrorRef.current?.("unsupported");
          return;
        }
        hls = new Hls({ enableWorker: true });
        hls.on(Hls.Events.MANIFEST_PARSED, restorePosition);
        hls.on(Hls.Events.ERROR, (_event, data) => {
          if (!data?.fatal) return;
          if (data.type === Hls.ErrorTypes.NETWORK_ERROR && !cancelled) {
            // An expired or invalid token surfaces here as a fatal network error;
            // let the caller mint a fresh one rather than hammering the same URL.
            onErrorRef.current?.("fatal");
          } else if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
            hls.recoverMediaError();
          } else {
            onErrorRef.current?.("fatal");
          }
        });
        hls.loadSource(url);
        hls.attachMedia(video);
      })
      .catch(() => {
        if (!cancelled) onErrorRef.current?.("unsupported");
      });

    return () => {
      cancelled = true;
      if (hls) {
        hls.destroy();
        hls = null;
      }
      video.removeAttribute("src");
    };
  }, [videoRef, url]);
}
