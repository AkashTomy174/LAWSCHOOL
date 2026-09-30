import { Link, Outlet } from "react-router-dom";

import Footer from "./Footer";
import Navbar from "./Navbar";
import ToastHost from "./ToastHost";

/**
 * App shell.
 *
 * `#main-content` is the skip-link target, and `min-h` on main keeps the footer
 * at the bottom on short pages (a common mobile complaint).
 */
export default function Layout() {
  return (
    <div className="flex min-h-dvh flex-col">
      <Navbar />
      <main id="main-content" className="flex-1">
        <Outlet />
      </main>
      <Footer />
      <ToastHost />
    </div>
  );
}

/** Page heading used by every inner page for consistent rhythm. */
export function PageHeader({ title, description, actions, breadcrumbs }) {
  return (
    <div className="mb-6">
      {breadcrumbs?.length > 0 && (
        <nav aria-label="Breadcrumb" className="mb-3">
          <ol className="flex flex-wrap items-center gap-1 text-xs text-white/45">
            {breadcrumbs.map((crumb, index) => (
              <li
                key={`${crumb.label}-${index}`}
                className="flex items-center gap-1"
              >
                {crumb.to ? (
                  <Link to={crumb.to} className="hover:text-gold-300">
                    {crumb.label}
                  </Link>
                ) : (
                  <span aria-current="page">{crumb.label}</span>
                )}
                {index < breadcrumbs.length - 1 && (
                  <span aria-hidden="true">/</span>
                )}
              </li>
            ))}
          </ol>
        </nav>
      )}

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl text-parchment sm:text-3xl">
            {title}
          </h1>
          {description && (
            <p className="mt-2 max-w-2xl text-sm text-white/60">
              {description}
            </p>
          )}
        </div>
        {actions && (
          <div className="flex flex-wrap items-center gap-2">{actions}</div>
        )}
      </div>
      <div className="gold-rule mt-5" />
    </div>
  );
}

export { Layout };
