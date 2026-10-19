import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import notificationService from "../../services/notificationService";
import AdminNotifications from "./AdminNotifications";

vi.mock("../../services/notificationService", () => ({
  default: {
    adminOverview: vi.fn(),
    adminHistory: vi.fn(),
    adminRetry: vi.fn(),
    adminTemplates: vi.fn(),
    adminUpdateTemplate: vi.fn(),
    adminSettings: vi.fn(),
    adminUpdateSettings: vi.fn(),
    adminAnnouncementPreview: vi.fn(),
    adminAnnounce: vi.fn(),
  },
}));
const pushToast = vi.fn();
vi.mock("../../context/UIContext", () => ({ useUI: () => ({ pushToast }) }));

const OVERVIEW = {
  enabled: true,
  days: 30,
  by_status: { accepted: 3, delivered: 5, failed: 1 },
  by_template: [{ template_name: "payment_success", n: 9 }],
  note: "'Accepted' means WhatsApp took the message; only 'Delivered' and 'Read' come from delivery receipts.",
  estimated_cost: null,
  estimated_cost_note: "Cost estimate not configured.",
};
const ROW = { id: "n1", recipient: "Asha", recipient_number: "+91*****3210", template_name: "payment_success", status: "failed", status_label: "Failed", last_error_code: "131026", created_at: "2026-10-18T10:00:00Z", delivered_at: null };

const page = () => render(<MemoryRouter><AdminNotifications /></MemoryRouter>);

beforeEach(() => {
  vi.clearAllMocks();
  notificationService.adminOverview.mockResolvedValue(OVERVIEW);
});

