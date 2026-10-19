import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AuthContext } from "../../context/AuthContext";
import courseService from "../../services/courseService";
import CourseDetails from "./CourseDetails";

vi.mock("../../services/courseService", () => ({
  default: { detail: vi.fn() },
}));

const COURSE = {
  title: "Criminal Procedure",
  subtitle: "",
  summary: "",
  description: "",
  level: "intermediate",
  language: "English",
  price: "0",
  unlock_rule: "subscription",
  instructor: { name: "Adv. Meera" },
  lesson_count: 0,
  duration_minutes: 0,
  progress_percentage: 0,
  sections: [],
  quiz_count: 1,
  quizzes: [
    {
      id: "q1",
      title: "Bail Basics",
      description: "",
      pass_percentage: 60,
      max_attempts: 3,
      time_limit_minutes: null,
    },
  ],
};

function renderCourse(course) {
  courseService.detail.mockResolvedValue(course);
  return render(
    <AuthContext.Provider value={{ isAuthenticated: true, user: { role: "student" } }}>
      <MemoryRouter initialEntries={["/courses/criminal-procedure"]}>
        <Routes>
          <Route path="/courses/:slug" element={<CourseDetails />} />
          <Route path="/quiz/:quizId" element={<div>Quiz page</div>} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

beforeEach(() => vi.clearAllMocks());

describe("course quizzes", () => {
  it("links an accessible course's quizzes to the quiz page", async () => {
    renderCourse({ ...COURSE, is_accessible: true });
    expect(await screen.findByRole("heading", { name: "Quizzes" })).toBeInTheDocument();
    expect(screen.getByText("Pass mark 60% · 3 attempts · Untimed")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("link", { name: /Bail Basics/ }));
    expect(screen.getByText("Quiz page")).toBeInTheDocument();
  });

  it("lists quizzes on a locked course without linking to them", async () => {
    renderCourse({ ...COURSE, is_accessible: false });
    expect(await screen.findByText("Bail Basics")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Bail Basics/ })).toBeNull();
  });

  it("omits the section when the course has no published quizzes", async () => {
    renderCourse({ ...COURSE, is_accessible: true, quiz_count: 0, quizzes: [] });
    expect(await screen.findByRole("heading", { name: "Criminal Procedure" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Quizzes" })).toBeNull();
  });
});

describe("course load failures", () => {
  function renderAt() {
    return render(
      <AuthContext.Provider value={{ isAuthenticated: false, user: null }}>
        <MemoryRouter initialEntries={["/courses/no-such-course"]}>
          <Routes>
            <Route path="/courses/:slug" element={<CourseDetails />} />
            <Route path="/courses" element={<div>Catalogue</div>} />
          </Routes>
        </MemoryRouter>
      </AuthContext.Provider>,
    );
  }

  it("shows a not-found page with a way back, and never retries a 404", async () => {
    courseService.detail.mockRejectedValue({ status: 404, code: "not_found", message: "Not found." });
    renderAt();
    expect(await screen.findByRole("heading", { name: "Course not found" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
    expect(courseService.detail).toHaveBeenCalledTimes(1);

    await userEvent.click(screen.getByRole("link", { name: "Browse courses" }));
    expect(screen.getByText("Catalogue")).toBeInTheDocument();
  });

  it("offers a retry for a transient failure and recovers", async () => {
    courseService.detail
      .mockRejectedValueOnce({ status: 0, code: "network_error", message: "Could not reach the server." })
      .mockResolvedValueOnce({ ...COURSE, is_accessible: true });
    renderAt();
    expect(await screen.findByText("Could not reach the server.")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { name: "Criminal Procedure" })).toBeInTheDocument();
    expect(courseService.detail).toHaveBeenCalledTimes(2);
  });
});
