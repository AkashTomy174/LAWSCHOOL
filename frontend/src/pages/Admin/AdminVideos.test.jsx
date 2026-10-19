import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AuthContext } from "../../context/AuthContext";
import courseService from "../../services/courseService";
import videoService from "../../services/videoService";
import { AdminVideos } from "./AdminPages";

vi.mock("../../services/courseService", () => ({
  default: { lessonsWithoutVideo: vi.fn() },
}));
vi.mock("../../services/videoService", () => ({
  default: { list: vi.fn(), sync: vi.fn(), directUploadUrl: vi.fn(), registerLessonVideo: vi.fn() },
}));
vi.mock("../../context/UIContext", () => ({ useUI: () => ({ pushToast: vi.fn() }) }));

const lesson = (n) => ({ id: `l${n}`, title: `Lesson ${n}`, course_title: "Evidence" });
const page = (from, to, next) => ({
  count: 105,
  next,
  results: Array.from({ length: to - from + 1 }, (_, i) => lesson(from + i)),
});

function renderPage() {
  return render(
    <AuthContext.Provider value={{ isAdmin: false }}>
      <MemoryRouter>
        <AdminVideos />
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  videoService.list.mockResolvedValue([]);
});

describe("video lesson picker", () => {
  it("loads lessons beyond the first page and keeps the selection", async () => {
    courseService.lessonsWithoutVideo
      .mockResolvedValueOnce(page(1, 100, "?page=2"))
      .mockResolvedValueOnce(page(101, 105, null));
    renderPage();
    const select = await screen.findByLabelText(/Attach to lesson/);
    await waitFor(() => expect(select).toBeEnabled());
    expect(screen.queryByRole("option", { name: "Evidence — Lesson 105" })).toBeNull();

    await userEvent.selectOptions(select, "l7");
    await userEvent.click(screen.getByRole("button", { name: "Load more lessons" }));

    expect(await screen.findByRole("option", { name: "Evidence — Lesson 105" })).toBeInTheDocument();
    expect(select).toHaveValue("l7");
    expect(courseService.lessonsWithoutVideo).toHaveBeenLastCalledWith({ search: "", page: 2 });
    expect(screen.queryByRole("button", { name: "Load more lessons" })).toBeNull();
  });

  it("searches on the server and keeps the chosen lesson listed", async () => {
    courseService.lessonsWithoutVideo
      .mockResolvedValueOnce(page(1, 3, null))
      .mockResolvedValueOnce({ count: 0, next: null, results: [] });
    renderPage();
    const select = await screen.findByLabelText(/Attach to lesson/);
    await waitFor(() => expect(select).toBeEnabled());
    await userEvent.selectOptions(select, "l2");

    await userEvent.type(screen.getByLabelText("Search lessons"), "writ");
    expect(await screen.findByText("No lessons match that search.")).toBeInTheDocument();
    expect(courseService.lessonsWithoutVideo).toHaveBeenLastCalledWith({ search: "writ" });
    expect(screen.getByLabelText(/Attach to lesson/)).toHaveValue("l2");
  });

  it("says so when every lesson already has a video", async () => {
    courseService.lessonsWithoutVideo.mockResolvedValue({ count: 0, next: null, results: [] });
    renderPage();
    expect(await screen.findByText("Every lesson already has a video.")).toBeInTheDocument();
  });

  it("shows an error with a working retry when the lesson list fails", async () => {
    courseService.lessonsWithoutVideo
      .mockRejectedValueOnce({ status: 500, message: "Server error." })
      .mockResolvedValueOnce(page(1, 2, null));
    renderPage();
    expect(await screen.findByText("Server error.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("option", { name: "Evidence — Lesson 2" })).toBeInTheDocument();
  });

  it("reports a failed 'load more' without losing the loaded lessons", async () => {
    courseService.lessonsWithoutVideo
      .mockResolvedValueOnce(page(1, 100, "?page=2"))
      .mockRejectedValueOnce({ status: 0, message: "Could not reach the server." });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "Load more lessons" }));
    expect(await screen.findByText("Could not reach the server.")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Evidence — Lesson 100" })).toBeInTheDocument();
  });
});
