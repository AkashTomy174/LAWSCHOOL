import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "../context/AuthContext";
import { Panel, Skeleton } from "./ui";

/**
 * Route guards.
 *
 * **These are UX affordances, not security controls.** Every protected endpoint
 * checks permissions server-side regardless of what the router allows; the guard
 * exists so a student is sent to the login page instead of seeing an empty
 * dashboard full of 403s.
 *
 * All three guards share one loading treatment, because a guard that renders
 * `null` while the session resolves makes the app look broken on a slow network.
 */

function SessionLoading() {
  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-16" aria-busy="true">
      <Skeleton className="h-8 w-48" />
      <Skeleton className="mt-6 h-32 w-full" />
      <span className="sr-only">Checking your session…</span>
    </div>
  );
}

/** Requires any signed-in user. */
export function RequireAuth() {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "loading") return <SessionLoading />;
  if (status !== "authenticated") {
    // Preserve the intended destination so login can bounce the student back.
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <Outlet />;
}

/** Requires one of the given roles (student cannot reach instructor surfaces). */
export function RequireRole({ roles }) {
  const { status, user } = useAuth();
  const location = useLocation();

  if (status === "loading") return <SessionLoading />;
  if (status !== "authenticated") {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  if (!roles.includes(user?.role)) {
    return (
      <div className="wrap flex flex-col items-start gap-5 py-24">
        <span className="mono cap">Access restricted</span>
        <h1 className="d2 !text-[44px]">Not available for your account</h1>
        <p className="lead">
          This area is restricted to {roles.join(" and ")} accounts. If you
          believe you should have access, contact the platform administrator.
        </p>
      </div>
    );
  }
  return <Outlet />;
}

/** Redirects an already-authenticated visitor away from login/register. */
export function RedirectIfAuthenticated() {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "loading") return <SessionLoading />;
  if (status === "authenticated") {
    const destination = location.state?.from || "/dashboard";
    return <Navigate to={destination} replace />;
  }
  return <Outlet />;
}

export default RequireAuth;
