import { beforeEach, describe, expect, it, vi } from "vitest";

import { subscriptionService } from "./paymentService";

/**
 * Service contract tests.
 *
 * Regression guard for a real crash: ``/api/v1/subscriptions/plans/`` is paginated
 * and returns ``{count, next, previous, results: [...]}``, but the Subscription page
 * renders ``(plans.data || []).map(...)``.  When the service passed the raw envelope
 * through, ``.map`` was called on an object, which threw
 * "``(intermediate value).map is not a function``" and -- with no error boundary --
 * blanked the entire page.
 *
 * The lesson this test encodes: a list-returning service method must always
 * resolve to an array, regardless of the response envelope, because callers
 * iterate it.  If the backend pagination settings for an endpoint ever change
 * (in either direction), these tests still pass and the UI still works.
 */

vi.mock("./apiClient", () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

import apiClient from "./apiClient";

describe("subscriptionService.plans", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("unwraps the paginated envelope into an array", async () => {
    apiClient.get.mockResolvedValue({
      data: {
        count: 2,
        next: null,
        previous: null,
        results: [
          { id: "p1", name: "Foundations", price: "1999.00" },
          { id: "p2", name: "All Access", price: "4999.00" },
        ],
      },
    });

    const plans = await subscriptionService.plans();

    expect(Array.isArray(plans)).toBe(true);
    expect(plans).toHaveLength(2);
    expect(plans[0].name).toBe("Foundations");
    // The exact operation that used to throw.
    expect(() => plans.map((plan) => plan.name)).not.toThrow();
  });

  it("passes a bare array through unchanged", async () => {
    // Endpoints with ``pagination_class = None`` return an array directly.
    apiClient.get.mockResolvedValue({
      data: [{ id: "p1", name: "Foundations" }],
    });

    const plans = await subscriptionService.plans();

    expect(Array.isArray(plans)).toBe(true);
    expect(plans).toHaveLength(1);
  });

  it("returns an empty array rather than a non-iterable for an odd payload", async () => {
    // Defensive: a caller must never receive something it cannot iterate.
    apiClient.get.mockResolvedValue({ data: { unexpected: "shape" } });

    const plans = await subscriptionService.plans();

    expect(plans).toEqual([]);
    expect(() => plans.map(() => {})).not.toThrow();
  });
});

describe("subscriptionService.all", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("unwraps the paginated envelope for the admin listing", async () => {
    apiClient.get.mockResolvedValue({
      data: { count: 1, results: [{ id: "s1", status: "active" }] },
    });

    const subscriptions = await subscriptionService.all();

    expect(Array.isArray(subscriptions)).toBe(true);
    expect(subscriptions[0].status).toBe("active");
  });
});

describe("subscriptionService.mine", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("preserves the object shape the page destructures", async () => {
    // ``mine`` is NOT a list: the page reads ``mine.data.active`` and
    // ``mine.data.history``, so it must stay an object.
    apiClient.get.mockResolvedValue({
      data: {
        active: { id: "s1", plan: { name: "Foundations" } },
        history: [],
      },
    });

    const mine = await subscriptionService.mine();

    expect(Array.isArray(mine)).toBe(false);
    expect(mine.active.plan.name).toBe("Foundations");
  });
});
