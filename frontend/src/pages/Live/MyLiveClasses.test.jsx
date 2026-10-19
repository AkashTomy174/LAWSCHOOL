import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import liveService from "../../services/liveService";
import MyLiveClasses from "./MyLiveClasses";

vi.mock("../../services/liveService", () => ({
  default: { mine: vi.fn(), join: vi.fn() },
}));

const row = (over) => ({
  id: "c1",
  title: "Bail Clinic",
  course_title: "Criminal Procedure",
  course_slug: "criminal-procedure",
  instructor_name: "Adv. Meera",
  scheduled_start: "2026-10-21T13:00:00Z",
  duration_minutes: 60,
  status: "upcoming",
  can_join: false,
  ...over,
});

const renderPage = () =>
  render(
    <MemoryRouter>
      <MyLiveClasses />
    </MemoryRouter>,
  );

beforeEach(() => vi.clearAllMocks());

describe("student live classes", () => {
  it("groups classes by server status and shows course, instructor and local time", async () => {
    liveService.mine.mockResolvedValue([
      row({ id: "a", title: "Now", status: "live", can_join: true }),
      row({ id: "b", title: "Later" }),
      row({ id: "c", title: "Done", status: "ended" }),
    ]);
    renderPage();

    const live = await screen.findByRole("region", { name: "Live now" });
    expect(within(live).getByText("Now")).toBeInTheDocument();
    expect(within(live).getByRole("button", { name: "Join class" })).toBeInTheDocument();

    const upcoming = screen.getByRole("region", { name: "Upcoming" });
    expect(within(upcoming).getByText("You can join 15 minutes before it starts.")).toBeInTheDocument();
    expect(within(upcoming).getByRole("link", { name: "Criminal Procedure" })).toHaveAttribute(
      "href",
      "/courses/criminal-procedure",
    );
    expect(within(upcoming).getByText(/Adv\. Meera/)).toBeInTheDocument();
    // Rendered from the ISO timestamp in the browser's own timezone.
    const local = new Date("2026-10-21T13:00:00Z").toLocaleString("en-IN", {
      day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
    });
    expect(within(upcoming).getByText(new RegExp(local.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))))
      .toBeInTheDocument();

    const ended = screen.getByRole("region", { name: "Recently ended" });
    expect(within(ended).getByText("This class has ended.")).toBeInTheDocument();
    expect(within(ended).queryByRole("button")).toBeNull();
  });

  it("fetches the authorized link on join and opens it in a new tab", async () => {
    liveService.mine.mockResolvedValue([row({ status: "live", can_join: true })]);
    liveService.join.mockResolvedValue({ meeting_url: "https://zoom.us/j/123" });
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: "Join class" }));
    const link = await screen.findByRole("link", { name: "Open meeting" });
    expect(liveService.join).toHaveBeenCalledWith("c1");
    expect(link).toHaveAttribute("href", "https://zoom.us/j/123");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("explains a refused join and never renders a link", async () => {
    liveService.mine.mockResolvedValue([row({ status: "live", can_join: true })]);
    liveService.join.mockRejectedValue({
      status: 403,
      code: "subscription_required",
      message: "An active subscription is required for this course.",
    });
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: "Join class" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("An active subscription is required");
    expect(screen.queryByRole("link", { name: "Open meeting" })).toBeNull();
  });

  it("refuses to render a non-web meeting link", async () => {
    liveService.mine.mockResolvedValue([row({ status: "live", can_join: true })]);
    liveService.join.mockResolvedValue({ meeting_url: "javascript:alert(1)" });
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: "Join class" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("valid meeting link");
    expect(screen.queryByRole("link", { name: "Open meeting" })).toBeNull();
  });

  it("shows the empty state", async () => {
    liveService.mine.mockResolvedValue([]);
    renderPage();
    expect(await screen.findByText("No live classes scheduled")).toBeInTheDocument();
  });

  it("shows a loading state, then an error with a working retry", async () => {
    let fail;
    liveService.mine
      .mockReturnValueOnce(new Promise((_, reject) => { fail = reject; }))
      .mockResolvedValueOnce([row()]);
    renderPage();
    expect(document.querySelector(".animate-pulse")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Upcoming" })).toBeNull();

    fail({ status: 500, message: "Server error." });
    expect(await screen.findByText("Server error.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("region", { name: "Upcoming" })).toBeInTheDocument();
  });
});
