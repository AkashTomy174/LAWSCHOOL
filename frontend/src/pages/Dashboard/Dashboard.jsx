import { Link } from "react-router-dom";

import Icon from "../../components/Icon";
import { EmptyState, ErrorState, Skeleton } from "../../components/ui";
import { useAuth } from "../../context/AuthContext";
import useAsync from "../../hooks/useAsync";
import courseService from "../../services/courseService";
import { subscriptionService } from "../../services/paymentService";
import { leaderboardService, quizService } from "../../services/quizService";
import videoService from "../../services/videoService";
import {
  formatDaysRemaining,
  formatDuration,
  formatRelative,
} from "../../utils/format";

/**
 * Student dashboard.
 *
 * Performance note: this page makes a *small, fixed* number of paginated requests
 * and joins them client-side, and each section renders independently so one slow
 * endpoint does not hold up the rest:
 *
 *   1. subscription  2. courses (carry `is_accessible` + progress)
 *   3. recent progress  4. quiz attempts  5. leaderboard rank
 */
function greeting(date = new Date()) {
  const hour = date.getHours();
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

export default function Dashboard() {
  const { user } = useAuth();

  const subscription = useAsync(() => subscriptionService.mine(), []);
  const courses = useAsync(() => courseService.list({ page_size: 20 }), []);
  const progress = useAsync(
    () => videoService.myProgress({ page_size: 5 }),
    [],
  );
  const attempts = useAsync(() => quizService.myAttempts({ page_size: 5 }), []);
  const rank = useAsync(() => leaderboardService.me(), []);

  const active = subscription.data?.active;
  const allCourses = courses.data?.results || [];
  const enrolled = allCourses.filter((course) => course.is_accessible);
  const locked = allCourses.filter((course) => !course.is_accessible);
  const recentProgress = progress.data?.results || [];
  const recentAttempts = attempts.data?.results || [];
  const resumeRow =
    recentProgress.find((row) => !row.completed) || recentProgress[0] || null;

  const averageScore = recentAttempts.length
    ? Math.round(
        recentAttempts.reduce(
          (sum, attempt) => sum + Number(attempt.percentage || 0),
          0,
        ) / recentAttempts.length,
      )
    : null;

  const firstName = user?.name?.split(" ")[0];

  return (
    <div className="wrap pb-24 pt-12 lg:pt-14">
      <div className="flex flex-col justify-between gap-6 pb-10 md:flex-row md:items-end">
        <div className="flex flex-col gap-2">
          <h1 className="d2 !text-[40px] md:!text-[52px]">
            {greeting()}
            {firstName ? `, ${firstName}` : ""}.
          </h1>
          <p className="body">
            Your courses, recent results and standing, in one place.
          </p>
        </div>

        {subscription.loading ? (
          <Skeleton className="h-11 w-56" />
        ) : active ? (
          <div className="flex items-center gap-3 rounded-lg bg-gold-tint px-4 py-2.5 text-gold-ink">
            <span className="font-medium">{active.plan.name}</span>
            <span aria-hidden="true" className="opacity-50">
              |
            </span>
            <span className="num">
              {formatDaysRemaining(active.days_remaining)}
            </span>
          </div>
        ) : (
          <Link to="/subscription" className="btn btn-gold">
            {subscription.data?.history?.length ? "Renew your plan" : "View plans"}
          </Link>
        )}
      </div>

      {!subscription.loading && !active && (
        <p className="mb-10 rounded-[10px] bg-gold-tint px-4 py-3 text-[15px] text-[#4A3A00]">
          {subscription.data?.history?.length
            ? "Your previous plan has ended, so subscription courses are locked. "
            : "Choose a plan to unlock every subscription course and quiz. "}
          <Link
            to="/subscription"
            className="font-medium text-[#0B1220] underline underline-offset-4"
          >
            See plans
          </Link>
        </p>
      )}

      <div className="grid gap-14 lg:grid-cols-[minmax(0,8fr)_minmax(0,4fr)] lg:gap-0">
        {/* ------------------------------------------------------ Main column */}
        <div className="flex min-w-0 flex-col gap-12 lg:pr-14">
          <ContinueCard
            loading={progress.loading}
            row={resumeRow}
            fallbackCourse={enrolled[0]}
          />

          <section aria-labelledby="courses-heading" className="flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <h2 id="courses-heading" className="h3">
                Your courses
              </h2>
              <Link to="/courses" className="font-medium text-gold-ink underline-offset-4 hover:underline">
                View all
              </Link>
            </div>

            {courses.loading ? (
              <Skeleton className="h-48 w-full" />
            ) : courses.error ? (
              <ErrorState error={courses.error} onRetry={courses.refetch} />
            ) : enrolled.length === 0 ? (
              <div className="border-y border-line">
                <EmptyState
                  title="No courses unlocked yet"
                  description="Subscribe to a plan to start learning, or try a free preview lesson."
                  action={
                    <Link to="/courses" className="btn btn-gold">
                      Explore courses
                    </Link>
                  }
                />
              </div>
            ) : (
              <ul className="rows m-0 flex list-none flex-col border-t border-line-strong p-0">
                {enrolled.slice(0, 6).map((course) => (
                  <CourseProgressRow key={course.id} course={course} />
                ))}
              </ul>
            )}
          </section>

          <section aria-labelledby="quizzes-heading" className="flex flex-col gap-4">
            <h2 id="quizzes-heading" className="h3">
              Recent quizzes
            </h2>
            {attempts.loading ? (
              <Skeleton className="h-32 w-full" />
            ) : attempts.error ? (
              <ErrorState error={attempts.error} onRetry={attempts.refetch} />
            ) : recentAttempts.length === 0 ? (
              <p className="small border-y border-line py-6">
                No quiz attempts yet. Quizzes appear inside each course.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[480px] border-collapse text-[15px]">
                  <thead>
                    <tr className="border-b border-line-strong text-left text-[13px] text-ink3">
                      <th scope="col" className="pb-3 font-medium">
                        Quiz
                      </th>
                      <th scope="col" className="pb-3 font-medium">
                        Taken
                      </th>
                      <th scope="col" className="pb-3 text-right font-medium">
                        Score
                      </th>
                      <th scope="col" className="w-28 pb-3 text-right font-medium">
                        Result
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {recentAttempts.map((attempt) => (
                      <tr key={attempt.id} className="border-b border-line">
                        <td className="py-[18px] pr-4">
                          <Link
                            to={`/quiz/${attempt.quiz}/result?attempt=${attempt.id}`}
                            className="hover:underline"
                          >
                            {attempt.quiz_title}
                          </Link>
                        </td>
                        <td className="small pr-4">
                          {formatRelative(attempt.submitted_at)}
                        </td>
                        <td className="mono text-right">
                          {attempt.score} / {attempt.max_score}
                        </td>
                        <td className="text-right">
                          <span
                            className={`tag ${attempt.passed ? "tag-ok" : "tag-bad"}`}
                          >
                            {attempt.passed ? "Passed" : "Retake"}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>

        {/* ----------------------------------------------------------- Sidebar */}
        <aside
          aria-label="Your standing"
          className="flex min-w-0 flex-col gap-10 lg:border-l lg:border-line lg:pl-14"
        >
          <section className="flex flex-col gap-4">
            <h2 className="h4">Your results</h2>
            <dl className="m-0 grid grid-cols-3 gap-4">
              <Figure
                label="quizzes"
                value={attempts.loading ? null : (attempts.data?.count ?? 0)}
              />
              <Figure
                label="lessons done"
                value={rank.loading ? null : (rank.data?.lessons_completed ?? 0)}
              />
              <Figure
                label="avg score"
                value={
                  attempts.loading
                    ? null
                    : averageScore === null
                      ? "–"
                      : `${averageScore}%`
                }
              />
            </dl>
          </section>

          <hr className="rule" />

          <section className="flex flex-col gap-3" aria-label="Leaderboard">
            <div className="flex items-center justify-between">
              <h2 className="h4">Leaderboard</h2>
              <Link to="/leaderboard" className="small font-medium !text-gold-ink hover:underline">
                View ranking
              </Link>
            </div>
            {rank.loading ? (
              <Skeleton className="h-16 w-full" />
            ) : rank.error ? (
              <p className="small">Your ranking is unavailable right now.</p>
            ) : (
              <div className="flex items-center gap-4 rounded-lg bg-gold-tint px-4 py-3.5">
                <span className="font-serif text-[30px] leading-none text-[#0B1220] num">
                  {rank.data?.rank ? `#${rank.data.rank}` : "–"}
                </span>
                <div className="flex flex-1 flex-col">
                  <span className="font-medium text-[#0B1220]">You</span>
                  <span className="small !text-[#4A3A00]">
                    {rank.data?.rank
                      ? "Your current place"
                      : "Finish a quiz to be ranked"}
                  </span>
                </div>
                <span className="mono font-medium text-[#0B1220]">
                  {rank.data?.total_score ?? 0}
                </span>
              </div>
            )}
          </section>

          {locked.length > 0 && (
            <>
              <hr className="rule" />
              <section className="flex flex-col gap-3" aria-label="Locked courses">
                <h2 className="h4">Still locked</h2>
                <ul className="rows m-0 flex list-none flex-col p-0">
                  {locked.slice(0, 3).map((course) => (
                    <li key={course.id}>
                      <Link
                        to={`/courses/${course.slug}`}
                        className="flex min-h-12 items-center justify-between gap-3 py-3 text-[15px]"
                      >
                        <span className="min-w-0 truncate">{course.title}</span>
                        <Icon name="lock" className="i-sm text-ink3" label="Locked" />
                      </Link>
                    </li>
                  ))}
                </ul>
              </section>
            </>
          )}
        </aside>
      </div>
    </div>
  );
}

function Figure({ label, value }) {
  return (
    <div className="flex flex-col">
      {value === null ? (
        <Skeleton className="h-8 w-12" />
      ) : (
        <dd className="m-0 font-serif text-[30px] leading-[1.1] num">{value}</dd>
      )}
      <dt className="small">{label}</dt>
    </div>
  );
}

function ContinueCard({ loading, row, fallbackCourse }) {
  if (loading) return <Skeleton className="h-52 w-full" />;
  if (!row && !fallbackCourse) return null;

  const percent = row ? Math.round(Number(row.completion_percentage) || 0) : 0;

  return (
    <section
      aria-label="Continue learning"
      className="navy-surface flex flex-col overflow-hidden rounded-[14px] sm:flex-row"
    >
      <div className="flex h-36 flex-none items-center justify-center bg-navy2 sm:h-auto sm:w-[240px]">
        <span className="flex h-[60px] w-[60px] items-center justify-center rounded-full bg-[#C9A227] text-[#0B1220]">
          <Icon name="play" className="i-lg" />
        </span>
      </div>
      <div className="flex flex-1 flex-col gap-4 p-7 sm:p-8">
        <span className="cap !text-[#B4BED6]">Continue learning</span>
        {row ? (
          <>
            <h2 className="h3">
              {row.completed ? "Review your last lesson" : "Pick up your last lesson"}
            </h2>
            <div className="flex flex-col gap-2">
              <div
                className="h-1.5 overflow-hidden rounded-[3px] bg-white/[0.16]"
                role="progressbar"
                aria-label="Lesson progress"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={percent}
              >
                <i className="block h-full bg-[#C9A227]" style={{ width: `${percent}%` }} />
              </div>
              <span className="cap !text-[#B4BED6]">
                {percent}% watched, updated {formatRelative(row.updated_at)}
              </span>
            </div>
            <div className="flex flex-wrap gap-3 pt-1">
              <Link to={`/watch/${row.lesson_id}`} className="btn btn-gold">
                {row.completed
                  ? "Watch again"
                  : `Resume at ${formatDuration(row.last_position)}`}
              </Link>
              <Link to="/progress" className="btn btn-on-navy">
                All progress
              </Link>
            </div>
          </>
        ) : (
          <>
            <h2 className="h3">{fallbackCourse.title}</h2>
            <p className="text-[15px] text-[#B4BED6]">
              You have access. Start the first lesson whenever you are ready.
            </p>
            <div className="pt-1">
              <Link to={`/courses/${fallbackCourse.slug}`} className="btn btn-gold">
                Open course
              </Link>
            </div>
          </>
        )}
      </div>
    </section>
  );
}

function CourseProgressRow({ course }) {
  const percent = Math.round(Number(course.progress_percentage) || 0);
  const total = Number(course.lesson_count) || 0;
  const done = Math.min(total, Math.round((percent / 100) * total));

  return (
    <li>
      <Link
        to={`/courses/${course.slug}`}
        className="flex items-center gap-6 py-[22px]"
      >
        <span className="flex min-w-0 flex-1 flex-col gap-2">
          <span className="truncate text-[17px] font-medium">{course.title}</span>
          <span
            className="bar"
            role="progressbar"
            aria-label={`${course.title} progress`}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={percent}
          >
            <i style={{ width: `${percent}%` }} />
          </span>
        </span>
        <span className="flex w-28 flex-col items-end">
          <span className="mono font-medium">{percent}%</span>
          <span className="cap">
            {done} of {total} lessons
          </span>
        </span>
      </Link>
    </li>
  );
}
