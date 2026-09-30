import { useEffect, useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../context/AuthContext";
import { useUI } from "../context/UIContext";
import { Avatar, Button } from "./ui";

/**
 * Application header.
 *
 * Mobile-first: the primary navigation collapses behind a disclosure button below
 * the `md` breakpoint, and the menu closes on navigation so the student is not
 * left staring at an open overlay on the next page.
 */

const studentLinks = [
  { to: "/courses", label: "Courses" },
  { to: "/dashboard", label: "Dashboard" },
  { to: "/leaderboard", label: "Leaderboard" },
  { to: "/subscription", label: "Subscription" },
];

const staffLinks = [
  { to: "/admin", label: "Admin" },
  { to: "/admin/courses", label: "Courses" },
  { to: "/admin/videos", label: "Videos" },
];

export default function Navbar() {
  const { user, isAuthenticated, logout, isAdmin, isInstructor } = useAuth();
  const { unreadCount } = useUI();
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    setOpen(false);
  }, [location.pathname]);

  async function handleLogout() {
    await logout();
    navigate("/", { replace: true });
  }

  const links = [
    ...studentLinks,
    ...(isAdmin || isInstructor ? staffLinks : []),
  ];

  return (
    <header className="sticky top-0 z-40 border-b border-[var(--color-border-subtle)] bg-[rgba(6,11,26,0.86)] backdrop-blur-md">
      {/* Skip link: the first focusable element, for keyboard/screen-reader users. */}
      <a
        href="#main-content"
        className="sr-only-focusable absolute left-3 top-3 z-50 rounded bg-gold-500 px-3 py-2 text-sm font-semibold text-black"
      >
        Skip to main content
      </a>

      <nav
        className="mx-auto flex w-full max-w-7xl items-center justify-between gap-3 px-4 py-3"
        aria-label="Main"
      >
        <Link
          to="/"
          className="font-display text-lg tracking-wide text-gold-300 md:text-xl"
        >
          Law<span className="text-parchment">School</span>
        </Link>

        {/* Desktop navigation */}
        <ul className="hidden items-center gap-1 md:flex">
          {links.map((link) => (
            <li key={link.to}>
              <NavLink
                to={link.to}
                className={({ isActive }) =>
                  `rounded-full px-3 py-2 text-sm transition-colors ${
                    isActive
                      ? "bg-white/10 text-gold-300"
                      : "text-white/75 hover:text-gold-300"
                  }`
                }
              >
                {link.label}
              </NavLink>
            </li>
          ))}
        </ul>

        <div className="flex items-center gap-2">
          {isAuthenticated ? (
            <>
              <Link
                to="/notifications"
                className="relative hidden rounded-full p-2 text-white/75 hover:text-gold-300 sm:block"
                aria-label={
                  unreadCount > 0
                    ? `Notifications, ${unreadCount} unread`
                    : "Notifications"
                }
              >
                <span aria-hidden="true">{"\u{1F514}"}</span>
                {unreadCount > 0 && (
                  <span className="absolute -right-0 top-0 min-w-[18px] rounded-full bg-gold-500 px-1 text-center text-[10px] font-bold leading-[18px] text-black">
                    {unreadCount > 9 ? "9+" : unreadCount}
                  </span>
                )}
              </Link>

              <Link
                to="/profile"
                className="hidden items-center gap-2 rounded-full px-2 py-1 hover:bg-white/5 sm:flex"
              >
                <Avatar user={user} size={30} />
                <span className="max-w-[110px] truncate text-sm text-white/80">
                  {user?.name}
                </span>
              </Link>

              <Button
                variant="ghost"
                onClick={handleLogout}
                className="hidden !min-h-0 !px-3 !py-2 text-sm sm:inline-flex"
              >
                Sign out
              </Button>
            </>
          ) : (
            <>
              <Link
                to="/login"
                className="hidden text-sm text-white/80 hover:text-gold-300 sm:block"
              >
                Sign in
              </Link>
              <Link
                to="/register"
                className="btn btn-primary !min-h-0 !py-2 text-sm"
              >
                Get started
              </Link>
            </>
          )}

          <button
            type="button"
            className="rounded-lg border border-[var(--color-border-subtle)] p-2 md:hidden"
            aria-expanded={open}
            aria-controls="mobile-menu"
            aria-label={open ? "Close menu" : "Open menu"}
            onClick={() => setOpen((value) => !value)}
          >
            <span aria-hidden="true">{open ? "\u2715" : "\u2630"}</span>
          </button>
        </div>
      </nav>

      {open && (
        <div
          id="mobile-menu"
          className="border-t border-[var(--color-border-subtle)] md:hidden"
        >
          <ul className="mx-auto flex w-full max-w-7xl flex-col gap-1 px-4 py-3">
            {links.map((link) => (
              <li key={link.to}>
                <NavLink
                  to={link.to}
                  className={({ isActive }) =>
                    `block rounded-lg px-3 py-3 text-sm ${
                      isActive ? "bg-white/10 text-gold-300" : "text-white/80"
                    }`
                  }
                >
                  {link.label}
                </NavLink>
              </li>
            ))}
            {isAuthenticated ? (
              <>
                <li>
                  <NavLink
                    to="/notifications"
                    className="block rounded-lg px-3 py-3 text-sm text-white/80"
                  >
                    Notifications{unreadCount > 0 ? ` (${unreadCount})` : ""}
                  </NavLink>
                </li>
                <li>
                  <NavLink
                    to="/profile"
                    className="block rounded-lg px-3 py-3 text-sm text-white/80"
                  >
                    Profile
                  </NavLink>
                </li>
                <li>
                  <button
                    type="button"
                    onClick={handleLogout}
                    className="block w-full rounded-lg px-3 py-3 text-left text-sm text-red-300"
                  >
                    Sign out
                  </button>
                </li>
              </>
            ) : (
              <li>
                <NavLink
                  to="/login"
                  className="block rounded-lg px-3 py-3 text-sm text-white/80"
                >
                  Sign in
                </NavLink>
              </li>
            )}
          </ul>
        </div>
      )}
    </header>
  );
}
