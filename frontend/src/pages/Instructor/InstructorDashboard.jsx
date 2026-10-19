import { Link } from "react-router-dom";

import { PageHeader } from "../../components/Layout";
import {
  Badge,
  EmptyState,
  ErrorState,
  Panel,
  ProgressBar,
  Skeleton,
} from "../../components/ui";
import useAsync from "../../hooks/useAsync";
import courseService from "../../services/courseService";
import { formatDateTime, formatRelative } from "../../utils/format";

/**
 * Teaching overview for instructors (and admins, who see every course).
 *
 * All numbers come from one endpoint, `/courses/instructor/dashboard/`, which scopes
 * the data to the caller's own courses on the server. "Students" are learners with
 * recorded activity in a course, since access comes from subscriptions, not enrolment.
 */
const pct = (value) => (value == null ? "—" : `${value}%`);

export default function InstructorDashboard() {
  const { data, error, loading, refetch } = useAsync(
    () => courseService.instructorDashboard(),
    [],
  );

  const totals = data?.totals;
  const cards = [
    { label: "Courses", value: totals?.courses },
    { label: "Active students", value: totals?.students },
    { label: "Quiz attempts", value: totals?.quiz_attempts },
    { label: "Average quiz score", value: totals && pct(totals.avg_quiz_percent) },
    { label: "Quiz pass rate", value: totals && pct(totals.pass_rate_percent) },
  ];

  return (
    <div className="wrap pb-24 pt-12 lg:pt-14">
      <PageHeader
        title="Teaching"
        description="How your students are doing across your courses."
        breadcrumbs={[{ label: "Home", to: "/" }, { label: "Teaching" }]}
        actions={
          <Link to="/instructor/manage" className="btn btn-ghost">
            Manage courses
          </Link>
        }
      />

      {error ? (
        <ErrorState error={error} onRetry={refetch} />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            {cards.map((card) => (
              <Panel key={card.label} className="p-4">
                <p className="small">{card.label}</p>
                {loading ? (
                  <Skeleton className="mt-2 h-8 w-16" />
                ) : (
                  <p className="mt-1 font-serif text-[32px] leading-none num">
                    {card.value ?? 0}
                  </p>
                )}
              </Panel>
            ))}
          </div>

          <div className="mt-6 grid gap-6 lg:grid-cols-3">
            <Panel className="p-5 lg:col-span-2">
              <h2 className="h4">Your courses</h2>
              <div className="rule my-4" />
              {loading ? (
                <Skeleton className="h-32 w-full" />
              ) : data.courses.length === 0 ? (
                <EmptyState
                  title="No courses yet"
                  description="An administrator assigns courses to instructors. Once one is yours it appears here."
                />
              ) : (
                <ul className="space-y-6">
                  {data.courses.map((course) => (
                    <li key={course.id}>
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <Link
                          to={`/courses/${course.slug}`}
                          className="font-medium text-ink hover:underline"
                        >
                          {course.title}
                        </Link>
                        <Badge
                          tone={course.status === "published" ? "success" : "muted"}
                        >
                          {course.status}
                        </Badge>
                      </div>
                      <p className="small mt-1">
                        {course.student_count} students · {course.lesson_count}{" "}
                        lessons · {course.quiz_attempts} quiz attempts · avg{" "}
                        {pct(course.avg_quiz_percent)} · pass{" "}
                        {pct(course.pass_rate_percent)}
                      </p>
                      <ProgressBar
                        className="mt-2"
                        value={course.completion_percent}
                        label="Lessons completed by students"
                      />
                      {course.lessons.length > 0 && (
                        <details className="mt-2">
                          <summary className="small cursor-pointer">
                            Lesson breakdown
                          </summary>
                          <table className="mt-2 w-full text-left text-sm">
                            <thead>
                              <tr className="small">
                                <th className="py-1">Lesson</th>
                                <th className="py-1 text-right">Watching</th>
                                <th className="py-1 text-right">Completed</th>
                              </tr>
                            </thead>
                            <tbody>
                              {course.lessons.map((lesson) => (
                                <tr key={lesson.id} className="border-t border-line">
                                  <td className="py-1.5">{lesson.title}</td>
                                  <td className="py-1.5 text-right num">
                                    {lesson.watchers}
                                  </td>
                                  <td className="py-1.5 text-right num">
                                    {lesson.completed}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </details>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </Panel>

            <div className="space-y-6">
              <Panel className="p-5">
                <h2 className="h4">Upcoming live classes</h2>
                <div className="rule my-4" />
                {loading ? (
                  <Skeleton className="h-20 w-full" />
                ) : data.upcoming_live_classes.length === 0 ? (
                  <p className="small">Nothing scheduled.</p>
                ) : (
                  <ul className="space-y-3">
                    {data.upcoming_live_classes.map((lc) => (
                      <li key={lc.id}>
                        <p className="text-sm font-medium">
                          {lc.title}{" "}
                          {!lc.is_published && <Badge tone="muted">Draft</Badge>}
                        </p>
                        <p className="small">
                          {formatDateTime(lc.scheduled_start)} ·{" "}
                          {lc.duration_minutes} min · {lc.course_title}
                        </p>
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>

              <Panel className="p-5">
                <h2 className="h4">Recent quiz results</h2>
                <div className="rule my-4" />
                {loading ? (
                  <Skeleton className="h-20 w-full" />
                ) : data.recent_attempts.length === 0 ? (
                  <p className="small">No attempts yet.</p>
                ) : (
                  <ul className="space-y-3">
                    {data.recent_attempts.map((a) => (
                      <li key={a.id} className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-medium">{a.student}</p>
                          <p className="small">
                            {a.quiz} · {formatRelative(a.submitted_at)}
                          </p>
                        </div>
                        <Badge tone={a.passed ? "success" : "danger"}>
                          {Math.round(a.percentage)}%
                        </Badge>
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
