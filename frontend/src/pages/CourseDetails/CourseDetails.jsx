import { Link, useParams } from "react-router-dom";

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
import { formatDurationLabel, formatMoney } from "../../utils/format";

/**
 * Course detail page.
 *
 * Important: the payload this page renders contains **no playback data**. Locked
 * lessons carry only `is_locked: true`; the video token is fetched separately by
 * the player, after the server has re-checked entitlement. Locked rows are shown
 * with an explicit "locked" affordance rather than being hidden, so the student can
 * see what a subscription unlocks.
 */
export default function CourseDetails() {
  const { slug } = useParams();
  const { isAuthenticated } = useAuth();

  const {
    data: course,
    loading,
    error,
    refetch,
  } = useAsync(() => courseService.detail(slug), [slug]);

  if (loading) {
    return (
      <div className="mx-auto w-full max-w-6xl px-4 py-10">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="mt-4 h-5 w-1/3" />
        <Skeleton className="mt-8 h-64 w-full" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="mx-auto w-full max-w-3xl px-4 py-16">
        <ErrorState error={error} onRetry={refetch} />
      </div>
    );
  }

  if (!course) return null;

  const accessible = Boolean(course.is_accessible);
  const sections = course.sections || [];
  const totalLessons = sections.reduce(
    (sum, section) => sum + section.lessons.length,
    0,
  );
  const firstAvailableLesson = sections
    .flatMap((section) => section.lessons)
    .find((lesson) => !lesson.is_locked);

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-8 sm:py-10">
      <PageHeader
        title={course.title}
        description={course.subtitle || course.summary}
        breadcrumbs={[
          { label: "Home", to: "/" },
          { label: "Courses", to: "/courses" },
          { label: course.title },
        ]}
      />

      <div className="grid gap-8 lg:grid-cols-[1.6fr_1fr] lg:items-start">
        {/* --------------------------------------------------------- Main column */}
        <div className="space-y-8">
          <Panel className="overflow-hidden">
            <div className="aspect-video w-full bg-navy-800">
              {course.thumbnail_url ? (
                <img
                  src={course.thumbnail_url}
                  alt={`${course.title} cover`}
                  className="h-full w-full object-cover"
                />
              ) : (
                <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-navy-800 to-ink-900">
                  <span
                    className="font-display text-5xl text-gold-500/40"
                    aria-hidden="true"
                  >
                    {"\u2696"}
                  </span>
                </div>
              )}
            </div>

            <div className="p-5">
              <div className="flex flex-wrap items-center gap-2">
                {course.unlock_rule === "free" ? (
                  <Badge tone="success">Free course</Badge>
                ) : accessible ? (
                  <Badge tone="success">You have access</Badge>
                ) : (
                  <Badge tone="muted">Subscription required</Badge>
                )}
                {course.level && <Badge tone="muted">{course.level}</Badge>}
                <Badge tone="muted">{course.language}</Badge>
              </div>

              {accessible && Number(course.progress_percentage) > 0 && (
                <ProgressBar
                  value={course.progress_percentage}
                  label="Course progress"
                  className="mt-5"
                />
              )}

              <div className="mt-5 grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
                <Stat
                  label="Lessons"
                  value={totalLessons || course.lesson_count}
                />
                <Stat
                  label="Video time"
                  value={formatDurationLabel(
                    (course.duration_minutes || 0) * 60,
                  )}
                />
                <Stat label="Quizzes" value={course.quiz_count ?? 0} />
                <Stat label="Sections" value={sections.length} />
              </div>
            </div>
          </Panel>

          <section aria-labelledby="about-heading">
            <h2
              id="about-heading"
              className="font-display text-xl text-parchment"
            >
              About this course
            </h2>
            <div className="gold-rule my-4" />
            <p className="whitespace-pre-line text-sm leading-relaxed text-white/70">
              {course.description || course.summary}
            </p>
          </section>

          <section aria-labelledby="curriculum-heading">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <h2
                id="curriculum-heading"
                className="font-display text-xl text-parchment"
              >
                Curriculum
              </h2>
              <p className="text-xs text-white/45">
                {totalLessons} lesson{totalLessons === 1 ? "" : "s"} across{" "}
                {sections.length} section
                {sections.length === 1 ? "" : "s"}
              </p>
            </div>
            <div className="gold-rule my-4" />

            {sections.length === 0 ? (
              <Panel>
                <EmptyState
                  title="Curriculum coming soon"
                  description="This course has no published sections yet."
                />
              </Panel>
            ) : (
              <ol className="space-y-4">
                {sections.map((section, index) => (
                  <li key={section.id}>
                    <Panel className="overflow-hidden">
                      <div className="flex items-center justify-between gap-3 border-b border-[var(--color-border-subtle)] px-4 py-3">
                        <h3 className="font-display text-base text-parchment">
                          <span
                            className="mr-2 text-gold-500"
                            aria-hidden="true"
                          >
                            {String(index + 1).padStart(2, "0")}
                          </span>
                          {section.title}
                        </h3>
                        <span className="text-xs text-white/45">
                          {section.lessons.length} lesson
                          {section.lessons.length === 1 ? "" : "s"}
                        </span>
                      </div>

                      <ul className="divide-y divide-white/5">
                        {section.lessons.map((lesson) => (
                          <LessonRow
                            key={lesson.id}
                            lesson={lesson}
                            courseSlug={course.slug}
                            isAuthenticated={isAuthenticated}
                          />
                        ))}
                        {section.lessons.length === 0 && (
                          <li className="px-4 py-3 text-sm text-white/45">
                            No lessons published in this section yet.
                          </li>
                        )}
                      </ul>
                    </Panel>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </div>

        {/* ----------------------------------------------------------- Sidebar */}
        <aside className="space-y-4 lg:sticky lg:top-20">
          <Panel className="p-5">
            <p className="text-xs uppercase tracking-wider text-white/45">
              Access
            </p>
            <p className="mt-1 font-display text-2xl text-gold-300">
              {course.unlock_rule === "free"
                ? "Free"
                : formatMoney(course.price)}
            </p>
            <p className="mt-1 text-xs text-white/50">
              {course.unlock_rule === "free"
                ? "Included with every account."
                : "Included in a subscription plan — not a one-off purchase."}
            </p>

            <div className="mt-5 space-y-2">
              {accessible ? (
                firstAvailableLesson ? (
                  <Link
                    to={`/watch/${firstAvailableLesson.id}`}
                    className="btn btn-primary w-full"
                  >
                    {Number(course.progress_percentage) > 0
                      ? "Continue learning"
                      : "Start course"}
                  </Link>
                ) : (
                  <Callout tone="info">
                    Lessons for this course are being prepared.
                  </Callout>
                )
              ) : isAuthenticated ? (
                <Link to="/subscription" className="btn btn-primary w-full">
                  View subscription plans
                </Link>
              ) : (
                <>
                  <Link to="/register" className="btn btn-primary w-full">
                    Create an account to start
                  </Link>
                  <Link to="/login" className="btn btn-ghost w-full">
                    Sign in
                  </Link>
                </>
              )}
            </div>

            {!accessible && course.unlock_rule !== "free" && (
              <div className="mt-4">
                <Callout tone="warning">
                  Locked lessons show their titles but cannot be played without
                  an active subscription.
                </Callout>
              </div>
            )}
          </Panel>

          {course.instructor?.name && (
            <Panel className="p-5">
              <p className="text-xs uppercase tracking-wider text-white/45">
                Instructor
              </p>
              <p className="mt-1 font-display text-lg text-parchment">
                {course.instructor.name}
              </p>
              {course.instructor.qualification && (
                <p className="mt-1 text-sm text-white/55">
                  {course.instructor.qualification}
                </p>
              )}
            </Panel>
          )}
        </aside>
      </div>
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wider text-white/40">{label}</p>
      <p className="mt-0.5 font-semibold text-parchment">{value}</p>
    </div>
  );
}

/**
 * One lesson row.
 *
 * Locked lessons render as non-interactive rows (a `<div>`, not a link) so there is
 * no clickable path to a page that would only 403.
 */
function LessonRow({ lesson, courseSlug, isAuthenticated }) {
  const playable = !lesson.is_locked;
  const target = playable ? `/watch/${lesson.id}` : null;

  const content = (
    <>
      <span
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs ${
          lesson.is_completed
            ? "bg-emerald-500/20 text-emerald-300"
            : playable
              ? "bg-gold-500/15 text-gold-300"
              : "bg-white/5 text-white/40"
        }`}
        aria-hidden="true"
      >
        {lesson.is_completed ? "\u2713" : playable ? "\u25B6" : "\u{1F512}"}
      </span>

      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm text-parchment">
          {lesson.title}
        </span>
        <span className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-white/45">
          <span>{lesson.duration_display}</span>
          {lesson.is_preview && <Badge tone="success">Free preview</Badge>}
          {lesson.quiz_id && <Badge tone="gold">Quiz</Badge>}
          {lesson.is_locked && <Badge tone="muted">Locked</Badge>}
          {lesson.is_completed && <Badge tone="success">Completed</Badge>}
        </span>
      </span>

      {lesson.is_locked && (
        <span className="shrink-0 text-xs text-white/40" aria-hidden="true">
          Requires subscription
        </span>
      )}
    </>
  );

  if (!target) {
    return (
      <li
        className="flex items-center gap-3 px-4 py-3 opacity-70"
        aria-label={`${lesson.title} (locked)`}
      >
        {content}
      </li>
    );
  }

  return (
    <li>
      <Link
        to={target}
        className="flex items-center gap-3 px-4 py-3 transition-colors hover:bg-white/5"
      >
        {content}
      </Link>
    </li>
  );
}
