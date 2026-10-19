import { NavLink, Outlet } from "react-router-dom";

import { teachingTabs } from "../../utils/roles";

/**
 * Shell for the instructor workspace: a sub-navigation above every Teaching page.
 * Scrolls sideways on narrow screens instead of wrapping.
 */
export default function InstructorLayout({
  tabs = teachingTabs,
  label = "Teaching",
}) {
  return (
    <>
      <div className="border-b border-line bg-page">
        <nav
          aria-label={label}
          className="wrap nav-links flex gap-1 overflow-x-auto py-2"
        >
          {tabs.map((tab) => (
            <NavLink
              key={tab.to}
              to={tab.to}
              end={tab.end}
              className={({ isActive }) => (isActive ? "on" : undefined)}
            >
              {tab.label}
            </NavLink>
          ))}
        </nav>
      </div>
      <Outlet />
    </>
  );
}
