import apiClient from "./apiClient";

/** Course catalogue + lesson access. */

export const courseService = {
  /** Public catalogue with filters. `params` accepts page, search, level, ordering. */
  async list(params = {}) {
    const response = await apiClient.get("/courses/", { params });
    return response.data;
  },

  async detail(slug) {
    const response = await apiClient.get(`/courses/${slug}/`);
    return response.data;
  },

  async lessons(slug) {
    const response = await apiClient.get(`/courses/${slug}/lessons/`);
    return response.data;
  },

  /** Explicit entitlement probe, used by the purchase CTA. */
  async access(slug) {
    const response = await apiClient.get(`/courses/${slug}/access/`);
    return response.data;
  },

  async create(payload) {
    const response = await apiClient.post("/courses/", payload);
    return response.data;
  },

  async update(slug, payload) {
    const response = await apiClient.patch(`/courses/${slug}/`, payload);
    return response.data;
  },

  async remove(slug) {
    await apiClient.delete(`/courses/${slug}/`);
  },

  /* ---- sections & lessons (authoring) ---- */
  async createSection(payload) {
    const response = await apiClient.post("/sections/", payload);
    return response.data;
  },

  async updateSection(id, payload) {
    const response = await apiClient.patch(`/sections/${id}/`, payload);
    return response.data;
  },

  async deleteSection(id) {
    await apiClient.delete(`/sections/${id}/`);
  },

  async createLesson(payload) {
    const response = await apiClient.post("/lessons/", payload);
    return response.data;
  },

  async updateLesson(id, payload) {
    const response = await apiClient.patch(`/lessons/${id}/`, payload);
    return response.data;
  },

  async deleteLesson(id) {
    await apiClient.delete(`/lessons/${id}/`);
  },

  async watchLesson(id) {
    const response = await apiClient.get(`/lessons/${id}/watch/`);
    return response.data;
  },
};

export default courseService;
