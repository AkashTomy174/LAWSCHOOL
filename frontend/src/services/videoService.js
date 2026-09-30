import apiClient from "./apiClient";

/**
 * Video playback + progress.
 *
 * Note what is *not* here: there is no method that returns a permanent video URL.
 * `playback()` always asks Django for a freshly signed, short-lived token; the
 * browser never learns the Cloudflare video id.
 */

export const videoService = {
  async playback(videoUid) {
    const response = await apiClient.get(`/videos/${videoUid}/playback/`);
    return response.data;
  },

  async playbackForLesson(lessonId) {
    const response = await apiClient.get(
      `/videos/lessons/${lessonId}/playback/`,
    );
    return response.data;
  },

  /**
   * Send a progress heartbeat.
   *
   * Called on a 15s interval and on pause/end/unload — never per second.  The
   * server derives completion from these positions; `completed` is only a hint.
   */
  async updateProgress(
    videoUid,
    { positionSeconds, watchedSeconds, completed = false },
  ) {
    const response = await apiClient.post(
      `/videos/${videoUid}/progress/`,
      {
        position_seconds: Math.max(0, Math.round(positionSeconds)),
        watched_seconds:
          watchedSeconds === undefined
            ? undefined
            : Math.max(0, Math.round(watchedSeconds)),
        completed,
      },
      // A heartbeat must never block the UI or trigger a global error toast.
      { skipAuth: false, headers: { "X-Silent-Error": "1" } },
    );
    return response.data;
  },

  async myProgress(params = {}) {
    const response = await apiClient.get("/progress/", { params });
    return response.data;
  },

  async courseProgress(slug) {
    const response = await apiClient.get(`/progress/course/${slug}/`);
    return response.data;
  },

  /* ---- instructor/admin ---- */
  async list(params = {}) {
    const response = await apiClient.get("/videos/", { params });
    return response.data;
  },

  async registerLessonVideo({
    title,
    cloudflareVideoId,
    lessonId,
    description,
  }) {
    const response = await apiClient.post("/videos/register/", {
      title,
      cloudflare_video_id: cloudflareVideoId,
      lesson: lessonId || null,
      description: description || "",
    });
    return response.data;
  },

  /** One-time upload URL so the browser posts the file straight to Cloudflare. */
  async directUploadUrl() {
    const response = await apiClient.post("/videos/upload-url/");
    return response.data;
  },

  async sync(videoUid) {
    const response = await apiClient.post(`/videos/${videoUid}/sync/`);
    return response.data;
  },
};

export default videoService;
