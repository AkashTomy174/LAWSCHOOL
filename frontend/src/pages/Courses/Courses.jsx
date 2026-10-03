import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import CourseCard from "../../components/CourseCard";
import Icon from "../../components/Icon";
import { EmptyState, ErrorState, Skeleton } from "../../components/ui";
import useAsync from "../../hooks/useAsync";
import courseService from "../../services/courseService";

/**
 * Course catalogue.
 *
 * Filtering, sorting and pagination state lives in the URL
 * (`?page=&search=&level=&ordering=`), not in component state. That makes results
 * shareable and bookmarkable, and it means the back button behaves the way
 * students expect.
 *
 * Searching is debounced, so a page of results is not re-requested on every
 * keystroke.
 */
const PAGE_SIZE = 9;

const LEVELS = ["Beginner", "Intermediate", "Advanced"];
const SORTS = [
  ["-published_at", "Newest first"],
  ["price", "Price, low to high"],
  ["-price", "Price, high to low"],
  ["title", "Title, A to Z"],
];

export default function Courses() {
  const [searchParams, setSearchParams] = useSearchParams();

  const page = Number(searchParams.get("page") || 1);
  const search = searchParams.get("search") || "";
  const level = searchParams.get("level") || "";
  const ordering = searchParams.get("ordering") || "-published_at";

  const [searchInput, setSearchInput] = useState(search);

  const params = useMemo(
    () => ({
      page,
      page_size: PAGE_SIZE,
      ...(search ? { search } : {}),
      ...(level ? { level } : {}),
      ordering,
    }),
    [page, search, level, ordering],
  );

  const { data, loading, error, refetch } = useAsync(
    () => courseService.list(params),
    [params.page, params.search, params.level, params.ordering],
  );

  const updateParams = useCallback(
    (changes) => {
      setSearchParams((current) => {
        const next = new URLSearchParams(current);
        Object.entries(changes).forEach(([key, value]) => {
          if (value === "" || value === undefined || value === null)
            next.delete(key);
          else next.set(key, String(value));
        });
        return next;
      });
    },
    [setSearchParams],
  );

  // Debounce: push the typed value into the URL 400ms after typing stops.
  useEffect(() => {
    if (searchInput === search) return undefined;
    const timer = window.setTimeout(() => {
      updateParams({ search: searchInput, page: 1 });
    }, 400);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchInput]);

  // Keep the input in sync when the URL changes externally (back button, link).
  useEffect(() => {
    setSearchInput(search);
  }, [search]);

  const courses = data?.results || [];
  const totalPages = data?.num_pages || 1;
  const totalCount = data?.count || 0;
  const filtered = Boolean(search || level);

  function clearAll() {
    setSearchInput("");
    setSearchParams({});
  }

  const summary =
    loading || error
      ? " "
      : `${totalCount} course${totalCount === 1 ? "" : "s"}${
          search ? ` for “${search}”` : ""
        }`;

  return (
    <>
      <section className="wrap pb-10 pt-12 lg:pt-16">
        <div className="flex flex-col justify-between gap-8 md:flex-row md:items-end">
          <div className="flex flex-col gap-3">
            <h1 className="d2">Courses</h1>
            <p className="body max-w-[560px]">
              Browse published courses. Every syllabus is visible; lessons open
              once your plan covers the course.
            </p>
          </div>
          <div className="flex w-full flex-col gap-2 md:w-[380px]">
            <label
              htmlFor="course-search"
              className="small font-medium !text-ink"
            >
              Search courses
            </label>
            <div className="flex h-12 items-center gap-2 rounded-lg border border-control bg-card px-3.5 focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-ink">
              <Icon name="search" className="text-ink3" />
              <input
                id="course-search"
                type="search"
                value={searchInput}
                onChange={(event) => setSearchInput(event.target.value)}
                placeholder="Title or topic"
                className="min-w-0 flex-1 border-0 bg-transparent text-[15px] text-ink outline-none placeholder:text-ink3"
              />
            </div>
          </div>
        </div>
      </section>

      <section className="wrap pb-24">
        <div className="grid gap-10 lg:grid-cols-[240px_minmax(0,1fr)] lg:gap-16">
          <aside aria-label="Filters" className="flex flex-col gap-8 lg:pt-2">
            <fieldset className="m-0 flex flex-col gap-1 border-0 p-0">
              <legend className="h4 mb-3 !text-[20px]">Level</legend>
              {[["", "All levels"], ...LEVELS.map((name) => [name, name])].map(
                ([value, label]) => (
                  <label
                    key={label}
                    className="flex min-h-9 cursor-pointer items-center gap-3 text-[15px] text-ink2"
                  >
                    <input
                      type="radio"
                      name="level"
                      value={value}
                      checked={level === value}
                      onChange={() => updateParams({ level: value, page: 1 })}
                      className="h-[18px] w-[18px] accent-[var(--gold)]"
                    />
                    <span
                      className={level === value ? "font-medium text-ink" : ""}
                    >
                      {label}
                    </span>
                  </label>
                ),
              )}
            </fieldset>
          </aside>

          <div className="flex min-w-0 flex-col">
            <div className="flex flex-wrap items-center justify-between gap-3 pb-5">
              <p className="small" aria-live="polite">
                {summary}
              </p>
              <div className="flex items-center gap-2">
                <label htmlFor="course-sort" className="small">
                  Sort by
                </label>
                <select
                  id="course-sort"
                  value={ordering}
                  onChange={(event) =>
                    updateParams({ ordering: event.target.value, page: 1 })
                  }
                  className="input !min-h-11 !w-auto"
                >
                  {SORTS.map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {loading ? (
              <div className="flex flex-col gap-6 border-t border-line pt-7">
                {Array.from({ length: 4 }).map((_, index) => (
                  <Skeleton key={index} className="h-[124px] w-full" />
                ))}
              </div>
            ) : error ? (
              <ErrorState error={error} onRetry={refetch} />
            ) : courses.length === 0 ? (
              <div className="border-t border-line">
                <EmptyState
                  title="No courses match your search"
                  description={
                    search
                      ? `Nothing matched “${search}”. Try a different term or clear the filters.`
                      : "No published courses are available yet."
                  }
                  action={
                    filtered && (
                      <button
                        type="button"
                        className="btn btn-line"
                        onClick={clearAll}
                      >
                        Clear filters
                      </button>
                    )
                  }
                />
              </div>
            ) : (
              <>
                <div className="rows flex flex-col border-t border-line">
                  {courses.map((course) => (
                    <CourseCard key={course.id} course={course} />
                  ))}
                </div>

                {totalPages > 1 && (
                  <nav
                    className="flex items-center justify-center gap-3 pt-10"
                    aria-label="Pagination"
                  >
                    <button
                      type="button"
                      className="btn btn-line"
                      disabled={page <= 1}
                      onClick={() => updateParams({ page: page - 1 })}
                    >
                      <Icon name="caretLeft" />
                      Previous
                    </button>
                    <span className="small num px-2">
                      Page {page} of {totalPages}
                    </span>
                    <button
                      type="button"
                      className="btn btn-line"
                      disabled={page >= totalPages}
                      onClick={() => updateParams({ page: page + 1 })}
                    >
                      Next
                      <Icon name="caretRight" />
                    </button>
                  </nav>
                )}
              </>
            )}
          </div>
        </div>
      </section>
    </>
  );
}
