import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import notificationService from "../../services/notificationService";
import WhatsAppSettings from "./WhatsAppSettings";

vi.mock("../../services/notificationService", () => ({
  default: {
    getPreferences: vi.fn(),
    updatePreferences: vi.fn(),
    requestLink: vi.fn(),
    verify: vi.fn(),
    optOut: vi.fn(),
    history: vi.fn(),
  },
}));
const pushToast = vi.fn();
vi.mock("../../context/UIContext", () => ({ useUI: () => ({ pushToast }) }));

const UNLINKED = {
  whatsapp_available: true,
  is_verified: false,
  whatsapp_number_masked: "",
  whatsapp_enabled: false,
  consent_status: "none",
  study_reminders_paused_until: null,
  live_class_enabled: true,
  schedule_change_enabled: true,
  quiz_updates_enabled: true,
  progress_updates_enabled: true,
  study_reminders_enabled: true,
  payment_updates_enabled: true,
  announcements_enabled: true,
};
const LINKED = { ...UNLINKED, is_verified: true, whatsapp_enabled: true, consent_status: "opted_in", whatsapp_number_masked: "+91*****3210" };

const page = () => render(<MemoryRouter><WhatsAppSettings /></MemoryRouter>);

beforeEach(() => {
  vi.clearAllMocks();
  notificationService.history.mockResolvedValue({ results: [] });
});

