/** Where a signed-in user lands by default: staff go to their workspace, learners to the dashboard. */
export function homePathFor(user) {
  if (user?.role === "admin") return "/admin";
  if (user?.role === "instructor") return "/instructor";
  return "/dashboard";
}

export const isStaffUser = (user) =>
  user?.role === "admin" || user?.role === "instructor";

const publicLinks = [
  { to: "/courses", label: "Courses" },
  { to: "/subscription", label: "Plans" },
  { to: "/leaderboard", label: "Leaderboard" },
];

const learnerLinks = [
  { to: "/courses", label: "Courses" },
  { to: "/dashboard", label: "Dashboard" },
  { to: "/live", label: "Live classes" },
  { to: "/subscription", label: "Plans" },
  { to: "/leaderboard", label: "Leaderboard" },
];

// Staff reach courses by role/ownership, not by plan, and rankings are a learner
// feature, so Plans and Leaderboard are learner-only.
const LEARNER_ONLY = new Set(["/live", "/subscription", "/leaderboard"]);
const staffBaseLinks = learnerLinks.filter((link) => !LEARNER_ONLY.has(link.to));

/**
 * Top-bar links for a user. Navigation only: every route and endpoint re-checks
 * authorisation, so hiding a link is never the access control.
 */
export function navLinksFor(user) {
  if (!user) return publicLinks;
  if (user.role === "admin") return [...staffBaseLinks, { to: "/admin", label: "Admin" }];
  if (user.role === "instructor") {
    return [...staffBaseLinks, { to: "/instructor", label: "Teaching" }];
  }
  return learnerLinks;
}

/** Tabs of the admin workspace. */
export const adminTabs = [
  { to: "/admin", label: "Overview", end: true },
  { to: "/admin/users", label: "Users" },
  { to: "/admin/courses", label: "Courses" },
  { to: "/admin/videos", label: "Videos" },
  { to: "/admin/quizzes", label: "Quizzes" },
  { to: "/admin/subscriptions", label: "Subscriptions" },
  { to: "/admin/payments", label: "Payments" },
  { to: "/admin/leaderboard", label: "Leaderboard" },
  { to: "/admin/notifications", label: "WhatsApp" },
];

/** Tabs of the instructor workspace (also used to build the sub-navigation). */
export const teachingTabs = [
  { to: "/instructor", label: "Overview", end: true },
  { to: "/instructor/courses", label: "My Courses" },
  { to: "/instructor/manage", label: "Manage Courses" },
  { to: "/instructor/videos", label: "Videos" },
  { to: "/instructor/quizzes", label: "Quizzes" },
  { to: "/instructor/live", label: "Live Classes" },
];
