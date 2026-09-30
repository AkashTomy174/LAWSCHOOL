import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { RequireAuth, RequireRole } from "../components/RouteGuards";
import { AuthContext } from "../context/AuthContext";

/**
 * Route guard tests.
 *
 * These verify the UX behaviour (redirect vs. role message) and — importantly —
 * document that the guards are *not* the security boundary: the assertions here say
 * nothing about whether the API would allow the request. That is covered by the
 * backend test suite.
 */

function renderWithAuth(ui, { status, user, initialEntry = "/" }) {
  const value = {
    status,
    user,
    error: null,
    setError: vi.fn(),
    isAuthenticated: status === "authenticated",
    isStudent: user?.role === "student",
    isInstructor: user?.role === "instructor",
    isAdmin: user?.role === "admin",
    hasRole: (...roles) => Boolean(user && roles.includes(user.role)),
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    refreshUser: vi.fn(),
    updateUser: vi.fn(),
  };

  // The guarded route is the ONLY route that defines the protected path. Declaring
  // it a second time outside the guard would let react-router match the unguarded
  // one and silently defeat the test.
  return render(
    <AuthContext.Provider value={value}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/login" element={<div>Login screen</div>} />
          {ui}
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

describe("RequireAuth", () => {
  it("redirects an anonymous visitor to the login page", () => {
    renderWithAuth(
      <Route element={<RequireAuth />}>
        <Route path="/dashboard" element={<div>Dashboard content</div>} />
      </Route>,
      { status: "anonymous", user: null, initialEntry: "/dashboard" },
    );

    expect(screen.getByText("Login screen")).toBeInTheDocument();
    expect(screen.queryByText("Dashboard content")).not.toBeInTheDocument();
  });

  it("renders the protected route for an authenticated student", () => {
    renderWithAuth(
      <Route element={<RequireAuth />}>
        <Route path="/dashboard" element={<div>Dashboard content</div>} />
      </Route>,
      {
        status: "authenticated",
        user: { role: "student", name: "Test" },
        initialEntry: "/dashboard",
      },
    );

    expect(screen.getByText("Dashboard content")).toBeInTheDocument();
  });

  it("shows a loading state instead of nothing while the session resolves", () => {
    renderWithAuth(
      <Route element={<RequireAuth />}>
        <Route path="/dashboard" element={<div>Dashboard content</div>} />
      </Route>,
      { status: "loading", user: null, initialEntry: "/dashboard" },
    );

    // A blank screen on a slow network looks like a broken app.
    expect(screen.getByText(/checking your session/i)).toBeInTheDocument();
  });
});

describe("RequireRole", () => {
  it("denies a student the instructor surface with an explanation", () => {
    renderWithAuth(
      <Route element={<RequireRole roles={["instructor", "admin"]} />}>
        <Route path="/admin" element={<div>Admin content</div>} />
      </Route>,
      {
        status: "authenticated",
        user: { role: "student", name: "Test" },
        initialEntry: "/admin",
      },
    );

    expect(screen.queryByText("Admin content")).not.toBeInTheDocument();
    expect(
      screen.getByText(/not available for your account/i),
    ).toBeInTheDocument();
  });

  it("allows an instructor through", () => {
    renderWithAuth(
      <Route element={<RequireRole roles={["instructor", "admin"]} />}>
        <Route path="/admin" element={<div>Admin content</div>} />
      </Route>,
      {
        status: "authenticated",
        user: { role: "instructor", name: "Teacher" },
        initialEntry: "/admin",
      },
    );

    expect(screen.getByText("Admin content")).toBeInTheDocument();
  });

  it("redirects an anonymous visitor before evaluating roles", () => {
    renderWithAuth(
      <Route element={<RequireRole roles={["instructor", "admin"]} />}>
        <Route path="/admin" element={<div>Admin content</div>} />
      </Route>,
      { status: "anonymous", user: null, initialEntry: "/admin" },
    );

    expect(screen.getByText("Login screen")).toBeInTheDocument();
  });
});