describe("Admin WhatsApp", () => {
  it("separates accepted from delivered and never invents a cost", async () => {
    page();
    expect(await screen.findByText(/only 'Delivered' and 'Read'/)).toBeInTheDocument();
    expect(screen.queryByText(/estimated spend/i)).toBeNull();
    expect(screen.getByText("accepted").nextSibling).toHaveTextContent("3");
    expect(screen.getByText("delivered").nextSibling).toHaveTextContent("5");
  });

  it("warns when WhatsApp is off", async () => {
    notificationService.adminOverview.mockResolvedValue({ ...OVERVIEW, enabled: false });
    page();
    expect(await screen.findByText("WhatsApp is switched off")).toBeInTheDocument();
  });

  it("shows an error with retry", async () => {
    notificationService.adminOverview.mockRejectedValue(new Error("forbidden"));
    page();
    expect(await screen.findByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("lists the delivery log with masked numbers and retries a failure", async () => {
    notificationService.adminHistory.mockResolvedValue({ results: [ROW], page: 1, num_pages: 1 });
    notificationService.adminRetry.mockResolvedValue({});
    page();
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: "Delivery log" }));
    expect(await screen.findByText("+91*****3210")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(notificationService.adminRetry).toHaveBeenCalledWith("n1"));
    expect(pushToast).toHaveBeenCalledWith(expect.objectContaining({ tone: "success" }));
  });

  it("passes filters to the API", async () => {
    notificationService.adminHistory.mockResolvedValue({ results: [], page: 1, num_pages: 1 });
    page();
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: "Delivery log" }));
    await screen.findByText("No messages match");
    await user.selectOptions(screen.getByLabelText("Status"), "failed");
    await waitFor(() => expect(notificationService.adminHistory).toHaveBeenLastCalledWith({ status: "failed", page: 1 }));
  });

  it("records template approval changes", async () => {
    const template = { id: 1, internal_name: "payment_success", meta_category: "utility", variable_schema: ["student_name"], body_preview: "Hi {{1}}", approval_status: "unknown", active: true, has_trigger: true };
    notificationService.adminTemplates.mockResolvedValue([template]);
    notificationService.adminUpdateTemplate.mockResolvedValue({ ...template, approval_status: "approved" });
    page();
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: "Templates" }));
    await user.selectOptions(await screen.findByLabelText("Approval for payment_success"), "approved");
    await waitFor(() => expect(notificationService.adminUpdateTemplate).toHaveBeenCalledWith(1, { approval_status: "approved" }));
    expect(await screen.findByDisplayValue("Approved")).toBeInTheDocument();
  });

  it("lists templates with no trigger separately", async () => {
    const base = { variable_schema: [], body_preview: "", approval_status: "unknown", active: true, meta_category: "utility" };
    notificationService.adminTemplates.mockResolvedValue([
      { ...base, id: 1, internal_name: "payment_success", has_trigger: true },
      { ...base, id: 2, internal_name: "certificate_available", has_trigger: false },
    ]);
    page();
    await userEvent.setup().click(screen.getByRole("tab", { name: "Templates" }));
    expect(await screen.findByLabelText("Approval for payment_success")).toBeInTheDocument();
    expect(screen.queryByLabelText("Approval for certificate_available")).toBeNull();
    expect(screen.getByText(/certificate_available/)).toBeInTheDocument();
  });

  it("shows a readable failure reason", async () => {
    notificationService.adminHistory.mockResolvedValue({ results: [{ ...ROW, last_error_code: "invalid_recipient" }], page: 1, num_pages: 1 });
    page();
    await userEvent.setup().click(screen.getByRole("tab", { name: "Delivery log" }));
    expect(await screen.findByText("Number not on WhatsApp")).toBeInTheDocument();
  });

  it("validates reminder offsets before saving settings", async () => {
    notificationService.adminSettings.mockResolvedValue({
      reminder_offsets_minutes: [1440, 30], schedule_notifications_enabled: true, weekly_summary_enabled: true,
      inactivity_reminders_enabled: true, inactivity_days: 7, inactivity_max_reminders: 2, send_rate_per_minute: 600,
    });
    page();
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: "Settings" }));
    const field = await screen.findByLabelText("Class reminders (minutes before start)");
    await user.clear(field);
    await user.type(field, "abc");
    await user.click(screen.getByRole("button", { name: "Save settings" }));
    expect(await screen.findByText(/whole minute values/i)).toBeInTheDocument();
    expect(notificationService.adminUpdateSettings).not.toHaveBeenCalled();

    notificationService.adminUpdateSettings.mockResolvedValue({
      reminder_offsets_minutes: [60], schedule_notifications_enabled: true, weekly_summary_enabled: true,
      inactivity_reminders_enabled: true, inactivity_days: 7, inactivity_max_reminders: 2, send_rate_per_minute: 600,
    });
    await user.clear(field);
    await user.type(field, "60");
    await user.click(screen.getByRole("button", { name: "Save settings" }));
    await waitFor(() =>
      expect(notificationService.adminUpdateSettings).toHaveBeenCalledWith(expect.objectContaining({ reminder_offsets_minutes: [60] })),
    );
  });

  it("requires a recipient preview and confirmation before announcing", async () => {
    notificationService.adminAnnouncementPreview.mockResolvedValue({ recipients: 42, cap: 2000 });
    notificationService.adminAnnounce.mockResolvedValue({});
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    page();
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: "Announcements" }));
    expect(screen.getByRole("button", { name: /preview recipients/i })).toBeDisabled();

    await user.type(screen.getByLabelText("Title"), "Holiday");
    await user.type(screen.getByLabelText("Message"), "No class Friday");
    expect(screen.queryByRole("button", { name: /^send to/i })).toBeNull();

    await user.click(screen.getByRole("button", { name: /preview recipients/i }));
    await user.click(await screen.findByRole("button", { name: "Send to 42" }));
    expect(confirm).toHaveBeenCalled();
    await waitFor(() =>
      expect(notificationService.adminAnnounce).toHaveBeenCalledWith({ title: "Holiday", text: "No class Friday", course: "", confirm_recipient_count: 42 }),
    );
  });

  it("refuses to send when the audience exceeds the cap", async () => {
    notificationService.adminAnnouncementPreview.mockResolvedValue({ recipients: 5000, cap: 2000 });
    page();
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: "Announcements" }));
    await user.type(screen.getByLabelText("Title"), "T");
    await user.type(screen.getByLabelText("Message"), "M");
    await user.click(screen.getByRole("button", { name: /preview recipients/i }));
    expect(await screen.findByRole("button", { name: "Send to 5000" })).toBeDisabled();
  });
});
