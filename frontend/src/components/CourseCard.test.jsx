import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import CourseCard from "../components/CourseCard";
import { toApiError } from "../services/apiClient";

/**
 * Component + service tests focused on the behaviours that would be *security* bugs
 * if they regressed, rather than on markup details.
 */

function baseCourse(overrides = {}) {
  return {
    id: "course-1",
    title: "Constitutional Law Foundations",
    slug: "constitutional-law-foundations",
    subtitle: "From Preamble to Fundamental Duties",
    summary: "A complete walkthrough of the Indian Constitution.",
    thumbnail_url: null,
    instructor: { id: "u1", name: "Adv. Meera Krishnan" },
    price: "1999.00",
    status: "published",
    unlock_rule: "subscription",
    level: "Beginner",
    language: "English",
    duration_minutes: 120,
    lesson_count: 8,
    published_at: "2026-01-01T00:00:00Z",
    is_accessible: false,
    access_reason: "subscription_required",
    progress_percentage: 0,
    ...overrides,
  };
}

function renderCard(course) {
  return render(
    <MemoryRouter>
      <CourseCard course={course} />
    </MemoryRouter>,
  );
}

describe("CourseCard", () => {
  it("renders the title, instructor and lesson count", () => {
    renderCard(baseCourse());
    expect(
      screen.getByText("Constitutional Law Foundations"),
    ).toBeInTheDocument();
    expect(screen.getByText(/Adv. Meera Krishnan/)).toBeInTheDocument();
    expect(screen.getByText(/8 lessons/)).toBeInTheDocument();
  });

  it("marks an inaccessible course as locked", () => {
    renderCard(baseCourse({ is_accessible: false }));
    expect(screen.getByText("Locked")).toBeInTheDocument();
    // The CTA must not imply the student can already watch it.
    expect(
      screen.getByRole("link", { name: /view course/i }),
    ).toBeInTheDocument();
  });

  it("marks an accessible course as continue-able with progress", () => {
    renderCard(
      baseCourse({
        is_accessible: true,
        access_reason: "active_subscription",
        progress_percentage: 45,
      }),
    );
    expect(screen.getByText("In progress")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /continue/i })).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute(
      "aria-valuenow",
      "45",
    );
  });

  it("labels a free course as free rather than locked", () => {
    renderCard(baseCourse({ unlock_rule: "free", is_accessible: true }));
    expect(screen.getByText("Free")).toBeInTheDocument();
    expect(screen.queryByText("Locked")).not.toBeInTheDocument();
    expect(screen.getByText("Included free")).toBeInTheDocument();
  });

  it("hides the progress bar when progress is zero", () => {
    renderCard(baseCourse({ is_accessible: true, progress_percentage: 0 }));
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("exposes a labelled link to the course page", () => {
    renderCard(baseCourse());
    expect(
      screen.getByRole("link", {
        name: /view constitutional law foundations/i,
      }),
    ).toHaveAttribute("href", "/courses/constitutional-law-foundations");
  });
});

describe("toApiError", () => {
  it("unwraps the backend error envelope", () => {
    const error = {
      response: {
        status: 403,
        data: {
          error: {
            code: "subscription_expired",
            message: "Your subscription has expired.",
            details: { reason: "subscription_expired" },
          },
        },
      },
    };

    const normalised = toApiError(error);
    expect(normalised.status).toBe(403);
    expect(normalised.code).toBe("subscription_expired");
    expect(normalised.message).toBe("Your subscription has expired.");
    expect(normalised.isNetworkError).toBe(false);
  });

  it("produces a usable message when there is no response at all", () => {
    const normalised = toApiError(new Error("Network Error"));
    expect(normalised.status).toBe(0);
    expect(normalised.code).toBe("network_error");
    expect(normalised.isNetworkError).toBe(true);
    expect(normalised.message).toMatch(/could not reach the server/i);
  });

  it("reports timeouts distinctly so the UI can suggest a retry", () => {
    const normalised = toApiError({ code: "ECONNABORTED" });
    expect(normalised.code).toBe("timeout");
    expect(normalised.message).toMatch(/too long/i);
  });

  it("falls back to a generic message for an unrecognised envelope", () => {
    const normalised = toApiError({ response: { status: 500, data: {} } });
    expect(normalised.status).toBe(500);
    expect(normalised.code).toBe("http_error");
    expect(normalised.message).toBeTruthy();
  });
});
