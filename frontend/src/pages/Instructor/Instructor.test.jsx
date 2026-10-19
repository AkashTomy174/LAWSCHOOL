import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import courseService from "../../services/courseService";
import liveService from "../../services/liveService";
import InstructorDashboard from "./InstructorDashboard";
import LiveClasses from "./LiveClasses";
import ManageCourses from "./ManageCourses";

vi.mock("../../services/courseService", () => ({
  default: {
    instructorDashboard: vi.fn(),
    list: vi.fn(),
    listSections: vi.fn(),
    listLessons: vi.fn(),
  },
}));
vi.mock("../../services/quizService", () => ({ default: { list: vi.fn().mockResolvedValue([]) } }));
vi.mock("../../services/liveService", () => ({
  default: { list: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn() },
}));
vi.mock("../../context/UIContext", () => ({ useUI: () => ({ pushToast: vi.fn() }) }));

const page = (ui) => render(<MemoryRouter>{ui}</MemoryRouter>);
const never = () => new Promise(() => {});

beforeEach(() => vi.clearAllMocks());

describe("Teaching overview", () => {
  it("shows an error state with retry when the API fails", async () => {
    courseService.instructorDashboard.mockRejectedValue(new Error("boom"));
    page(<InstructorDashboard />);
    expect(await screen.findByRole("button", { name: /try again|retry/i })).toBeInTheDocument();
  });

  it("shows the empty state when the instructor has no courses", async () => {
    courseService.instructorDashboard.mockResolvedValue({
      totals: {}, courses: [], upcoming_live_classes: [], recent_attempts: [],
    });
    page(<InstructorDashboard />);
    expect(await screen.findByText("No courses yet")).toBeInTheDocument();
    expect(screen.getByText("Nothing scheduled.")).toBeInTheDocument();
    expect(screen.getByText("No attempts yet.")).toBeInTheDocument();
  });

  it("loads only the teaching endpoint (no users/payments/subscriptions)", async () => {
    courseService.instructorDashboard.mockResolvedValue({
      totals: {}, courses: [], upcoming_live_classes: [], recent_attempts: [],
    });
    page(<InstructorDashboard />);
    await screen.findByText("No courses yet");
    expect(courseService.instructorDashboard).toHaveBeenCalledTimes(1);
    expect(courseService.list).not.toHaveBeenCalled();
  });
});

describe("Live classes", () => {
  it("shows a skeleton while loading", () => {
    liveService.list.mockReturnValue(never());
    courseService.list.mockReturnValue(never());
    const { container } = page(<LiveClasses />);
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();
  });

  it("shows the empty state", async () => {
    liveService.list.mockResolvedValue([]);
    courseService.list.mockResolvedValue({ results: [{ id: "c1", title: "Course 1", slug: "c1" }] });
    page(<LiveClasses />);
    expect(await screen.findByText("No live classes yet")).toBeInTheDocument();
  });

  it("lists classes and asks for own courses only", async () => {
    liveService.list.mockResolvedValue([
      { id: "l1", course: "c1", title: "Bail basics", scheduled_start: "2030-01-01T10:00:00Z", duration_minutes: 60, is_published: false },
    ]);
    courseService.list.mockResolvedValue({ results: [{ id: "c1", title: "Course 1", slug: "c1" }] });
    page(<LiveClasses />);
    expect(await screen.findByText("Bail basics")).toBeInTheDocument();
    expect(screen.getByText("Draft")).toBeInTheDocument();
    expect(courseService.list).toHaveBeenCalledWith(expect.objectContaining({ scope: "mine" }));
  });

  it("shows an error state when listing fails", async () => {
    liveService.list.mockRejectedValue(new Error("down"));
    courseService.list.mockResolvedValue({ results: [] });
    page(<LiveClasses />);
    expect(await screen.findByRole("button", { name: /try again|retry/i })).toBeInTheDocument();
  });
});

describe("Manage courses", () => {
  it("shows the empty state when no course is assigned", async () => {
    courseService.list.mockResolvedValue({ results: [] });
    page(<ManageCourses />);
    expect(await screen.findByText("No courses to manage")).toBeInTheDocument();
  });

  it("asks only for the caller's own courses", async () => {
    courseService.list.mockResolvedValue({ results: [] });
    page(<ManageCourses />);
    await screen.findByText("No courses to manage");
    expect(courseService.list).toHaveBeenCalledWith(expect.objectContaining({ scope: "mine" }));
  });

  it("renders sections with their lessons and an empty section message", async () => {
    courseService.list.mockResolvedValue({ results: [{ id: "c1", slug: "c1", title: "Course 1", status: "published" }] });
    courseService.listSections.mockResolvedValue([
      { id: "s1", title: "Intro", ordering: 1, is_published: true },
      { id: "s2", title: "Empty one", ordering: 2, is_published: false },
    ]);
    courseService.listLessons.mockResolvedValue([
      { id: "x1", section: "s1", title: "Lesson A", ordering: 1, status: "published", is_preview: false },
      { id: "x2", section: "other-course-section", title: "Not mine", ordering: 1, status: "draft" },
    ]);
    page(<ManageCourses />);
    expect(await screen.findByText(/Lesson A/)).toBeInTheDocument();
    expect(screen.queryByText(/Not mine/)).not.toBeInTheDocument();
    expect(screen.getByText("No lessons in this section.")).toBeInTheDocument();
  });

  it("shows an error state when the course tree fails to load", async () => {
    courseService.list.mockResolvedValue({ results: [{ id: "c1", slug: "c1", title: "Course 1", status: "draft" }] });
    courseService.listSections.mockRejectedValue(new Error("nope"));
    courseService.listLessons.mockResolvedValue([]);
    page(<ManageCourses />);
    expect(await screen.findByRole("button", { name: /try again|retry/i })).toBeInTheDocument();
  });
});
