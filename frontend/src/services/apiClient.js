import axios from "axios";

/**
 * Centralised HTTP client.
 *
 * Design decisions:
 *
 * * **One axios instance for the whole app.** Components and hooks never call
 *   `fetch`/`axios` directly, so auth headers, error shapes and base URLs are
 *   handled in exactly one place.
 * * **Base URL defaults to the same origin** (`/api/v1`). Combined with the Vite
 *   dev proxy this means no CORS preflight in development and no cross-origin
 *   token leakage in production, where nginx serves both.
 * * **Single-flight refresh.** When several requests 401 at once (very common on
 *   a dashboard that fires three parallel calls), only *one* refresh request is
 *   made; the rest await the same promise. Without this, refresh-token rotation
 *   would break: the second concurrent refresh would use an already-blacklisted
 *   token and log the student out.
 * * **No token in localStorage by default preference.** Tokens live in
 *   localStorage because the API is JWT-based and the SPA is served from a
 *   different origin during development. The trade-off (XSS exposure) is
 *   documented in docs/architecture.md; the mitigation is a strict CSP plus
 *   short access-token lifetimes.
 */

const ACCESS_TOKEN_KEY = "lawschool.access";
const REFRESH_TOKEN_KEY = "lawschool.refresh";

export const tokenStore = {
  getAccess: () => localStorage.getItem(ACCESS_TOKEN_KEY),
  getRefresh: () => localStorage.getItem(REFRESH_TOKEN_KEY),
  set({ access, refresh }) {
    if (access) localStorage.setItem(ACCESS_TOKEN_KEY, access);
    if (refresh) localStorage.setItem(REFRESH_TOKEN_KEY, refresh);
  },
  clear() {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
  },
  hasSession() {
    return Boolean(localStorage.getItem(ACCESS_TOKEN_KEY));
  },
};

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "/api/v1",
  timeout: 20000,
  headers: { "Content-Type": "application/json" },
});

/* -------------------------------------------------------------------------- */
/* Request: attach the access token                                           */
/* -------------------------------------------------------------------------- */
apiClient.interceptors.request.use((config) => {
  const token = tokenStore.getAccess();
  if (token && !config.skipAuth) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

/* -------------------------------------------------------------------------- */
/* Response: normalise errors + transparently refresh                         */
/* -------------------------------------------------------------------------- */
const REFRESH_PATH = "/auth/refresh/";

let refreshPromise = null;
/** Called when refresh fails, so the auth context can clear state and redirect. */
let onSessionExpired = () => {};

export function setSessionExpiredHandler(handler) {
  onSessionExpired = handler;
}

/**
 * Normalise every failure into one shape the UI can rely on.
 *
 * The backend already returns `{error: {code, message, details}}`; this adds a
 * matching shape for network/timeout failures so components never have to branch
 * on `error.response === undefined`.
 */
export function toApiError(error) {
  if (error?.response) {
    const payload = error.response.data;
    const envelope = payload?.error;
    return {
      status: error.response.status,
      code: envelope?.code || "http_error",
      message: envelope?.message || "The request could not be completed.",
      details: envelope?.details || null,
      isNetworkError: false,
    };
  }
  if (error?.code === "ECONNABORTED") {
    return {
      status: 0,
      code: "timeout",
      message: "The server took too long to respond. Please try again.",
      details: null,
      isNetworkError: true,
    };
  }
  return {
    status: 0,
    code: "network_error",
    message: "Could not reach the server. Check your connection and try again.",
    details: null,
    isNetworkError: true,
  };
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config || {};
    const status = error.response?.status;

    const isAuthEndpoint =
      original.url?.includes("/auth/login/") ||
      original.url?.includes("/auth/register/") ||
      original.url?.includes(REFRESH_PATH);

    // A 401 on a normal request means the access token lapsed: try to refresh
    // exactly once, then replay the original request.
    if (
      status === 401 &&
      !original._retried &&
      !isAuthEndpoint &&
      tokenStore.getRefresh()
    ) {
      original._retried = true;
      try {
        const access = await refreshAccessToken();
        original.headers = {
          ...original.headers,
          Authorization: `Bearer ${access}`,
        };
        return apiClient(original);
      } catch {
        tokenStore.clear();
        onSessionExpired();
        return Promise.reject(toApiError(error));
      }
    }

    return Promise.reject(toApiError(error));
  },
);

/**
 * Exchange the refresh token for a new access token.
 *
 * Uses a bare axios call (not `apiClient`) so the interceptor above cannot
 * recurse, and deduplicates concurrent callers via `refreshPromise`.
 */
export async function refreshAccessToken() {
  if (refreshPromise) return refreshPromise;

  const refresh = tokenStore.getRefresh();
  if (!refresh) return Promise.reject(new Error("No refresh token available."));

  const baseURL = import.meta.env.VITE_API_BASE_URL || "/api/v1";
  refreshPromise = axios
    .post(`${baseURL}${REFRESH_PATH}`, { refresh })
    .then((response) => {
      // ROTATE_REFRESH_TOKENS is on server-side, so a new refresh token comes back
      // and the old one is blacklisted — both must be stored.
      tokenStore.set({
        access: response.data.access,
        refresh: response.data.refresh || refresh,
      });
      return response.data.access;
    })
    .finally(() => {
      refreshPromise = null;
    });

  return refreshPromise;
}

export default apiClient;
