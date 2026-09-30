import { Link } from "react-router-dom";

import CourseCard from "../../components/CourseCard";
import { PageHeader } from "../../components/Layout";
import {
  Badge,
  Button,
  Callout,
  EmptyState,
  ErrorState,
  Panel,
  ProgressBar,
  Skeleton,
} from "../../components/ui";
import { useAuth } from "../../context/AuthContext";
import useAsync from "../../hooks/useAsync";
import courseService from "../../services/courseService";
import { leaderboardService, quizService } from "../../services/quizService";
import { subscriptionService } from "../../services/paymentService";
import videoService from "../../services/videoService";
import {
  formatDaysRemaining,
  formatPercent,
  formatRelative,
} from "../../utils/format";

/**
 * Student dashboard.
 *
 * Performance note — this page intentionally makes a *small, fixed* number of
 * requests and does all the joining client-side:
 *
 *   1. courses (catalogue, carries `is_accessible` + progress)
 *   2. subscription
 *   3. recent progress
 *   4. quiz attempts
 *   5. leaderboard rank
 *
 * Every one of those is a paginated endpoint, so the payload stays bounded as the
 * catalogue grows. There is no "fetch everything" call, and the widgets render
 * independently so one slow endpoint does not hold up the whole page.
 */
export default function Dashboard() {
  const { user } = useAuth();

  const subscription = useAsync(() => subscriptionService.mine(), []);
  const courses = useAsync(() => courseService.list({ page_size: 6 }), []);
  const progress = useAsync(
    () => videoService.myProgress({ page_size: 5 }),
    [],
  );
  const attempts = useAsync(() => quizService.myAttempts({ page_size: 5 }), []);
  const rank = useAsync(() => leaderboardService.me(), []);

  const active = subscription.data?.active;
  const allCourses = courses.data?.results || [];
  const enrolled = allCourses.filter((course) => course.is_accessible);
  const recentProgress = progress.data?.results || [];
  const recentAttempts = attempts.data?.results || [];

  const averageScore = recentAttempts.length
    ? Math.round(
        recentAttempts.reduce(
          (sum, attempt) => sum + Number(attempt.percentage || 0),
          0,
        ) / recentAttempts.length,
      )
    : 0;

  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-8 sm:py-10">
      <PageHeader
        title={`Welcome back, ${user?.name?.split(" ")[0] || "student"}`}
        description="Your subscription, courses, recent activity and standing — all in one place."
        breadcrumbs={[{ label: "Home", to: "/" }, { label: "Dashboard" }]}
      />

      {/* ------------------------------------------------------------- Summary */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <SummaryCard
          label="Subscription"
          value={
            subscription.loading
              ? null
              : active
                ? active.plan.name
                : subscription.data?.history?.length
                  ? "Expired"
                  : "None"
          }
          tone={active ? "success" : "warning"}
          footnote={
            active
              ? formatDaysRemaining(active.days_remaining)
              : "Renew to unlock courses"
          }
          action={
            <Link
              to="/subscription"
              className="text-xs text-gold-300 hover:underline"
            >
              {active ? "Manage" : "View plans"}
            </Link>
          }
        />

        <SummaryCard
          label="Courses with access"
          value={courses.loading ? null : enrolled.length}
          tone="gold"
          footnote={
            allCourses.length > enrolled.length
              ? `${allCourses.length - enrolled.length} more need a subscription`
              : "All available courses unlocked"
          }
          action={
            <Link
              to="/courses"
              className="text-xs text-gold-300 hover:underline"
            >
              Browse
            </Link>
          }
        />

        <SummaryCard
          label="Average quiz score"
          value={attempts.loading ? null : `${averageScore}%`}
          tone={averageScore >= 60 ? "success" : "warning"}
          footnote={`${attempts.data?.count ?? 0} attempts recorded`}
          action={
            <Link
              to="/leaderboard"
              className="text-xs text-gold-300 hover:underline"
            >
              Leaderboard
            </Link>
          }
        />

        <SummaryCard
          label="Leaderboard rank"
          value={
            rank.loading
              ? null
              : rank.data?.rank
                ? `#${rank.data.rank}`
                : "Unranked"
          }
          tone="gold"
          footnote={`${rank.data?.total_score ?? 0} points earned`}
          action={
            <Link
              to="/leaderboard"
              className="text-xs text-gold-300 hover:underline"
            >
              View ranking
            </Link>
          }
        />
      </div>

      {!subscription.loading && !active && (
        <div className="mt-6">
          <Callout tone="warning" title="Your courses are locked">
            {subscription.data?.history?.length
              ? "Your previous subscription has ended. Renew to restore access to your courses."
              : "Choose a plan to unlock every course, quiz and leaderboard ranking."}{" "}
            <Link to="/subscription" className="text-gold-300 underline">
              See plans
            </Link>
          </Callout>
        </div>
      )}

      <div className="mt-8 grid gap-8 lg:grid-cols-[1.5fr_1fr] lg:items-start">
        {/* ------------------------------------------------------- My courses */}
        <section aria-labelledby="my-courses-heading">
          <div className="mb-4 flex items-end justify-between gap-3">
            <h2
              id="my-courses-heading"
              className="font-display text-xl text-parchment"
            >
              My courses
            </h2>
            <Link
              to="/courses"
              className="text-sm text-gold-300 hover:underline"
            >
              All courses
            </Link>
          </div>

          {courses.loading ? (
            <div className="grid gap-5 sm:grid-cols-2">
              <Skeleton className="h-72 w-full" />
              <Skeleton className="h-72 w-full" />
            </div>
          ) : courses.error ? (
            <ErrorState error={courses.error} onRetry={courses.refetch} />
          ) : enrolled.length === 0 ? (
            <Panel>
              <EmptyState
                icon="lock"
                title="No courses unlocked yet"
                description="Subscribe to a plan to start learning, or try a free preview lesson."
                action={
                  <Link to="/courses" className="btn btn-primary">
                    Explore courses
                  </Link>
                }
              />
            </Panel>
          ) : (
            <div className="grid gap-5 sm:grid-cols-2">
              {enrolled.slice(0, 4).map((course) => (
                <CourseCard key={course.id} course={course} />
              ))}
            </div>
          )}
        </section>

        {/* ---------------------------------------------------- Activity feed */}
        <div className="space-y-6">
          <Panel className="p-5">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="font-display text-base text-parchment">
                Recently watched
              </h2>
              <Link
                to="/progress"
                className="text-xs text-gold-300 hover:underline"
              >
                All progress
              </Link>
            </div>

            {progress.loading ? (
              <Skeleton className="h-24 w-full" />
            ) : recentProgress.length === 0 ? (
              <p className="py-4 text-sm text-white/50">
                No playback yet. Open a course and start your first lesson.
              </p>
            ) : (
              <ul className="space-y-3">
                {recentProgress.map((row) => (
                  <li key={row.id}>
                    <Link
                      to={`/watch/${row.lesson_id}`}
                      className="block rounded-lg px-2 py-2 transition-colors hover:bg-white/5"
                    >
                      <span className="flex items-center justify-between gap-2">
                        <span className="truncate text-sm text-parchment">
                          Resume lesson
                        </span>
                        {row.completed ? (
                          <Badge tone="success">Done</Badge>
                        ) : (
                          <span className="text-xs text-white/45">
                            {formatPercent(row.completion_percentage)}
                          </span>
                        )}
                      </span>
                      <ProgressBar
                        value={row.completion_percentage}
                        className="mt-2"
                      />
                      <span className="mt-1 block text-xs text-white/40">
                        Updated {formatRelative(row.updated_at)}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Panel>

          <Panel className="p-5">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="font-display text-base text-parchment">
                Recent quiz results
              </h2>
            </div>

            {attempts.loading ? (
              <Skeleton className="h-24 w-full" />
            ) : recentAttempts.length === 0 ? (
              <p className="py-4 text-sm text-white/50">
                No quiz attempts yet.
              </p>
            ) : (
              <ul className="space-y-2">
                {recentAttempts.map((attempt) => (
                  <li key={attempt.id}>
                    <Link
                      to={`/quiz/${attempt.quiz}/result?attempt=${attempt.id}`}
                      className="flex items-center justify-between gap-3 rounded-lg px-2 py-2 hover:bg-white/5"
                    >
                      <span className="min-w-0">
                        <span className="block truncate text-sm text-parchment">
                          {attempt.quiz_title}
                        </span>
                        <span className="text-xs text-white/40">
                          Attempt {attempt.attempt_number} ·{" "}
                          {formatRelative(attempt.submitted_at)}
                        </span>
                      </span>
                      <span className="flex shrink-0 items-center gap-2">
                        <span className="text-sm text-white/70">
                          {attempt.score}/{attempt.max_score}
                        </span>
                        <Badge tone={attempt.passed ? "success" : "danger"}>
                          {attempt.passed ? "Passed" : "Failed"}
                        </Badge>
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Panel>

          <Panel className="p-5">
            <h2 className="font-display text-base text-parchment">
              Recommended next
            </h2>
            <p className="mt-1 text-xs text-white/45">
              Locked courses you can unlock with a subscription.
            </p>
            <ul className="mt-3 space-y-2">
              {allCourses
                .filter((course) => !course.is_accessible)
                .slice(0, 3)
                .map((course) => (
                  <li key={course.id}>
                    <Link
                      to={`/courses/${course.slug}`}
                      className="flex items-center justify-between gap-2 rounded-lg px-2 py-2 hover:bg-white/5"
                    >
                      <span className="truncate text-sm text-white/75">
                        {course.title}
                      </span>
                      <Badge tone="muted">Locked</Badge>
                    </Link>
                  </li>
                ))}
              {allCourses.every((course) => course.is_accessible) && (
                <li className="px-2 py-2 text-sm text-white/50">
                  You have access to every available course.
                </li>
              )}
            </ul>
          </Panel>
        </div>
      </div>
    </div>
  );
}

function SummaryCard({ label, value, footnote, tone = "gold", action }) {
  const tones = {
    gold: "text-gold-300",
    success: "text-emerald-300",
    warning: "text-amber-300",
  };

  return (
    <Panel className="p-4">
      <p className="text-xs uppercase tracking-wider text-white/45">{label}</p>
      {value === null ? (
        <Skeleton className="mt-2 h-7 w-20" />
      ) : (
        <p
          className={`mt-1 font-display text-2xl ${tones[tone] || tones.gold}`}
        >
          {value}
        </p>
      )}
      <p className="mt-1 text-xs text-white/45">{footnote}</p>
      {action && <div className="mt-2">{action}</div>}
    </Panel>
  );
}
