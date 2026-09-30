import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import CourseCard from "../../components/CourseCard";
import { PageHeader } from "../../components/Layout";
import {
  Button,
  EmptyState,
  ErrorState,
  Panel,
  Skeleton,
  TextField,
} from "../../components/ui";
import useAsync from "../../hooks/useAsync";
import courseService from "../../services/courseService";

/**
 * Course catalogue.
 *
 * Filtering/pagination state lives in the URL (`?page=&search=`), not in component
 * state. That makes results shareable and bookmarkable, and it means the back
 * button behaves the way students expect.
 *
 * Searching is debounced and only *submitted* on Enter or after a pause, so a page
 * of results is not re-requested on every keystroke.
 */
const PAGE_SIZE = 9;

export default function Courses() {
  const [searchParams, setSearchParams] = useSearchParams();

  const page = Number(searchParams.get("page") || 1);
  const search = searchParams.get("search") || "";
  const level = searchParams.get("level") || "";

  const [searchInput, setSearchInput] = useState(search);
  const [showFilters, setShowFilters] = useState(Boolean(level));

  const params = useMemo(
    () => ({
      page,
      page_size: PAGE_SIZE,
      ...(search ? { search } : {}),
      ...(level ? { level } : {}),
    }),
    [page, search, level],
  );

  const { data, loading, error, refetch } = useAsync(
    () => courseService.list(params),
    [params.page, params.search, params.level],
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

  const courses = data?.results || [];
  const totalPages = data?.num_pages || 1;
  const totalCount = data?.count || 0;

  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-8 sm:py-10">
      <PageHeader
        title="Course catalogue"
        description="Browse published courses. Contents of a locked course are visible, but lessons stay unavailable until you subscribe."
        breadcrumbs={[{ label: "Home", to: "/" }, { label: "Courses" }]}
        actions={
          <Button
            variant="ghost"
            onClick={() => setShowFilters((value) => !value)}
          >
            {showFilters ? "Hide filters" : "Filters"}
          </Button>
        }
      />

      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end">
        <TextField
          id="course-search"
          label="Search courses"
          type="search"
          value={searchInput}
          onChange={(event) => setSearchInput(event.target.value)}
          placeholder="Constitutional law, criminal procedure…"
          className="flex-1"
          hint="Results update as you type."
        />

        {showFilters && (
          <div className="sm:w-56">
            <label htmlFor="level-filter" className="label">
              Level
            </label>
            <select
              id="level-filter"
              className="input"
              value={level}
              onChange={(event) =>
                updateParams({ level: event.target.value, page: 1 })
              }
            >
              <option value="">All levels</option>
              <option value="Beginner">Beginner</option>
              <option value="Intermediate">Intermediate</option>
              <option value="Advanced">Advanced</option>
            </select>
          </div>
        )}
      </div>

      {!loading && !error && (
        <p className="mb-4 text-sm text-white/50" aria-live="polite">
          {totalCount} course{totalCount === 1 ? "" : "s"} found
          {search ? ` for “${search}”` : ""}
        </p>
      )}

      {loading ? (
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <Skeleton key={index} className="h-80 w-full" />
          ))}
        </div>
      ) : error ? (
        <ErrorState error={error} onRetry={refetch} />
      ) : courses.length === 0 ? (
        <Panel>
          <EmptyState
            icon="search"
            title="No courses match your search"
            description={
              search
                ? `Nothing matched “${search}”. Try a different term or clear the filters.`
                : "No published courses are available yet."
            }
            action={
              (search || level) && (
                <Button
                  variant="ghost"
                  onClick={() => {
                    setSearchInput("");
                    setSearchParams({});
                  }}
                >
                  Clear filters
                </Button>
              )
            }
          />
        </Panel>
      ) : (
        <>
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {courses.map((course) => (
              <CourseCard key={course.id} course={course} />
            ))}
          </div>

          {totalPages > 1 && (
            <nav
              className="mt-10 flex items-center justify-center gap-2"
              aria-label="Pagination"
            >
              <Button
                variant="ghost"
                disabled={page <= 1}
                onClick={() => updateParams({ page: page - 1 })}
              >
                Previous
              </Button>
              <span className="px-3 text-sm text-white/60">
                Page {page} of {totalPages}
              </span>
              <Button
                variant="ghost"
                disabled={page >= totalPages}
                onClick={() => updateParams({ page: page + 1 })}
              >
                Next
              </Button>
            </nav>
          )}
        </>
      )}
    </div>
  );
}
