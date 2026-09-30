import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { PageHeader } from "../../components/Layout";
import {
  Avatar,
  Badge,
  Button,
  EmptyState,
  ErrorState,
  Panel,
  Skeleton,
} from "../../components/ui";
import { useAuth } from "../../context/AuthContext";
import useAsync from "../../hooks/useAsync";
import { leaderboardService } from "../../services/quizService";
import { formatRelative } from "../../utils/format";

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
  const podium = page === 1 ? entries.slice(0, 3) : [];
  const rest = page === 1 ? entries.slice(3) : entries;

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-8 sm:py-10">
      <PageHeader
        title="Leaderboard"
        description="Ranked by quiz score plus completed lessons. Only aggregate scores are shown — never contact details."
        breadcrumbs={[{ label: "Home", to: "/" }, { label: "Leaderboard" }]}
      />

      {/* --------------------------------------------------------- My position */}
      {me && (
        <Panel className="mb-6 p-5">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <div className="flex h-14 w-14 items-center justify-center rounded-full bg-gold-500/15 font-display text-xl text-gold-300">
                {me.rank ? `#${me.rank}` : "\u2014"}
              </div>
              <div>
                <p className="font-display text-lg text-parchment">
                  Your standing
                </p>
                <p className="text-sm text-white/55">
                  {me.rank
                    ? `Rank ${me.rank}${me.percentile !== null ? ` · top ${Math.max(1, Math.round(100 - me.percentile))}%` : ""}`
                    : "Complete a lesson or quiz to enter the ranking"}
                </p>
              </div>
            </div>

            <dl className="flex gap-6 text-sm">
              <Stat label="Total" value={me.total_score} />
              <Stat label="Quiz" value={me.quiz_score} />
              <Stat label="Lessons" value={me.lessons_completed} />
              <Stat label="Courses" value={me.courses_completed} />
            </dl>
          </div>
        </Panel>
      )}

      {/* -------------------------------------------------------------- Sorting */}
      <div
        className="mb-5 flex flex-wrap gap-2"
        role="group"
        aria-label="Sort leaderboard"
      >
        {SORTS.map((sort) => (
          <Button
            key={sort.value}
            variant={ordering === sort.value ? "primary" : "ghost"}
            onClick={() => changeSort(sort.value)}
            className="!min-h-0 !py-2 text-sm"
            aria-pressed={ordering === sort.value}
          >
            {sort.label}
          </Button>
        ))}
      </div>

      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 8 }).map((_, index) => (
            <Skeleton key={index} className="h-16 w-full" />
          ))}
        </div>
      ) : error ? (
        <ErrorState error={error} onRetry={refetch} />
      ) : entries.length === 0 ? (
        <Panel>
          <EmptyState
            icon="chart"
            title="No rankings yet"
            description="Scores appear once students complete lessons and quizzes."
          />
        </Panel>
      ) : (
        <>
          {/* Podium for the top three on page 1 */}
          {podium.length === 3 && (
            <div className="mb-6 grid gap-4 sm:grid-cols-3">
              {podium.map((entry, index) => (
                <PodiumCard
                  key={entry.user_id}
                  entry={entry}
                  place={index + 1}
                  isMe={entry.user_id === user?.id}
                />
              ))}
            </div>
          )}

          {/* Table */}
          <Panel className="overflow-hidden">
            <table className="w-full text-left text-sm">
              <caption className="sr-only">
                Student leaderboard ranked by{" "}
                {SORTS.find((sort) => sort.value === ordering)?.label}
              </caption>
              <thead className="bg-white/[0.03] text-xs uppercase tracking-wider text-white/50">
                <tr>
                  <th scope="col" className="px-4 py-3">
                    Rank
                  </th>
                  <th scope="col" className="px-4 py-3">
                    Student
                  </th>
                  <th scope="col" className="hidden px-4 py-3 sm:table-cell">
                    Quiz
                  </th>
                  <th scope="col" className="hidden px-4 py-3 sm:table-cell">
                    Lessons
                  </th>
                  <th scope="col" className="px-4 py-3 text-right">
                    Score
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {rest.map((entry) => {
                  const isMe = entry.user_id === user?.id;
                  return (
                    <tr
                      key={entry.user_id}
                      className={isMe ? "bg-gold-500/10" : undefined}
                    >
                      <td className="px-4 py-3 font-display text-white/70">
                        {entry.rank || "\u2014"}
                      </td>
                      <td className="px-4 py-3">
                        <span className="flex items-center gap-3">
                          <Avatar
                            user={{
                              name: entry.name,
                              avatar: entry.avatar_url,
                            }}
                            size={30}
                          />
                          <span className="min-w-0">
                            <span className="block truncate text-parchment">
                              {entry.name}
                              {isMe && (
                                <span className="ml-2 text-xs text-gold-300">
                                  (you)
                                </span>
                              )}
                            </span>
                            {entry.last_activity_at && (
                              <span className="text-xs text-white/40">
                                Active {formatRelative(entry.last_activity_at)}
                              </span>
                            )}
                          </span>
                        </span>
                      </td>
                      <td className="hidden px-4 py-3 text-white/65 sm:table-cell">
                        {entry.quiz_score}
                      </td>
                      <td className="hidden px-4 py-3 text-white/65 sm:table-cell">
                        {entry.lessons_completed}
                      </td>
                      <td className="px-4 py-3 text-right font-semibold text-gold-300">
                        {entry.total_score}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </Panel>

          {totalPages > 1 && (
            <nav
              className="mt-6 flex items-center justify-center gap-2"
              aria-label="Pagination"
            >
              <Button
                variant="ghost"
                disabled={page <= 1}
                onClick={() => setPage(page - 1)}
              >
                Previous
              </Button>
              <span className="px-3 text-sm text-white/60">
                Page {page} of {totalPages}
              </span>
              <Button
                variant="ghost"
                disabled={page >= totalPages}
                onClick={() => setPage(page + 1)}
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

function Stat({ label, value }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wider text-white/40">
        {label}
      </dt>
      <dd className="font-semibold text-parchment">{value}</dd>
    </div>
  );
}

function PodiumCard({ entry, place, isMe }) {
  const medals = { 1: "\u{1F947}", 2: "\u{1F948}", 3: "\u{1F949}" };
  return (
    <Panel className={`p-5 text-center ${isMe ? "border-gold-500" : ""}`}>
      <div className="text-3xl" aria-hidden="true">
        {medals[place]}
      </div>
      <p className="mt-2 truncate font-display text-lg text-parchment">
        {entry.name}
      </p>
      <p className="text-xs text-white/45">Rank {entry.rank}</p>
      <p className="mt-3 font-display text-2xl text-gold-300">
        {entry.total_score}
      </p>
      <p className="text-xs text-white/45">points</p>
      {isMe && (
        <div className="mt-2">
          <Badge tone="gold">That&apos;s you</Badge>
        </div>
      )}
    </Panel>
  );
}
