import apiClient, { tokenStore, toApiError } from "./apiClient";

/**
 * Authentication service.
 *
 * Every call here mirrors a single backend endpoint.  No component imports axios
 * directly, so retry/refresh behaviour is uniform across the app.
 */
export const authService = {
  async register({ email, name, phone, password, passwordConfirm }) {
    const response = await apiClient.post("/auth/register/", {
      email,
      name,
      phone: phone || "",
      password,
      password_confirm: passwordConfirm,
    });
    tokenStore.set(response.data.tokens);
    return response.data;
  },

  async login({ email, password }) {
    const response = await apiClient.post("/auth/login/", { email, password });
    tokenStore.set({
      access: response.data.access,
      refresh: response.data.refresh,
    });
    return response.data;
  },

  /**
   * Logout is best-effort: the server blacklists the refresh token, but the local
   * session is cleared either way so a network failure cannot strand the student
   * in a half-logged-in state.
   */
  async logout() {
    const refresh = tokenStore.getRefresh();
    try {
      if (refresh) await apiClient.post("/auth/logout/", { refresh });
    } catch {
      // ignore: local cleanup below is what the user observes
    } finally {
      tokenStore.clear();
    }
  },

  async logoutAll() {
    try {
      await apiClient.post("/auth/logout-all/");
    } finally {
      tokenStore.clear();
    }
  },

  async me() {
    const response = await apiClient.get("/auth/me/");
    return response.data;
  },

  async updateProfile(payload) {
    const response = await apiClient.patch("/auth/me/", payload);
    return response.data;
  },

  async changePassword({ currentPassword, newPassword, newPasswordConfirm }) {
    const response = await apiClient.post("/auth/password/change/", {
      current_password: currentPassword,
      new_password: newPassword,
      new_password_confirm: newPasswordConfirm,
    });
    // Changing a password revokes every refresh token server-side, so the local
    // session must not pretend it is still valid.
    tokenStore.clear();
    return response.data;
  },

  async requestPasswordReset(email) {
    const response = await apiClient.post("/auth/password/reset/", { email });
    return response.data;
  },

  async confirmPasswordReset({ uid, token, newPassword, newPasswordConfirm }) {
    const response = await apiClient.post("/auth/password/reset/confirm/", {
      uid,
      token,
      new_password: newPassword,
      new_password_confirm: newPasswordConfirm,
    });
    return response.data;
  },

  async verifyEmail({ uid, token }) {
    const response = await apiClient.post("/auth/verify-email/", {
      uid,
      token,
    });
    return response.data;
  },

  async uploadAvatar(file) {
    const form = new FormData();
    form.append("avatar", file);
    const response = await apiClient.patch("/auth/me/", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return response.data;
  },
};

export { toApiError };
