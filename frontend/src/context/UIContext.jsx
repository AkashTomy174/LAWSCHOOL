import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { notificationService } from "../services/quizService";
import { useAuth } from "./AuthContext";

/**
 * Lightweight UI concerns that genuinely are global: toast messages and the
 * unread notification badge.
 *
 * Server data (courses, progress, payments) is deliberately NOT cached here —
 * each page fetches what it needs, which keeps this context small and avoids
 * stale-data bugs after a mutation.
 */

const UIContext = createContext(null);

export function UIProvider({ children }) {
  const { isAuthenticated } = useAuth();
  const [toasts, setToasts] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);

  const pushToast = useCallback(
    ({ message, tone = "info", timeout = 4500 }) => {
      const id = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
      setToasts((current) => [...current, { id, message, tone }]);
      if (timeout) {
        window.setTimeout(() => {
          setToasts((current) => current.filter((toast) => toast.id !== id));
        }, timeout);
      }
      return id;
    },
    [],
  );

  const dismissToast = useCallback((id) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const refreshUnread = useCallback(async () => {
    if (!isAuthenticated) {
      setUnreadCount(0);
      return;
    }
    try {
      const data = await notificationService.unreadCount();
      setUnreadCount(data.unread || 0);
    } catch {
      // A failed badge refresh is not worth surfacing to the student.
    }
  }, [isAuthenticated]);

  // Poll for the badge instead of opening a websocket: one cheap indexed COUNT a
  // minute is far simpler than a push channel, and the badge is not time-critical.
  useEffect(() => {
    refreshUnread();
    if (!isAuthenticated) return undefined;
    const interval = window.setInterval(refreshUnread, 60000);
    return () => window.clearInterval(interval);
  }, [isAuthenticated, refreshUnread]);

  const value = useMemo(
    () => ({
      toasts,
      pushToast,
      dismissToast,
      unreadCount,
      refreshUnread,
      setUnreadCount,
    }),
    [toasts, pushToast, dismissToast, unreadCount, refreshUnread],
  );

  return <UIContext.Provider value={value}>{children}</UIContext.Provider>;
}

export function useUI() {
  const context = useContext(UIContext);
  if (!context) throw new Error("useUI must be used inside a <UIProvider>.");
  return context;
}

export { UIContext };
