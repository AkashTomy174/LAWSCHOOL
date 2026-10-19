import apiClient from "./apiClient";

/**
 * WhatsApp notification API. Student calls act on the signed-in user only; the
 * `admin*` calls are admin-only server-side (this file just names the routes).
 * No provider credentials ever reach the browser.
 */
const base = "/notifications";

export const notificationService = {
  async getPreferences() {
    return (await apiClient.get(`${base}/whatsapp/preferences/`)).data;
  },
  async updatePreferences(patch) {
    return (await apiClient.patch(`${base}/whatsapp/preferences/`, patch)).data;
  },
  async requestLink({ phone, consent }) {
    return (await apiClient.post(`${base}/whatsapp/link/`, { phone, consent })).data;
  },
  async verify(code) {
    return (await apiClient.post(`${base}/whatsapp/verify/`, { code })).data;
  },
  async optOut() {
    return (await apiClient.post(`${base}/whatsapp/opt-out/`)).data;
  },
  async history(params = {}) {
    return (await apiClient.get(`${base}/whatsapp/history/`, { params })).data;
  },

  /* ----------------------------------------------------------------- admin */
  async adminOverview(params = {}) {
    return (await apiClient.get(`${base}/admin/overview/`, { params })).data;
  },
  async adminHistory(params = {}) {
    return (await apiClient.get(`${base}/admin/history/`, { params })).data;
  },
  async adminRetry(id) {
    return (await apiClient.post(`${base}/admin/${id}/retry/`)).data;
  },
  async adminTemplates() {
    return (await apiClient.get(`${base}/admin/templates/`)).data;
  },
  async adminUpdateTemplate(id, patch) {
    return (await apiClient.patch(`${base}/admin/templates/${id}/`, patch)).data;
  },
  async adminSettings() {
    return (await apiClient.get(`${base}/admin/settings/`)).data;
  },
  async adminUpdateSettings(patch) {
    return (await apiClient.patch(`${base}/admin/settings/`, patch)).data;
  },
  async adminAnnouncementPreview(params = {}) {
    return (await apiClient.get(`${base}/admin/announcements/preview/`, { params })).data;
  },
  async adminAnnounce(payload) {
    return (await apiClient.post(`${base}/admin/announcements/`, payload)).data;
  },
};

export default notificationService;
