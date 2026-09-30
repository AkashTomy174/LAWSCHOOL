import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { authService } from "../services/authService";
import { setSessionExpiredHandler, tokenStore } from "../services/apiClient";

/**
 * Authentication + identity state.
 *
 * Scope is deliberately narrow: this context owns *who is signed in*, nothing
 * else. Course lists, progress and payments are fetched by the pages that need
 * them (via hooks), because stuffing server data into a global store would mean
 * re-fetching everything on every navigation.
 *
 * Route protection here is a **UX affordance only**. The server enforces every
 * permission independently; a student who edits the URL or the JS state still
 * gets a 403 from Django.
 */

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [status, setStatus] = useState("loading"); // loading | authenticated | anonymous
  const [error, setError] = useState(null);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const clearSession = useCallback(() => {
    tokenStore.clear();
    setUser(null);
    setStatus("anonymous");
  }, []);

  // When the axios interceptor cannot refresh the token, the session is over.
  useEffect(() => {
    setSessionExpiredHandler(() => {
      if (mounted.current) clearSession();
    });
    return () => setSessionExpiredHandler(() => {});
  }, [clearSession]);

  /** Resolve the session once on boot, using the stored token if present. */
  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      if (!tokenStore.hasSession()) {
        if (!cancelled) setStatus("anonymous");
        return;
      }
      try {
        const profile = await authService.me();
        if (cancelled) return;
        setUser(profile);
        setStatus("authenticated");
      } catch {
        // An expired/invalid token means: no session. Not an error to show.
        if (!cancelled) clearSession();
      }
    }

    bootstrap();
    return () => {
      cancelled = true;
    };
  }, [clearSession]);

  const login = useCallback(async ({ email, password }) => {
    setError(null);
    const data = await authService.login({ email, password });
    setUser(data.user);
    setStatus("authenticated");
    return data.user;
  }, []);

  const register = useCallback(async (payload) => {
    setError(null);
    const data = await authService.register(payload);
    setUser(data.user);
    setStatus("authenticated");
    return data.user;
  }, []);

  const logout = useCallback(async () => {
    await authService.logout();
    clearSession();
  }, [clearSession]);

  /** Re-read the profile after a PATCH so the whole app sees fresh data. */
  const refreshUser = useCallback(async () => {
    try {
      const profile = await authService.me();
      setUser(profile);
      return profile;
    } catch {
      return null;
    }
  }, []);

  const hasRole = useCallback(
    (...roles) => Boolean(user && roles.includes(user.role)),
    [user],
  );

  const value = useMemo(
    () => ({
      user,
      status,
      error,
      setError,
      isAuthenticated: status === "authenticated",
      isStudent: user?.role === "student",
      isInstructor: user?.role === "instructor",
      isAdmin: user?.role === "admin",
      hasRole,
      login,
      register,
      logout,
      refreshUser,
      updateUser: setUser,
    }),
    [user, status, error, hasRole, login, register, logout, refreshUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside an <AuthProvider>.");
  }
  return context;
}

export { AuthContext };
