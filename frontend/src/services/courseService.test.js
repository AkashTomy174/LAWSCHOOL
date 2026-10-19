import { afterEach, describe, expect, it, vi } from "vitest";

import apiClient from "./apiClient";
import courseService from "./courseService";

afterEach(() => vi.restoreAllMocks());

describe("listLessons", () => {
  it("follows every page of one course so a large course is complete", async () => {
    const lesson = (n) => ({ id: `l${n}` });
    const get = vi
      .spyOn(apiClient, "get")
      .mockResolvedValueOnce({ data: { results: Array.from({ length: 100 }, (_, i) => lesson(i)), next: "p2" } })
      .mockResolvedValueOnce({ data: { results: [lesson(100), lesson(101)], next: null } });

    const lessons = await courseService.listLessons("evidence");

    expect(lessons).toHaveLength(102);
    expect(lessons.at(-1).id).toBe("l101");
    expect(get).toHaveBeenNthCalledWith(1, "/lessons/", {
      params: { course: "evidence", page: 1, page_size: 100 },
    });
    expect(get).toHaveBeenNthCalledWith(2, "/lessons/", {
      params: { course: "evidence", page: 2, page_size: 100 },
    });
  });

  it("returns an empty list for a course without lessons", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: { results: [], next: null } });
    expect(await courseService.listLessons("empty")).toEqual([]);
  });
});
