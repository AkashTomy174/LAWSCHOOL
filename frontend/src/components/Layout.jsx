import { useEffect } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";

import Footer from "./Footer";
import Icon from "./Icon";
import Navbar from "./Navbar";
import ToastHost from "./ToastHost";

/**
 * Where each theme applies.
 *
 * * Focus mode (lecture, quiz attempt): dark, and no site navigation at all, so
 *   the content is the brightest thing on screen. The page draws its own header.
 * * Light: every other page. The dark tokens still exist for focus mode.
 */
const FOCUS_ROUTES = [/^\/watch\/[^/]+\/?$/, /^\/quiz\/[^/]+\/?$/];

export function themeForPath(pathname) {
  return FOCUS_ROUTES.some((pattern) => pattern.test(pathname))
    ? "focus"
    : "light";
}

const UNPADDED = [/^\/$/, /^\/(login|register|forgot-password|reset-password|verify-email)\/?$/];

const PAGE_BACKGROUND = { light: "#F3F5F9", dark: "#0A1226", focus: "#0A1226" };

/**
 * App shell.
 *
 * `#main-content` is the skip-link target, and `min-h` on main keeps the footer
 * at the bottom on short pages (a common mobile complaint).
 */
export default function Layout() {
  const { pathname } = useLocation();
  const theme = themeForPath(pathname);
  const padded =
    theme !== "focus" && !UNPADDED.some((pattern) => pattern.test(pathname));

  // Colour the area behind the app too, so overscroll never flashes the wrong theme.
  useEffect(() => {
    document.body.style.backgroundColor = PAGE_BACKGROUND[theme];
  }, [theme]);

  return (
    <div
      className={`ls ${theme === "light" ? "" : "dark"} flex min-h-dvh flex-col`}
    >
      <a
        href="#main-content"
        className="sr-only-focusable absolute left-3 top-3 z-50 rounded-lg bg-gold px-3 py-2 text-sm font-medium text-on-gold"
      >
        Skip to main content
      </a>
      {theme !== "focus" && <Navbar />}
      <main
        id="main-content"
        className={`flex-1 ${padded ? "pb-16" : ""}`}
      >
        <Outlet />
      </main>
      {theme !== "focus" && <Footer />}
      <ToastHost />
    </div>
  );
}

/** Page heading used by every inner page for consistent rhythm. */
export function PageHeader({ title, description, actions, breadcrumbs }) {
  return (
    <div className="mb-8">
      {breadcrumbs?.length > 0 && (
        <nav aria-label="Breadcrumb" className="mb-4">
          <ol className="small flex flex-wrap items-center gap-2">
            {breadcrumbs.map((crumb, index) => (
              <li
                key={`${crumb.label}-${index}`}
                className="flex items-center gap-2"
              >
                {crumb.to ? (
                  <Link
                    to={crumb.to}
                    className="underline underline-offset-[3px] hover:text-ink"
                  >
                    {crumb.label}
                  </Link>
                ) : (
                  <span aria-current="page" className="text-ink2">
                    {crumb.label}
                  </span>
                )}
                {index < breadcrumbs.length - 1 && (
                  <Icon name="caretRight" className="i-sm" />
                )}
              </li>
            ))}
          </ol>
        </nav>
      )}

      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="h2">{title}</h1>
          {description && <p className="body mt-3 max-w-2xl">{description}</p>}
        </div>
        {actions && (
          <div className="flex flex-wrap items-center gap-2">{actions}</div>
        )}
      </div>
      <hr className="rule mt-6" />
    </div>
  );
}

export { Layout };
