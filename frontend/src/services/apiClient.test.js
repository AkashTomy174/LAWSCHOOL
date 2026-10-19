import axios from "axios";
import { afterEach, describe, expect, it, vi } from "vitest";

import apiClient, {
  refreshAccessToken,
  setSessionExpiredHandler,
  toApiError,
  tokenStore,
} from "./apiClient";

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

describe("toApiError", () => {
  it("reads the locked-lesson reason from the watch endpoint's 403", () => {
    const error = toApiError({
      response: {
        status: 403,
        data: { access: { reason: "subscription_required", detail: "Subscribe." } },
      },
    });
    expect(error.code).toBe("subscription_required");
    expect(error.message).toBe("Subscribe.");
  });
});

describe("session expiry", () => {
  it("ends the session on a 401 when there is no refresh token", async () => {
    tokenStore.clear(); // e.g. a password change just revoked the session
    const expired = vi.fn();
    setSessionExpiredHandler(expired);
    const adapter = (config) =>
      Promise.reject(
        Object.assign(new Error("401"), {
          config,
          response: { status: 401, data: {} },
        }),
      );

    await expect(apiClient.get("/auth/me/", { adapter })).rejects.toMatchObject({
      status: 401,
    });
    expect(expired).toHaveBeenCalledOnce();
    setSessionExpiredHandler(() => {});
  });
});

describe("toApiError keeps other errors intact", () => {
  it("prefers the standard error envelope", () => {
    const error = toApiError({
      response: {
        status: 403,
        data: { error: { code: "permission_denied", message: "Nope." }, access: { reason: "x" } },
      },
    });
    expect(error).toMatchObject({ code: "permission_denied", message: "Nope." });
  });

  it("falls back to a generic message for a bare server error", () => {
    expect(toApiError({ response: { status: 500, data: "<html>" } })).toMatchObject({
      status: 500,
      code: "http_error",
      message: "The request could not be completed.",
    });
  });
});

describe("concurrent 401s after the session is gone", () => {
  it("fail safely, never retry, and only end an already-ended session", async () => {
    tokenStore.clear();
    const expired = vi.fn();
    setSessionExpiredHandler(expired);
    const calls = vi.fn();
    const adapter = (config) => {
      calls();
      return Promise.reject(
        Object.assign(new Error("401"), { config, response: { status: 401, data: {} } }),
      );
    };

    const results = await Promise.allSettled(
      ["/a/", "/b/", "/c/"].map((url) => apiClient.get(url, { adapter })),
    );
    expect(results.every((r) => r.status === "rejected" && r.reason.status === 401)).toBe(true);
    expect(calls).toHaveBeenCalledTimes(3); // no replay without a refresh token
    expect(expired).toHaveBeenCalledTimes(3); // idempotent: clears state, never navigates
    expect(tokenStore.getRefresh()).toBeFalsy();
    setSessionExpiredHandler(() => {});
  });

  it("a failed login is not treated as an expired session", async () => {
    const expired = vi.fn();
    setSessionExpiredHandler(expired);
    const adapter = (config) =>
      Promise.reject(Object.assign(new Error("401"), { config, response: { status: 401, data: {} } }));
    await expect(apiClient.post("/auth/login/", {}, { adapter })).rejects.toMatchObject({ status: 401 });
    expect(expired).not.toHaveBeenCalled();
    setSessionExpiredHandler(() => {});
  });
});
