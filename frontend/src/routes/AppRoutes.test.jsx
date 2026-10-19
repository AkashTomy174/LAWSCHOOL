import { render, screen } from "@testing-library/react";
import { MemoryRouter, Outlet } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { AuthContext } from "../context/AuthContext";
import AppRoutes from "./AppRoutes";

/**
 * The real route table, with the shell and every page replaced by a labelled stub.
 * What is under test is *which role reaches which URL* -- the direct-URL half of
 * role-based navigation (hiding a link is never the access control). The API
 * enforces the same rules independently; see apps/core/tests/test_role_permissions.py.
 */
vi.mock("../components/Layout", () => ({ default: () => <Outlet /> }));
vi.mock("../pages/Instructor/InstructorLayout", () => ({
  default: () => (
    <div>
      <span>TEACHING SHELL</span>
      <Outlet />
    </div>
  ),
}));
vi.mock("../pages/Instructor/InstructorDashboard", () => ({ default: () => <p>PAGE instructor-overview</p> }));
vi.mock("../pages/Instructor/ManageCourses", () => ({ default: () => <p>PAGE instructor-manage</p> }));
vi.mock("../pages/Instructor/LiveClasses", () => ({ default: () => <p>PAGE instructor-live</p> }));
vi.mock("../pages/Dashboard/Dashboard", () => ({ default: () => <p>PAGE learner-dashboard</p> }));
vi.mock("../pages/Leaderboard/Leaderboard", () => ({ default: () => <p>PAGE learner-rankings</p> }));
vi.mock("../pages/Live/MyLiveClasses", () => ({ default: () => <p>PAGE learner-live</p> }));
vi.mock("../pages/Auth/Login", () => ({ default: () => <p>PAGE login</p> }));
vi.mock("../pages/Profile/WhatsAppSettings", () => ({ default: () => <p>PAGE whatsapp-settings</p> }));
vi.mock("../pages/Admin/AdminNotifications", () => ({ default: () => <p>PAGE admin-whatsapp</p> }));
vi.mock("../pages/Admin/AdminPages", () => ({
  default: () => <p>PAGE admin-overview</p>,
  AdminUsers: () => <p>PAGE admin-users</p>,
  AdminCourses: () => <p>PAGE courses-table</p>,
  AdminSubscriptions: () => <p>PAGE admin-subscriptions</p>,
  AdminPayments: () => <p>PAGE admin-payments</p>,
  AdminVideos: () => <p>PAGE videos-table</p>,
  AdminQuizzes: () => <p>PAGE quizzes-table</p>,
  AdminLeaderboard: () => <p>PAGE admin-leaderboard</p>,
}));

function visit(path, user) {
  const value = {
    status: user ? "authenticated" : "anonymous",
    user,
    error: null,
    isAuthenticated: Boolean(user),
    hasRole: (...roles) => Boolean(user && roles.includes(user.role)),
  };
  return render(
    <AuthContext.Provider value={value}>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

const student = { role: "student", name: "S" };
const instructor = { role: "instructor", name: "I" };
const admin = { role: "admin", name: "A" };

const ADMIN_PATHS = [
  ["/admin", "admin-overview"],
  ["/admin/users", "admin-users"],
  ["/admin/courses", "courses-table"],
  ["/admin/subscriptions", "admin-subscriptions"],
  ["/admin/payments", "admin-payments"],
  ["/admin/videos", "videos-table"],
  ["/admin/quizzes", "quizzes-table"],
  ["/admin/leaderboard", "admin-leaderboard"],
  ["/admin/notifications", "admin-whatsapp"],
];

const TEACHING_PATHS = [
  ["/instructor", "instructor-overview"],
  ["/instructor/courses", "courses-table"],
  ["/instructor/manage", "instructor-manage"],
  ["/instructor/videos", "videos-table"],
  ["/instructor/quizzes", "quizzes-table"],
  ["/instructor/live", "instructor-live"],
];

describe("admin area is admin-only", () => {
  it.each(ADMIN_PATHS)("%s: admin reaches it", async (path, marker) => {
    visit(path, admin);
    expect(await screen.findByText(`PAGE ${marker}`)).toBeInTheDocument();
  });

  it.each(ADMIN_PATHS)("%s: instructor is refused", async (path, marker) => {
    visit(path, instructor);
    expect(await screen.findByText(/not available for your account/i)).toBeInTheDocument();
    expect(screen.queryByText(`PAGE ${marker}`)).not.toBeInTheDocument();
  });

  it.each(ADMIN_PATHS)("%s: student is refused", async (path, marker) => {
    visit(path, student);
    expect(await screen.findByText(/not available for your account/i)).toBeInTheDocument();
    expect(screen.queryByText(`PAGE ${marker}`)).not.toBeInTheDocument();
  });
});

describe("teaching workspace is instructor-only", () => {
  it.each(TEACHING_PATHS)("%s: instructor reaches it inside the Teaching shell", async (path, marker) => {
    visit(path, instructor);
    expect(await screen.findByText(`PAGE ${marker}`)).toBeInTheDocument();
    expect(screen.getByText("TEACHING SHELL")).toBeInTheDocument();
  });

  it.each(TEACHING_PATHS)("%s: student is refused", async (path, marker) => {
    visit(path, student);
    expect(await screen.findByText(/not available for your account/i)).toBeInTheDocument();
    expect(screen.queryByText(`PAGE ${marker}`)).not.toBeInTheDocument();
  });

  it.each(TEACHING_PATHS)("%s: admin is refused", async (path, marker) => {
    visit(path, admin);
    expect(await screen.findByText(/not available for your account/i)).toBeInTheDocument();
    expect(screen.queryByText(`PAGE ${marker}`)).not.toBeInTheDocument();
  });
});

describe("learner pages stay shared", () => {
  it.each([student, instructor, admin])("$role can open the learner dashboard", async (user) => {
    visit("/dashboard", user);
    expect(await screen.findByText("PAGE learner-dashboard")).toBeInTheDocument();
  });
});

describe("learner rankings are learner-only", () => {
  it("lets a student open /leaderboard", async () => {
    visit("/leaderboard", student);
    expect(await screen.findByText("PAGE learner-rankings")).toBeInTheDocument();
  });

  it.each([instructor, admin])("refuses $role at /leaderboard", async (user) => {
    visit("/leaderboard", user);
    expect(await screen.findByText(/not available for your account/i)).toBeInTheDocument();
    expect(screen.queryByText("PAGE learner-rankings")).not.toBeInTheDocument();
  });
});

describe("WhatsApp settings need a signed-in user", () => {
  it.each([student, instructor, admin])("$role can open /settings/whatsapp", async (user) => {
    visit("/settings/whatsapp", user);
    expect(await screen.findByText("PAGE whatsapp-settings")).toBeInTheDocument();
  });

  it("sends an anonymous visitor to sign in instead", async () => {
    visit("/settings/whatsapp", null);
    expect(await screen.findByText("PAGE login")).toBeInTheDocument();
    expect(screen.queryByText("PAGE whatsapp-settings")).not.toBeInTheDocument();
  });
});


describe("live classes page is for learners", () => {
  it("a student reaches it", async () => {
    visit("/live", student);
    expect(await screen.findByText("PAGE learner-live")).toBeInTheDocument();
  });

  it.each([["instructor", instructor], ["admin", admin]])("%s is refused", async (_, user) => {
    visit("/live", user);
    expect(await screen.findByText(/not available for your account/i)).toBeInTheDocument();
  });

  it("a visitor is sent to sign in", async () => {
    visit("/live", null);
    expect(await screen.findByText("PAGE login")).toBeInTheDocument();
  });
});
