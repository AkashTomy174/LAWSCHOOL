import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AuthContext } from "../../context/AuthContext";
import liveService from "../../services/liveService";
import Dashboard from "./Dashboard";

vi.mock("../../services/liveService", () => ({ default: { mine: vi.fn() } }));
vi.mock("../../services/courseService", () => ({
  default: { list: vi.fn().mockResolvedValue({ results: [] }) },
}));
vi.mock("../../services/paymentService", () => ({
  subscriptionService: { mine: vi.fn().mockResolvedValue({ active: null, history: [] }) },
}));
vi.mock("../../services/quizService", () => ({
  quizService: { myAttempts: vi.fn().mockResolvedValue({ count: 0, results: [] }) },
  leaderboardService: { me: vi.fn().mockResolvedValue({ rank: null }) },
}));
vi.mock("../../services/videoService", () => ({
  default: { myProgress: vi.fn().mockResolvedValue({ results: [] }) },
}));

const renderAs = (role) =>
  render(
    <AuthContext.Provider value={{ user: { role, name: "Rahul Sharma" } }}>
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    </AuthContext.Provider>,
  );

beforeEach(() => vi.clearAllMocks());

describe("dashboard live classes", () => {
  it("lists a learner's next classes, live first, and hides ended ones", async () => {
    liveService.mine.mockResolvedValue([
      { id: "1", title: "Bail Clinic", course_title: "CrPC", status: "live",
        scheduled_start: "2026-10-21T13:00:00Z" },
      { id: "2", title: "Writs Q&A", course_title: "Constitution", status: "upcoming",
        scheduled_start: "2026-10-22T13:00:00Z" },
      { id: "3", title: "Old Session", course_title: "CrPC", status: "ended",
        scheduled_start: "2026-10-18T13:00:00Z" },
    ]);
    renderAs("student");
    const block = await screen.findByRole("region", { name: "Live classes" });
    expect(await within(block).findByText("Bail Clinic")).toBeInTheDocument();
    expect(within(block).getByText("Live now")).toBeInTheDocument();
    expect(within(block).getByText("Writs Q&A")).toBeInTheDocument();
    expect(within(block).queryByText("Old Session")).toBeNull();
    expect(within(block).getByRole("link", { name: "View all" })).toHaveAttribute("href", "/live");
  });

  it("says when nothing is scheduled", async () => {
    liveService.mine.mockResolvedValue([]);
    renderAs("student");
    expect(await screen.findByText("No upcoming live classes.")).toBeInTheDocument();
  });

  it("degrades quietly when live classes fail to load", async () => {
    liveService.mine.mockRejectedValue({ status: 500, message: "boom" });
    renderAs("student");
    expect(await screen.findByText("Live classes are unavailable right now.")).toBeInTheDocument();
  });

  it("staff neither fetch nor see the learner block", async () => {
    renderAs("instructor");
    await screen.findByRole("heading", { level: 1 });
    expect(screen.queryByRole("region", { name: "Live classes" })).toBeNull();
    expect(liveService.mine).not.toHaveBeenCalled();
  });
});