describe("WhatsApp settings", () => {
  it("shows a loading skeleton, then the form", async () => {
    notificationService.getPreferences.mockReturnValue(new Promise(() => {}));
    page();
    expect(screen.queryByLabelText("WhatsApp number")).toBeNull();
  });

  it("offers retry when preferences fail to load", async () => {
    notificationService.getPreferences.mockRejectedValue(new Error("down"));
    page();
    expect(await screen.findByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("explains when WhatsApp is not enabled on the server and blocks linking", async () => {
    notificationService.getPreferences.mockResolvedValue({ ...UNLINKED, whatsapp_available: false });
    page();
    expect(await screen.findByText("Not available yet")).toBeInTheDocument();
    expect(screen.getByLabelText("WhatsApp number")).toBeDisabled();
    expect(screen.getByRole("button", { name: /send verification code/i })).toBeDisabled();
  });

  it("validates the number and requires explicit consent before calling the API", async () => {
    notificationService.getPreferences.mockResolvedValue(UNLINKED);
    page();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /send verification code/i }));
    expect(await screen.findByText("Enter your WhatsApp number.")).toBeInTheDocument();
    expect(screen.getByText("Please agree to receive WhatsApp messages.")).toBeInTheDocument();

    await user.type(screen.getByLabelText("WhatsApp number"), "98765");
    await user.click(screen.getByRole("button", { name: /send verification code/i }));
    expect(await screen.findByText(/include the country code/i)).toBeInTheDocument();
    expect(notificationService.requestLink).not.toHaveBeenCalled();
  });

  it("links a number: consent, code, verify", async () => {
    notificationService.getPreferences.mockResolvedValue(UNLINKED);
    notificationService.requestLink.mockResolvedValue({ detail: "ok" });
    notificationService.verify.mockResolvedValue(LINKED);
    page();
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText("WhatsApp number"), "+919876543210");
    await user.click(screen.getByRole("checkbox", { name: /i agree to receive/i }));
    await user.click(screen.getByRole("button", { name: /send verification code/i }));
    await waitFor(() =>
      expect(notificationService.requestLink).toHaveBeenCalledWith({ phone: "+919876543210", consent: true }),
    );

    await user.type(await screen.findByLabelText("Verification code"), "12ab3456");
    expect(screen.getByLabelText("Verification code")).toHaveValue("123456"); // digits only
    await user.click(screen.getByRole("button", { name: "Verify" }));
    await waitFor(() => expect(notificationService.verify).toHaveBeenCalledWith("123456"));
    expect(await screen.findByText("Verified")).toBeInTheDocument();
    expect(screen.getByText("+91*****3210")).toBeInTheDocument();
  });

  it("rejects a malformed code locally", async () => {
    notificationService.getPreferences.mockResolvedValue(UNLINKED);
    notificationService.requestLink.mockResolvedValue({});
    page();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("WhatsApp number"), "+919876543210");
    await user.click(screen.getByRole("checkbox", { name: /i agree to receive/i }));
    await user.click(screen.getByRole("button", { name: /send verification code/i }));
    await user.type(await screen.findByLabelText("Verification code"), "123");
    await user.click(screen.getByRole("button", { name: "Verify" }));
    expect(await screen.findByText("Enter the 6-digit code.")).toBeInTheDocument();
    expect(notificationService.verify).not.toHaveBeenCalled();
  });

  it("shows the server's message when verification fails", async () => {
    notificationService.getPreferences.mockResolvedValue(UNLINKED);
    notificationService.requestLink.mockResolvedValue({});
    notificationService.verify.mockRejectedValue(new Error("That code is not correct."));
    page();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("WhatsApp number"), "+919876543210");
    await user.click(screen.getByRole("checkbox", { name: /i agree to receive/i }));
    await user.click(screen.getByRole("button", { name: /send verification code/i }));
    await user.type(await screen.findByLabelText("Verification code"), "000000");
    await user.click(screen.getByRole("button", { name: "Verify" }));
    expect(await screen.findByText("That code is not correct.")).toBeInTheDocument();
  });

  it("loads preferences and updates a category with a PATCH", async () => {
    notificationService.getPreferences.mockResolvedValue(LINKED);
    notificationService.updatePreferences.mockResolvedValue({ ...LINKED, quiz_updates_enabled: false });
    page();
    const user = userEvent.setup();
    const box = await screen.findByRole("checkbox", { name: /quiz updates/i });
    expect(box).toBeChecked();
    await user.click(box);
    await waitFor(() =>
      expect(notificationService.updatePreferences).toHaveBeenCalledWith({ quiz_updates_enabled: false }),
    );
    await waitFor(() => expect(screen.getByRole("checkbox", { name: /quiz updates/i })).not.toBeChecked());
  });

  it("only offers categories the platform can send", async () => {
    notificationService.getPreferences.mockResolvedValue(LINKED);
    page();
    await screen.findByRole("checkbox", { name: /quiz updates/i });
    expect(screen.queryByRole("checkbox", { name: /assignment/i })).toBeNull();
  });

  it("disables category switches until a number is verified", async () => {
    notificationService.getPreferences.mockResolvedValue(UNLINKED);
    page();
    expect(await screen.findByRole("checkbox", { name: /live classes/i })).toBeDisabled();
  });

  it("opts out only after confirmation", async () => {
    notificationService.getPreferences.mockResolvedValue(LINKED);
    notificationService.optOut.mockResolvedValue({ ...LINKED, whatsapp_enabled: false, consent_status: "opted_out" });
    const confirm = vi.spyOn(window, "confirm");
    page();
    const user = userEvent.setup();
    const button = await screen.findByRole("button", { name: /opt out of all/i });

    confirm.mockReturnValueOnce(false);
    await user.click(button);
    expect(notificationService.optOut).not.toHaveBeenCalled();

    confirm.mockReturnValueOnce(true);
    await user.click(button);
    await waitFor(() => expect(notificationService.optOut).toHaveBeenCalled());
    expect(await screen.findByText("Opted out")).toBeInTheDocument();
  });

  it("does not claim queued messages were delivered", async () => {
    notificationService.getPreferences.mockResolvedValue(LINKED);
    notificationService.history.mockResolvedValue({
      results: [{ id: "1", template_name: "payment_success", status: "accepted", status_label: "Accepted by WhatsApp", created_at: "2026-10-18T10:00:00Z" }],
    });
    page();
    expect(await screen.findByText("Accepted by WhatsApp")).toBeInTheDocument();
    expect(screen.queryByText("Delivered")).toBeNull();
  });
});
