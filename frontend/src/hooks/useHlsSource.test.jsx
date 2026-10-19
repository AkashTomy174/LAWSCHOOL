import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const hlsInstances = [];

vi.mock("hls.js", () => {
  class FakeHls {
    static isSupported = vi.fn(() => true);
    static Events = { MANIFEST_PARSED: "manifest", ERROR: "error" };
    static ErrorTypes = { NETWORK_ERROR: "network", MEDIA_ERROR: "media" };
    constructor() {
      this.handlers = {};
      this.loadSource = vi.fn();
      this.attachMedia = vi.fn();
      this.destroy = vi.fn();
      this.recoverMediaError = vi.fn();
      hlsInstances.push(this);
    }
    on(name, fn) {
      this.handlers[name] = fn;
    }
  }
  return { default: FakeHls };
});

import Hls from "hls.js";
import useHlsSource from "./useHlsSource";

function makeVideo({ native }) {
  const video = document.createElement("video");
  video.canPlayType = vi.fn(() => (native ? "maybe" : ""));
  return video;
}

const URL1 = "https://customer-x.cloudflarestream.com/TOKEN1/manifest/video.m3u8";
const URL2 = "https://customer-x.cloudflarestream.com/TOKEN2/manifest/video.m3u8";

describe("useHlsSource", () => {
  beforeEach(() => {
    hlsInstances.length = 0;
    Hls.isSupported.mockReturnValue(true);
  });

  it("uses native playback when the browser supports HLS (no hls.js instance)", () => {
    const video = makeVideo({ native: true });
    renderHook(() => useHlsSource({ current: video }, URL1));
    expect(video.src).toBe(URL1);
    expect(hlsInstances).toHaveLength(0);
  });

  it("falls back to hls.js when native HLS is unavailable", async () => {
    const video = makeVideo({ native: false });
    renderHook(() => useHlsSource({ current: video }, URL1));
    await waitFor(() => expect(hlsInstances).toHaveLength(1));
    expect(hlsInstances[0].loadSource).toHaveBeenCalledWith(URL1);
    expect(hlsInstances[0].attachMedia).toHaveBeenCalledWith(video);
  });

  it("destroys the hls.js instance on unmount", async () => {
    const video = makeVideo({ native: false });
    const { unmount } = renderHook(() => useHlsSource({ current: video }, URL1));
    await waitFor(() => expect(hlsInstances).toHaveLength(1));
    unmount();
    expect(hlsInstances[0].destroy).toHaveBeenCalled();
  });

  it("tears down and reloads when the signed URL is refreshed", async () => {
    const video = makeVideo({ native: false });
    const ref = { current: video };
    const { rerender } = renderHook(({ url }) => useHlsSource(ref, url), {
      initialProps: { url: URL1 },
    });
    await waitFor(() => expect(hlsInstances).toHaveLength(1));
    rerender({ url: URL2 });
    await waitFor(() => expect(hlsInstances).toHaveLength(2));
    expect(hlsInstances[0].destroy).toHaveBeenCalled();
    expect(hlsInstances[1].loadSource).toHaveBeenCalledWith(URL2);
  });

  it("does nothing without a URL", () => {
    const video = makeVideo({ native: false });
    renderHook(() => useHlsSource({ current: video }, null));
    expect(hlsInstances).toHaveLength(0);
    expect(video.getAttribute("src")).toBeNull();
  });

  it("reports unsupported when hls.js cannot run here", async () => {
    Hls.isSupported.mockReturnValue(false);
    const onError = vi.fn();
    renderHook(() => useHlsSource({ current: makeVideo({ native: false }) }, URL1, { onError }));
    await waitFor(() => expect(onError).toHaveBeenCalledWith("unsupported"));
    expect(hlsInstances).toHaveLength(0);
  });

  it("asks the caller for a fresh token on a fatal network error, without leaking the URL", async () => {
    const onError = vi.fn();
    renderHook(() => useHlsSource({ current: makeVideo({ native: false }) }, URL1, { onError }));
    await waitFor(() => expect(hlsInstances).toHaveLength(1));
    hlsInstances[0].handlers.error("error", { fatal: true, type: "network" });
    expect(onError).toHaveBeenCalledWith("fatal");
    expect(JSON.stringify(onError.mock.calls)).not.toContain("TOKEN1");
  });

  it("recovers media errors in place and ignores non-fatal ones", async () => {
    const onError = vi.fn();
    renderHook(() => useHlsSource({ current: makeVideo({ native: false }) }, URL1, { onError }));
    await waitFor(() => expect(hlsInstances).toHaveLength(1));
    hlsInstances[0].handlers.error("error", { fatal: false, type: "network" });
    hlsInstances[0].handlers.error("error", { fatal: true, type: "media" });
    expect(hlsInstances[0].recoverMediaError).toHaveBeenCalled();
    expect(onError).not.toHaveBeenCalled();
  });
});
