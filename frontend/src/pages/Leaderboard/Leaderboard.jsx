import { useCallback, useEffect, useState } from "react";

import Icon from "../../components/Icon";
import { EmptyState, ErrorState, Skeleton } from "../../components/ui";
import { useAuth } from "../../context/AuthContext";
import useAsync from "../../hooks/useAsync";
import { useSearchParams } from "react-router-dom";
import { leaderboardService } from "../../services/quizService";
import { formatRelative, initials } from "../../utils/format";

/**
 * Leaderboard.
 *
 * Ranking is computed in SQL on the backend (indexed, paginated), and this page
 * makes exactly one request per sort/page change. The "me" card comes from the same
 * response, so there is no second call to work out the student's own position.
 *
 * Sort choice is stored in the URL so a shared link opens the same view.
 */

const SORTS = [
  { value: "total_score", label: "Overall" },
  { value: "quiz_score", label: "Quiz score" },
  { value: "lessons", label: "Lessons completed" },
  { value: "courses", label: "Courses completed" },
];

export default function Leaderboard() {
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();

  const page = Number(searchParams.get("page") || 1);
  const ordering = searchParams.get("ordering") || "total_score";

  const { data, loading, error, refetch } = useAsync(
    () => leaderboardService.list({ page, ordering }),
    [page, ordering],
  );

  const [me, setMe] = useState(null);
  useEffect(() => {
    // `me` is delivered inside the list response; mirror it into local state so it
    // survives re-renders without a second request.
    if (data?.me) setMe(data.me);
  }, [data]);

  const changeSort = useCallback(
    (value) => {
      setSearchParams((current) => {
        const next = new URLSearchParams(current);
        next.set("ordering", value);
        next.delete("page");
        return next;
      });
    },
    [setSearchParams],
  );

  const setPage = useCallback(
    (value) => {
      setSearchParams((current) => {
        const next = new URLSearchParams(current);
        if (value <= 1) next.delete("page");
        else next.set("page", String(value));
        return next;
      });
      window.scrollTo({ top: 0, behavior: "smooth" });
    },
    [setSearchParams],
  );

  const entries = data?.results || [];
  const totalPages = data?.num_pages || 1;
  const podium = page === 1 && entries.length >= 3 ? entries.slice(0, 3) : [];
  const rest = podium.length ? entries.slice(3) : entries;
  const sortLabel = SORTS.find((sort) => sort.value === ordering)?.label;

  return (
    <div className="wrap pb-24 pt-12 lg:pt-16">
      <div className="flex flex-col gap-3 pb-10">
        <h1 className="d2">Leaderboard</h1>
        <p className="body max-w-[600px]">
          Ranked by quiz score plus completed lessons. Only aggregate scores are
          shown, never contact details.
        </p>
      </div>

      {/* --------------------------------------------------------- My position */}
      {me && (
        <section
          aria-label="Your standing"
          className="mb-10 flex flex-col gap-6 rounded-[14px] bg-gold-tint p-6 md:flex-row md:items-center md:justify-between"
        >
          <div className="flex items-center gap-5">
            <span className="min-w-[64px] font-serif text-[48px] leading-none text-[#0B1220] num">
              {me.rank ? `#${me.rank}` : "–"}
            </span>
            <div className="flex flex-col">
              <span className="font-medium text-[#0B1220]">Your standing</span>
              <span className="small !text-[#4A3A00]">
                {me.rank
                  ? `Top ${me.percentile !== null ? Math.max(1, Math.round(100 - me.percentile)) : 100}% of students`
                  : "Complete a lesson or quiz to enter the ranking"}
              </span>
            </div>
          </div>

          <dl className="m-0 grid grid-cols-4 gap-6">
            <Stat label="Total" value={me.total_score} />
            <Stat label="Quiz" value={me.quiz_score} />
            <Stat label="Lessons" value={me.lessons_completed} />
            <Stat label="Courses" value={me.courses_completed} />
          </dl>
        </section>
      )}

      {/* -------------------------------------------------------------- Sorting */}
      <div
        className="flex flex-wrap gap-2 pb-8"
        role="group"
        aria-label="Sort leaderboard"
      >
        {SORTS.map((sort) => (
          <button
            key={sort.value}
            type="button"
            onClick={() => changeSort(sort.value)}
            className={`btn ${ordering === sort.value ? "btn-gold" : "btn-line"}`}
            aria-pressed={ordering === sort.value}
          >
            {sort.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex flex-col gap-3">
          {Array.from({ length: 8 }).map((_, index) => (
            <Skeleton key={index} className="h-14 w-full" />
          ))}
        </div>
      ) : error ? (
        <ErrorState error={error} onRetry={refetch} />
      ) : entries.length === 0 ? (
        <div className="border-y border-line">
          <EmptyState
            title="No rankings yet"
            description="Scores appear once students complete lessons and quizzes."
          />
        </div>
      ) : (
        <>
          {podium.length === 3 && (
            <ol className="m-0 mb-10 grid list-none gap-5 p-0 md:grid-cols-3">
              {podium.map((entry, index) => (
                <PodiumCard
                  key={entry.user_id}
                  entry={entry}
                  place={index + 1}
                  isMe={entry.user_id === user?.id}
                />
              ))}
            </ol>
          )}

          {rest.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[420px] border-collapse text-[15px]">
                <caption className="sr-only">
                  Student leaderboard ranked by {sortLabel}
                </caption>
                <thead>
                  <tr className="border-b border-line-strong text-left text-[13px] text-ink3">
                    <th scope="col" className="w-16 pb-3 font-medium">
                      Rank
                    </th>
                    <th scope="col" className="pb-3 font-medium">
                      Student
                    </th>
                    <th
                      scope="col"
                      className="hidden pb-3 text-right font-medium sm:table-cell"
                    >
                      Quiz
                    </th>
                    <th
                      scope="col"
                      className="hidden pb-3 text-right font-medium sm:table-cell"
                    >
                      Lessons
                    </th>
                    <th scope="col" className="pb-3 text-right font-medium">
                      Score
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {rest.map((entry) => {
                    const isMe = entry.user_id === user?.id;
                    return (
                      <tr
                        key={entry.user_id}
                        className={`border-b border-line ${isMe ? "bg-gold-tint" : ""}`}
                      >
                        <td className="mono py-4 pl-1 text-ink2">
                          {entry.rank || "–"}
                        </td>
                        <td className="py-3 pr-4">
                          <span className="flex items-center gap-3">
                            <span className="avatar !h-9 !w-9 !text-xs">
                              {initials(entry.name)}
                            </span>
                            <span className="min-w-0">
                              <span className="block truncate">
                                {entry.name}
                                {isMe && (
                                  <span className="ml-2 text-[13px] font-medium text-gold-ink">
                                    you
                                  </span>
                                )}
                              </span>
                              {entry.last_activity_at && (
                                <span className="cap">
                                  Active {formatRelative(entry.last_activity_at)}
                                </span>
                              )}
                            </span>
                          </span>
                        </td>
                        <td className="mono hidden text-right text-ink3 sm:table-cell">
                          {entry.quiz_score}
                        </td>
                        <td className="mono hidden text-right text-ink3 sm:table-cell">
                          {entry.lessons_completed}
                        </td>
                        <td className="mono pr-1 text-right font-medium">
                          {entry.total_score}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {totalPages > 1 && (
            <nav
              className="flex items-center justify-center gap-3 pt-10"
              aria-label="Pagination"
            >
              <button
                type="button"
                className="btn btn-line"
                disabled={page <= 1}
                onClick={() => setPage(page - 1)}
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
                onClick={() => setPage(page + 1)}
              >
                Next
                <Icon name="caretRight" />
              </button>
            </nav>
          )}
        </>
      )}
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div className="flex flex-col">
      <dd className="m-0 font-serif text-[28px] leading-[1.1] text-[#0B1220] num">
        {value}
      </dd>
      <dt className="small !text-[#4A3A00]">{label}</dt>
    </div>
  );
}

function PodiumCard({ entry, place, isMe }) {
  const first = place === 1;
  return (
    <li
      className={`flex flex-col gap-4 rounded-[14px] p-6 ${first ? "navy-surface" : "card"} ${isMe ? "ring-2 ring-gold" : ""}`}
    >
      <div className="flex items-center justify-between">
        <span
          className={`mono cap ${first ? "!text-[#B4BED6]" : ""}`}
        >{`Rank ${entry.rank || place}`}</span>
        {isMe && <span className="tag tag-gold">You</span>}
      </div>
      <span className="font-serif text-[56px] leading-none num">{place}</span>
      <div className="flex flex-col">
        <span className="truncate text-[17px] font-medium">{entry.name}</span>
        <span className={`mono ${first ? "text-[#B4BED6]" : "small"}`}>
          {entry.total_score} points
        </span>
      </div>
    </li>
  );
}
