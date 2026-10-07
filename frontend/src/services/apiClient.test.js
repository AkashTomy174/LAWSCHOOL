import axios from "axios";
import { afterEach, describe, expect, it, vi } from "vitest";

import { refreshAccessToken, tokenStore } from "./apiClient";

/**
 * Regression guard: refresh tokens rotate and the old one is blacklisted, so two
 * tabs refreshing with the same token used to log the second tab out.  The
 * refresh now runs under a cross-tab lock and reuses another tab's result.
 */
describe("refreshAccessToken", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    delete navigator.locks;
    tokenStore.clear();
  });

  it("reuses tokens another tab rotated while waiting for the lock", async () => {
    tokenStore.set({ access: "old-access", refresh: "old-refresh" });
    const post = vi.spyOn(axios, "post");
    navigator.locks = {
      request: async (_name, callback) => {
        // Another tab finishes its refresh before we get the lock.
        tokenStore.set({ access: "new-access", refresh: "new-refresh" });
        return callback();
      },
    };

    await expect(refreshAccessToken()).resolves.toBe("new-access");
    expect(post).not.toHaveBeenCalled();
  });

  it("refreshes normally when no other tab has rotated", async () => {
    tokenStore.set({ access: "old-access", refresh: "old-refresh" });
    vi.spyOn(axios, "post").mockResolvedValue({
      data: { access: "fresh-access", refresh: "fresh-refresh" },
    });

    await expect(refreshAccessToken()).resolves.toBe("fresh-access");
    expect(tokenStore.getRefresh()).toBe("fresh-refresh");
  });
});
