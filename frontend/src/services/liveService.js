import apiClient from "./apiClient";

/** Live classes: authoring (instructor: own courses, admin: all) and attending. The server enforces access. */
export const liveService = {
  async list() {
    const response = await apiClient.get("/live-classes/manage/");
    return response.data;
  },

  async create(payload) {
    const response = await apiClient.post("/live-classes/manage/", payload);
    return response.data;
  },

  async update(id, payload) {
    const response = await apiClient.patch(`/live-classes/manage/${id}/`, payload);
    return response.data;
  },

  async remove(id) {
    await apiClient.delete(`/live-classes/manage/${id}/`);
  },

  /** Classes the caller may attend (no meeting links; status from the server). */
  async mine() {
    const response = await apiClient.get("/live-classes/");
    return response.data;
  },

  /** The meeting link: the server checks entitlement and the join window. */
  async join(id) {
    const response = await apiClient.get(`/live-classes/${id}/join/`);
    return response.data;
  },
};

export default liveService;
