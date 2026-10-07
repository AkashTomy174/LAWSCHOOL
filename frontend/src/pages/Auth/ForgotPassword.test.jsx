import { StrictMode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { authService } from "../../services/authService";
import ForgotPassword, { VerifyEmail } from "./ForgotPassword";

vi.mock("../../services/authService", () => ({
  authService: {
    requestPasswordReset: vi.fn(),
    confirmPasswordReset: vi.fn(),
    verifyEmail: vi.fn(),
  },
}));
vi.mock("../../context/UIContext", () => ({
  useUI: () => ({ pushToast: vi.fn() }),
}));

/**
 * These pages once rendered a blank screen because `AuthLayout` was used without
 * being imported.  Every test here mounts the real route, so a render-time
 * ReferenceError fails the suite instead of reaching production.
 */
function renderAt(entry) {
  return render(
    <StrictMode>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/reset-password" element={<ForgotPassword />} />
          <Route path="/verify-email" element={<VerifyEmail />} />
          <Route path="/login" element={<div>Login screen</div>} />
          <Route path="/dashboard" element={<div>Dashboard screen</div>} />
          <Route path="/profile" element={<div>Profile screen</div>} />
        </Routes>
      </MemoryRouter>
    </StrictMode>,
  );
}

beforeEach(() => vi.clearAllMocks());

describe("/forgot-password", () => {
  it("renders the request form", () => {
    renderAt("/forgot-password");
    expect(
      screen.getByRole("heading", { name: "Reset your password" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Email address")).toBeInTheDocument();
  });

  it("asks for an email before calling the API", async () => {
    renderAt("/forgot-password");
    await userEvent.click(screen.getByRole("button", { name: "Send reset link" }));
    expect(await screen.findByText("Enter your email address.")).toBeInTheDocument();
    expect(authService.requestPasswordReset).not.toHaveBeenCalled();
  });

  it("shows the neutral confirmation and links back to sign in", async () => {
    authService.requestPasswordReset.mockResolvedValue({});
    renderAt("/forgot-password");
    await userEvent.type(screen.getByLabelText("Email address"), "a@b.test");
    await userEvent.click(screen.getByRole("button", { name: "Send reset link" }));

    expect(await screen.findByText("Check your inbox")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("link", { name: "Back to sign in" }));
    expect(screen.getByText("Login screen")).toBeInTheDocument();
  });

  it("shows an error when the API fails", async () => {
    authService.requestPasswordReset.mockRejectedValue(new Error("Server down."));
    renderAt("/forgot-password");
    await userEvent.type(screen.getByLabelText("Email address"), "a@b.test");
    await userEvent.click(screen.getByRole("button", { name: "Send reset link" }));
    expect(await screen.findByText("Server down.")).toBeInTheDocument();
  });
});

describe("/reset-password", () => {
  const url = "/reset-password?uid=u1&token=t1";

  async function fill(password, confirm) {
    await userEvent.type(screen.getByLabelText("New password"), password);
    await userEvent.type(screen.getByLabelText("Confirm new password"), confirm);
    await userEvent.click(screen.getByRole("button", { name: "Set new password" }));
  }

  it("renders the new-password form when the link carries uid and token", () => {
    renderAt(url);
    expect(
      screen.getByRole("heading", { name: "Choose a new password" }),
    ).toBeInTheDocument();
  });

  it("rejects short and mismatched passwords locally", async () => {
    renderAt(url);
    await fill("short", "different");
    expect(await screen.findByText("Use at least 10 characters.")).toBeInTheDocument();
    expect(screen.getByText("Passwords do not match.")).toBeInTheDocument();
    expect(authService.confirmPasswordReset).not.toHaveBeenCalled();
  });

  it("submits the token and ends on a link to sign in", async () => {
    authService.confirmPasswordReset.mockResolvedValue({});
    renderAt(url);
    await fill("a-long-password-1", "a-long-password-1");

    expect(await screen.findByText("Password updated")).toBeInTheDocument();
    expect(authService.confirmPasswordReset).toHaveBeenCalledWith({
      uid: "u1",
      token: "t1",
      newPassword: "a-long-password-1",
      newPasswordConfirm: "a-long-password-1",
    });
    await userEvent.click(screen.getByRole("link", { name: "Back to sign in" }));
    expect(screen.getByText("Login screen")).toBeInTheDocument();
  });

  it("shows the server's message for an expired link", async () => {
    authService.confirmPasswordReset.mockRejectedValue(
      new Error("This reset link has expired."),
    );
    renderAt(url);
    await fill("a-long-password-1", "a-long-password-1");
    expect(await screen.findByText("This reset link has expired.")).toBeInTheDocument();
    expect(screen.queryByText("Password updated")).not.toBeInTheDocument();
  });
});

describe("/verify-email", () => {
  it("verifies once on arrival (even under StrictMode) and links to the dashboard", async () => {
    authService.verifyEmail.mockResolvedValue({});
    renderAt("/verify-email?uid=u1&token=t1");

    expect(await screen.findByText("Email verified")).toBeInTheDocument();
    expect(authService.verifyEmail).toHaveBeenCalledTimes(1);
    expect(authService.verifyEmail).toHaveBeenCalledWith({ uid: "u1", token: "t1" });
    await userEvent.click(screen.getByRole("link", { name: "Go to dashboard" }));
    expect(screen.getByText("Dashboard screen")).toBeInTheDocument();
  });

  it("shows the failure state for an invalid or expired link", async () => {
    authService.verifyEmail.mockRejectedValue(new Error("Link already used."));
    renderAt("/verify-email?uid=u1&token=bad");

    expect(await screen.findByText("Verification failed")).toBeInTheDocument();
    expect(screen.getByText("Link already used.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("link", { name: "Open profile" }));
    expect(screen.getByText("Profile screen")).toBeInTheDocument();
  });

  it("fails fast, without calling the API, when the link is incomplete", async () => {
    renderAt("/verify-email");
    expect(await screen.findByText("Verification failed")).toBeInTheDocument();
    await waitFor(() => expect(authService.verifyEmail).not.toHaveBeenCalled());
  });
});
