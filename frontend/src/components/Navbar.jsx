import { useEffect, useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../context/AuthContext";
import { useUI } from "../context/UIContext";
import { initials } from "../utils/format";
import Icon from "./Icon";

/**
 * Application header.
 *
 * Links shown depend on who is signed in, but they are only navigation: every
 * protected page and endpoint re-checks authorisation on its own. Below `lg` the
 * links collapse behind a disclosure button, and the menu closes on navigation so
 * a student is never left staring at an open overlay on the next page.
 */

const publicLinks = [
  { to: "/courses", label: "Courses" },
  { to: "/subscription", label: "Plans" },
  { to: "/leaderboard", label: "Leaderboard" },
];

const studentLinks = [
  { to: "/courses", label: "Courses" },
  { to: "/dashboard", label: "Dashboard" },
  { to: "/subscription", label: "Plans" },
  { to: "/leaderboard", label: "Leaderboard" },
];

const staffLinks = [{ to: "/admin", label: "Admin" }];

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
    ...(isAuthenticated ? studentLinks : publicLinks),
    ...(isAdmin || isInstructor ? staffLinks : []),
  ];

  const linkClass = ({ isActive }) => (isActive ? "on" : undefined);

  return (
    <header className="sticky top-0 z-40 border-b border-line bg-page">
      <div className="wrap">
        <div className="nav">
          <div className="flex items-center gap-12">
            <Link to="/" className="brand">
              <span className="brand-mark">§</span>LawSchool
            </Link>

            <nav aria-label="Main" className="nav-links hidden lg:flex">
              {links.map((link) => (
                <NavLink key={link.to} to={link.to} className={linkClass}>
                  {link.label}
                </NavLink>
              ))}
            </nav>
          </div>

          <div className="flex items-center gap-3">
            {isAuthenticated ? (
              <>
                <Link
                  to="/notifications"
                  className="relative hidden h-11 w-11 items-center justify-center rounded-lg text-ink2 hover:bg-sunken sm:flex"
                  aria-label={
                    unreadCount > 0
                      ? `Notifications, ${unreadCount} unread`
                      : "Notifications"
                  }
                >
                  <Icon name="bell" className="i-lg" />
                  {unreadCount > 0 && (
                    <span
                      className="absolute right-2 top-2 h-[9px] w-[9px] rounded-full border-2 border-page bg-gold"
                      aria-hidden="true"
                    />
                  )}
                </Link>

                <Link
                  to="/profile"
                  className="hidden items-center sm:flex"
                  aria-label={`Profile: ${user?.name || "your account"}`}
                >
                  <span className="avatar">{initials(user?.name)}</span>
                </Link>

                <button
                  type="button"
                  onClick={handleLogout}
                  className="btn btn-line hidden sm:inline-flex"
                >
                  Sign out
                </button>
              </>
            ) : (
              <>
                <Link to="/login" className="btn btn-line hidden sm:inline-flex">
                  Sign in
                </Link>
                <Link to="/register" className="btn btn-gold">
                  Start free
                </Link>
              </>
            )}

            <button
              type="button"
              className="btn btn-line !w-11 !px-0 lg:hidden"
              aria-expanded={open}
              aria-controls="mobile-menu"
              aria-label={open ? "Close menu" : "Open menu"}
              onClick={() => setOpen((value) => !value)}
            >
              <Icon name={open ? "x" : "caretDown"} />
            </button>
          </div>
        </div>
      </div>

      {open && (
        <div id="mobile-menu" className="border-t border-line lg:hidden">
          <nav
            aria-label="Mobile"
            className="wrap nav-links flex-col !gap-0 py-3"
          >
            {links.map((link) => (
              <NavLink key={link.to} to={link.to} className={linkClass}>
                {link.label}
              </NavLink>
            ))}
            {isAuthenticated ? (
              <>
                <NavLink to="/notifications">
                  Notifications{unreadCount > 0 ? ` (${unreadCount})` : ""}
                </NavLink>
                <NavLink to="/profile">Profile</NavLink>
                <button
                  type="button"
                  onClick={handleLogout}
                  className="flex h-11 items-center rounded-lg px-3 text-left text-[15px] text-bad"
                >
                  Sign out
                </button>
              </>
            ) : (
              <NavLink to="/login">Sign in</NavLink>
            )}
          </nav>
        </div>
      )}
    </header>
  );
}
