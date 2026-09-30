import apiClient from "./apiClient";

/**
 * Normalise a paginated DRF list response to the array it wraps.
 *
 * Django REST Framework list endpoints return
 * ``{count, next, previous, results: [...]}``.  A few of ours are deliberately
 * unpaginated and return a bare array instead.  Callers should not have to know
 * which is which, so this accepts either shape and always yields an array --
 * which is also why it is safe to call on a response whose pagination setting
 * might change later.
 */
function unwrapList(data) {
  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.results)) return data.results;
  return [];
}

/**
 * Payments + subscriptions.
 *
 * The golden rule mirrored from the backend: the frontend may *start* a payment
 * and then *report* its identifiers, but it never decides whether the payment
 * succeeded. `verifyPayment` sends the three Razorpay values and the server
 * verifies the HMAC signature before activating anything.
 */

export const subscriptionService = {
  /**
   * Public pricing list.
   *
   * The endpoint is *paginated* (``{count, next, previous, results}``) because it
   * shares the project-wide pagination settings.  Every caller wants the plan
   * array itself -- the pricing grid, the dashboard CTA and the admin table all
   * iterate it -- so the envelope is unwrapped here rather than at each call site.
   *
   * Returning ``response.data`` unconditionally (the previous behaviour) handed
   * back an object where callers did ``plans.data.map(...)``, which throws
   * "``.map`` is not a function" and blanks the whole page via the error boundary.
   * Unwrapping in one place means the next paginated list cannot reintroduce it.
   */
  async plans() {
    const response = await apiClient.get("/subscriptions/plans/");
    return unwrapList(response.data);
  },

  async plan(slug) {
    const response = await apiClient.get(`/subscriptions/plans/${slug}/`);
    return response.data;
  },

  async mine() {
    const response = await apiClient.get("/subscriptions/me/");
    return response.data;
  },

  async history(params = {}) {
    const response = await apiClient.get("/subscriptions/history/", { params });
    return response.data;
  },

  async cancel({ immediate = false } = {}) {
    const response = await apiClient.post("/subscriptions/me/cancel/", {
      immediate,
    });
    return response.data;
  },

  /* ---- admin ---- */
  async all(params = {}) {
    const response = await apiClient.get("/subscriptions/", { params });
    return unwrapList(response.data);
  },
};

export const paymentService = {
  /**
   * Create a Razorpay order server-side.
   *
   * `idempotencyKey` lets a retry return the same order instead of creating a
   * second one, which protects the student from a double charge.
   */
  async createOrder({ planSlug, idempotencyKey }) {
    const response = await apiClient.post("/payments/orders/", {
      plan_slug: planSlug,
      idempotency_key: idempotencyKey || "",
    });
    return response.data;
  },

  /** Report the checkout callback for server-side signature verification. */
  async verifyPayment({ orderId, paymentId, signature }) {
    const response = await apiClient.post("/payments/verify/", {
      razorpay_order_id: orderId,
      razorpay_payment_id: paymentId,
      razorpay_signature: signature,
    });
    return response.data;
  },

  async mine(params = {}) {
    const response = await apiClient.get("/payments/", { params });
    return response.data;
  },

  /* ---- admin ---- */
  async all(params = {}) {
    const response = await apiClient.get("/payments/all/", { params });
    return response.data;
  },

  async webhookEvents(params = {}) {
    const response = await apiClient.get("/payments/webhook-events/", {
      params,
    });
    return response.data;
  },
};
export default paymentService;
