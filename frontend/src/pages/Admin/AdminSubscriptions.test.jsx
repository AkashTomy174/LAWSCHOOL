import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { subscriptionService } from "../../services/paymentService";
import { AdminSubscriptions } from "./AdminPages";

vi.mock("../../services/paymentService", async (importOriginal) => ({
  ...(await importOriginal()),
  subscriptionService: { all: vi.fn() },
}));

function renderPage() {
  return render(
    <MemoryRouter>
      <AdminSubscriptions />
    </MemoryRouter>,
  );
}

const ROW = {
  id: "s1",
  user_email: "rahul@example.com",
  plan: { name: "All Access" },
  status: "active",
  is_currently_active: true,
  end_date: "2027-10-07T00:00:00Z",
  payment_reference: "pay_123",
};

beforeEach(() => vi.clearAllMocks());

describe("AdminSubscriptions", () => {
  it("renders every row of the paginated response", async () => {
    subscriptionService.all.mockResolvedValue({ count: 1, results: [ROW] });
    renderPage();
    expect(await screen.findByText("rahul@example.com")).toBeInTheDocument();
    expect(screen.getByText("All Access")).toBeInTheDocument();
    expect(screen.getByText("pay_123")).toBeInTheDocument();
    expect(screen.queryByText("No subscriptions yet.")).toBeNull();
  });

  it("says so when there are no subscriptions", async () => {
    subscriptionService.all.mockResolvedValue({ count: 0, results: [] });
    renderPage();
    expect(await screen.findByText("No subscriptions yet.")).toBeInTheDocument();
  });

  it("shows the server's refusal instead of an empty table", async () => {
    subscriptionService.all.mockRejectedValue(
      Object.assign(new Error("This action is available to administrators only."), {
        code: "permission_denied",
        status: 403,
      }),
    );
    renderPage();
    expect(
      await screen.findByText("This action is available to administrators only."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("shows a loading placeholder first", () => {
    subscriptionService.all.mockReturnValue(new Promise(() => {}));
    const { container } = renderPage();
    expect(container.querySelector("table")).toBeNull();
    expect(screen.queryByText("No subscriptions yet.")).toBeNull();
  });
});
