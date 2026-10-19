import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../services/authService", () => ({
  authService: {
    register: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    me: vi.fn(),
  },
}));
vi.mock("../services/apiClient", () => ({
  setSessionExpiredHandler: vi.fn(),
  tokenStore: { hasSession: () => false, clear: vi.fn(), getRefresh: () => null },
}));

import { authService } from "../services/authService";
import { AuthProvider, useAuth } from "./AuthContext";

const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
const FORM = { email: "a@b.test", password: "Str0ng-Passphrase-9" };

describe("register is neutral about existing accounts", () => {
  beforeEach(() => vi.clearAllMocks());

  it("signs a brand-new account in and returns the user", async () => {
    authService.register.mockResolvedValue({ detail: "neutral" });
    authService.login.mockResolvedValue({ user: { id: "1", role: "student" } });
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.status).not.toBe("loading"));
    let user;
    await act(async () => {
      user = await result.current.register(FORM);
    });
    expect(user).toEqual({ id: "1", role: "student" });
    expect(authService.login).toHaveBeenCalledWith({ email: FORM.email, password: FORM.password });
  });

  it("returns null (neutral notice) when the follow-up sign-in is refused", async () => {
    authService.register.mockResolvedValue({ detail: "neutral" });
    authService.login.mockRejectedValue({ status: 401, code: "authentication_failed" });
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.status).not.toBe("loading"));
    let user = "unset";
    await act(async () => {
      user = await result.current.register(FORM);
    });
    expect(user).toBeNull();
    expect(result.current.status).not.toBe("authenticated");
  });

  it("still surfaces genuine failures such as validation errors", async () => {
    authService.register.mockRejectedValue({ status: 400, code: "validation_error" });
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.status).not.toBe("loading"));
    await expect(act(() => result.current.register(FORM))).rejects.toMatchObject({ status: 400 });
    expect(authService.login).not.toHaveBeenCalled();
  });
});
