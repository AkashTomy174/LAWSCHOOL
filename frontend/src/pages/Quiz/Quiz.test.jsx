import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { quizService } from "../../services/quizService";
import Quiz from "./Quiz";

vi.mock("../../services/quizService", () => ({
  quizService: {
    quiz: vi.fn(),
    progress: vi.fn(),
    start: vi.fn(),
    submit: vi.fn(),
  },
}));

const QUIZ = {
  id: "q1",
  title: "Bail Basics",
  description: "Two questions on bail.",
  pass_percentage: 60,
  max_attempts: 3,
  time_limit_minutes: null,
  question_count: 1,
  available_from: null,
  available_until: null,
};

const PROGRESS = {
  quiz: { id: "q1", title: "Bail Basics" },
  in_progress_attempt: null,
  attempts_used: 0,
  attempts_allowed: 3,
  attempts_remaining: 3,
  best_attempt: null,
};

const STARTED = {
  attempt: { id: "a1", started_at: new Date().toISOString() },
  attempts_remaining: 3,
  quiz: {
    ...QUIZ,
    questions: [
      {
        id: "qq1",
        text: "Which section governs bail?",
        marks: 1,
        options: [
          { id: "o1", text: "Section 480" },
          { id: "o2", text: "Section 436" },
        ],
      },
    ],
  },
};

function apiError(message, code) {
  return Object.assign(new Error(message), { code });
}

function renderQuiz() {
  return render(
    <MemoryRouter initialEntries={["/quiz/q1"]}>
      <Routes>
        <Route path="/quiz/:quizId" element={<Quiz />} />
        <Route path="/quiz/:quizId/result" element={<div>Result screen</div>} />
        <Route path="/dashboard" element={<div>Dashboard screen</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  quizService.quiz.mockResolvedValue(QUIZ);
  quizService.progress.mockResolvedValue(PROGRESS);
  quizService.start.mockResolvedValue(STARTED);
});

describe("quiz intro", () => {
  it("shows a loading state, then the quiz details, without starting an attempt", async () => {
    const { container } = renderQuiz();
    expect(container.querySelector("[aria-busy='true']")).not.toBeNull();

    expect(await screen.findByRole("heading", { name: "Bail Basics" })).toBeInTheDocument();
    expect(screen.getByText("Two questions on bail.")).toBeInTheDocument();
    expect(screen.getByText("0 of 3 used")).toBeInTheDocument();
    expect(screen.getByText("60%")).toBeInTheDocument();
    expect(quizService.start).not.toHaveBeenCalled();
  });

  it("starts an attempt only when the student clicks Start", async () => {
    renderQuiz();
    await userEvent.click(await screen.findByRole("button", { name: "Start quiz" }));
    expect(quizService.start).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("Which section governs bail?")).toBeInTheDocument();
  });

  it("offers Resume when an attempt is already open", async () => {
    quizService.progress.mockResolvedValue({
      ...PROGRESS,
      in_progress_attempt: { id: "a1", started_at: new Date().toISOString() },
    });
    renderQuiz();
    expect(await screen.findByRole("button", { name: "Resume attempt" })).toBeInTheDocument();
  });

  it("blocks a new attempt when the allowance is used up", async () => {
    quizService.progress.mockResolvedValue({
      ...PROGRESS,
      attempts_used: 3,
      attempts_remaining: 0,
      best_attempt: { id: "a9", score: 1, max_score: 2, percentage: "50.00", passed: false },
    });
    renderQuiz();
    expect(await screen.findByText(/used all your attempts/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /start|resume/i })).toBeNull();
    expect(screen.getByRole("link", { name: "View best result" })).toHaveAttribute(
      "href",
      "/quiz/q1/result?attempt=a9",
    );
  });

  it("explains a quiz that has not opened yet", async () => {
    quizService.quiz.mockResolvedValue({
      ...QUIZ,
      available_from: new Date(Date.now() + 86_400_000).toISOString(),
    });
    renderQuiz();
    expect(await screen.findByText(/^Opens /)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start quiz" })).toBeNull();
  });

  it("shows an error when the quiz cannot be loaded", async () => {
    quizService.quiz.mockRejectedValue(apiError("Not found.", "not_found"));
    renderQuiz();
    expect(await screen.findByRole("heading", { name: "Quiz unavailable" })).toBeInTheDocument();
  });

  it("shows the locked state when the server refuses to start", async () => {
    quizService.start.mockRejectedValue(
      apiError("An active subscription is required for this course.", "subscription_required"),
    );
    renderQuiz();
    await userEvent.click(await screen.findByRole("button", { name: "Start quiz" }));
    expect(await screen.findByRole("heading", { name: "Quiz locked" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View plans" })).toBeInTheDocument();
  });
});

describe("quiz attempt", () => {
  it("submits the chosen answer and moves to the result", async () => {
    quizService.submit.mockResolvedValue({ attempt: { id: "a1" } });
    renderQuiz();
    await userEvent.click(await screen.findByRole("button", { name: "Start quiz" }));
    await userEvent.click(await screen.findByRole("radio", { name: /Section 480/ }));
    // One question: there is no "Save and next", the sidebar goes to review.
    await userEvent.click(screen.getAllByRole("button", { name: /review and submit/i })[0]);
    await userEvent.click(await screen.findByRole("button", { name: "Submit answers" }));

    await waitFor(() =>
      expect(quizService.submit).toHaveBeenCalledWith(
        "a1",
        expect.objectContaining({ answers: { qq1: "o1" } }),
      ),
    );
    expect(await screen.findByText("Result screen")).toBeInTheDocument();
  });

  it("keeps the student's answers and lets them retry when a submission is rejected", async () => {
    quizService.submit
      .mockRejectedValueOnce(apiError("Please try again shortly.", "service_unavailable"))
      .mockResolvedValueOnce({ attempt: { id: "a1" } });
    renderQuiz();
    await userEvent.click(await screen.findByRole("button", { name: "Start quiz" }));
    await userEvent.click(await screen.findByRole("radio", { name: /Section 480/ }));
    await userEvent.click(screen.getAllByRole("button", { name: /review and submit/i })[0]);
    await userEvent.click(await screen.findByRole("button", { name: "Submit answers" }));

    expect(await screen.findByText(/try again shortly/i)).toBeInTheDocument();
    // Still on the attempt screen, not bounced to the intro or result.
    expect(screen.queryByText("Result screen")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Submit answers" }));
    expect(await screen.findByText("Result screen")).toBeInTheDocument();
    expect(quizService.submit).toHaveBeenLastCalledWith(
      "a1",
      expect.objectContaining({ answers: { qq1: "o1" } }),
    );
  });
});
