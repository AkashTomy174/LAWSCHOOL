import apiClient from "./apiClient";

/** Quizzes, attempts and results. */

export const quizService = {
  /** Open (or resume) an attempt. The server enforces entitlement + limits. */
  async start(quizId) {
    const response = await apiClient.post(`/quizzes/${quizId}/attempts/`);
    return response.data;
  },

  async quiz(quizId) {
    const response = await apiClient.get(`/quizzes/${quizId}/`);
    return response.data;
  },

  /**
   * Submit answers.
   *
   * `answers` maps question id -> option id. The score is calculated by Django;
   * nothing about the result is decided in the browser.
   */
  async submit(attemptId, { answers, durationSeconds = 0 }) {
    const response = await apiClient.post(
      `/quiz-attempts/${attemptId}/submit/`,
      {
        answers,
        duration_seconds: Math.max(0, Math.round(durationSeconds)),
      },
    );
    return response.data;
  },

  async attempt(attemptId) {
    const response = await apiClient.get(`/quiz-attempts/${attemptId}/`);
    return response.data;
  },

  async myAttempts(params = {}) {
    const response = await apiClient.get("/quiz-attempts/", { params });
    return response.data;
  },

  async progress(quizId) {
    const response = await apiClient.get(`/quizzes/${quizId}/progress/`);
    return response.data;
  },

  /* ---- instructor/admin ---- */
  async list(params = {}) {
    const response = await apiClient.get("/quizzes/", { params });
    return response.data;
  },

  async create(payload) {
    const response = await apiClient.post("/quizzes/", payload);
    return response.data;
  },

  async update(quizId, payload) {
    const response = await apiClient.patch(`/quizzes/${quizId}/`, payload);
    return response.data;
  },

  async createQuestion(payload) {
    const response = await apiClient.post("/quizzes/questions/", payload);
    return response.data;
  },

  async createOption(payload) {
    const response = await apiClient.post("/quizzes/options/", payload);
    return response.data;
  },

  async allAttempts(params = {}) {
    const response = await apiClient.get("/quiz-attempts/all/", { params });
    return response.data;
  },
};

export const leaderboardService = {
  async list(params = {}) {
    const response = await apiClient.get("/leaderboard/", { params });
    return response.data;
  },

  async top(limit = 10) {
    const response = await apiClient.get("/leaderboard/top/", {
      params: { limit },
    });
    return response.data;
  },

  async me() {
    const response = await apiClient.get("/leaderboard/me/");
    return response.data;
  },

  async snapshots(params = {}) {
    const response = await apiClient.get("/leaderboard/snapshots/", { params });
    return response.data;
  },

  async recalculate() {
    const response = await apiClient.post("/leaderboard/recalculate/");
    return response.data;
  },
};

export const notificationService = {
  async list(params = {}) {
    const response = await apiClient.get("/notifications/", { params });
    return response.data;
  },

  async unreadCount() {
    const response = await apiClient.get("/notifications/unread-count/");
    return response.data;
  },

  async markRead(payload) {
    const response = await apiClient.post("/notifications/read/", payload);
    return response.data;
  },
};

export const userService = {
  /** Instructor/admin people directory. */
  async list(params = {}) {
    const response = await apiClient.get("/users/", { params });
    return response.data;
  },

  async detail(id) {
    const response = await apiClient.get(`/users/${id}/`);
    return response.data;
  },

  async update(id, payload) {
    const response = await apiClient.patch(`/users/${id}/`, payload);
    return response.data;
  },
};

export default quizService;
