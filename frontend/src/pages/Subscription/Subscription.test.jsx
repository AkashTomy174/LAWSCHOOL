import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { AuthContext } from "../../context/AuthContext";
import { UIProvider } from "../../context/UIContext";
import { paymentService, subscriptionService } from "../../services/paymentService";
import Subscription from "./Subscription";

vi.mock("../../hooks/useCheckout", () => ({
  default: () => ({ pay: vi.fn(), error: null, isBusy: () => false }),
}));
vi.mock("../../services/paymentService", () => ({
  paymentService: { mine: vi.fn() },
  subscriptionService: { mine: vi.fn(), plans: vi.fn() },
}));

describe("subscription status", () => {
  it("states the real expiry and offers no fictitious cancellation", async () => {
    subscriptionService.mine.mockResolvedValue({
      has_active_subscription: true,
      history: [],
      active: {
        status: "active",
        status_display: "Active",
        days_remaining: 30,
        end_date: "2027-10-20T00:00:00Z",
        payment_reference: "pay_1",
        plan: { name: "All Access", is_all_access: true },
      },
    });
    subscriptionService.plans.mockResolvedValue([]);
    paymentService.mine.mockResolvedValue({ results: [] });

    render(
      <AuthContext.Provider value={{ refreshUser: vi.fn() }}>
        <UIProvider>
          <MemoryRouter>
            <Subscription />
          </MemoryRouter>
        </UIProvider>
      </AuthContext.Provider>,
    );

    expect(
      await screen.findByText(/does not renew and you will not be charged again/),
    ).toHaveTextContent("Access ends on");
    expect(screen.queryByRole("button", { name: /cancel/i })).toBeNull();
  });
});
