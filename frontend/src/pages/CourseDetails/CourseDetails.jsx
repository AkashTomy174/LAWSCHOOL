import { Link, useParams } from "react-router-dom";

import Icon from "../../components/Icon";
import { EmptyState, ErrorState, Skeleton } from "../../components/ui";
import { useAuth } from "../../context/AuthContext";
import useAsync from "../../hooks/useAsync";
import courseService from "../../services/courseService";
import {
  formatDurationLabel,
  formatPrice,
  initials,
} from "../../utils/format";

/**
 * Course detail page.
 *
 * Important: the payload this page renders contains **no playback data**. Locked
 * lessons carry only `is_locked: true`; the video token is fetched separately by
 * the player, after the server has re-checked entitlement. Locked rows are shown
 * with an explicit lock rather than being hidden, so the student can see what a
 * subscription unlocks.
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
      <div className="wrap py-12">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="mt-4 h-5 w-1/3" />
        <Skeleton className="mt-8 h-64 w-full" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="wrap max-w-3xl py-16">
        <ErrorState error={error} onRetry={refetch} />
      </div>
    );
  }

  if (!course) return null;

  const accessible = Boolean(course.is_accessible);
  const free = course.unlock_rule === "free";
  const sections = course.sections || [];
  const allLessons = sections.flatMap((section) => section.lessons);
  const totalLessons = allLessons.length || course.lesson_count || 0;
  const firstAvailableLesson = allLessons.find((lesson) => !lesson.is_locked);
  const previewLesson = allLessons.find(
    (lesson) => lesson.is_preview && !lesson.is_locked,
  );
  const progress = Number(course.progress_percentage) || 0;

  const stats = [
    [String(totalLessons), "lessons"],
    [formatDurationLabel((course.duration_minutes || 0) * 60), "of lectures"],
    [String(course.quiz_count ?? 0), "quizzes"],
    [String(sections.length), "sections"],
  ];

  return (
    <div className="wrap pb-24 pt-10">
      <nav aria-label="Breadcrumb" className="small flex items-center gap-2 pb-8">
        <Link to="/courses" className="underline underline-offset-[3px] hover:text-ink">
          Courses
        </Link>
        <Icon name="caretRight" className="i-sm" />
        <span className="text-ink2" aria-current="page">
          {course.title}
        </span>
      </nav>

      <div className="grid gap-12 lg:grid-cols-[minmax(0,1fr)_420px] lg:items-start lg:gap-[72px]">
        {/* --------------------------------------------------------- Main column */}
        <div className="flex min-w-0 flex-col gap-12">
          <header className="flex flex-col gap-5">
            <div className="flex flex-wrap gap-2">
              {free ? (
                <span className="tag tag-ok">Free course</span>
              ) : accessible ? (
                <span className="tag tag-gold">You have access</span>
              ) : (
                <span className="tag">Subscription required</span>
              )}
              {course.language && <span className="tag">{course.language}</span>}
              {course.level && <span className="tag">{course.level}</span>}
            </div>
            <h1 className="d2">{course.title}</h1>
            {(course.subtitle || course.summary) && (
              <p className="lead">{course.subtitle || course.summary}</p>
            )}
            {course.instructor?.name && (
              <div className="flex items-center gap-3 pt-1">
                <span className="avatar !h-12 !w-12">
                  {initials(course.instructor.name)}
                </span>
                <div className="flex flex-col">
                  <span className="font-medium">{course.instructor.name}</span>
                  {course.instructor.qualification && (
                    <span className="small">
                      {course.instructor.qualification}
                    </span>
                  )}
                </div>
              </div>
            )}
            {accessible && progress > 0 && (
              <div className="flex max-w-sm flex-col gap-2 pt-2">
                <div className="flex justify-between text-sm text-ink2">
                  <span>Your progress</span>
                  <span className="mono">{Math.round(progress)}%</span>
                </div>
                <div
                  className="bar"
                  role="progressbar"
                  aria-label="Course progress"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={Math.round(progress)}
                >
                  <i style={{ width: `${progress}%` }} />
                </div>
              </div>
            )}
          </header>

          <dl className="m-0 grid grid-cols-2 border-y border-line sm:grid-cols-4">
            {stats.map(([value, label], index) => (
              <div
                key={label}
                className={`flex flex-col py-5 ${index % 2 === 1 ? "border-l border-line pl-6" : ""} ${index > 0 ? "sm:border-l sm:border-line sm:pl-6" : ""} ${index >= 2 ? "border-t border-line sm:border-t-0" : ""}`}
              >
                <dd className="m-0 font-serif text-[34px] leading-[1.1] num">
                  {value}
                </dd>
                <dt className="small">{label}</dt>
              </div>
            ))}
          </dl>

          {(course.description || course.summary) && (
            <section aria-labelledby="about-heading" className="flex flex-col gap-4">
              <h2 id="about-heading" className="h3">
                About this course
              </h2>
              <p className="body max-w-[68ch] whitespace-pre-line">
                {course.description || course.summary}
              </p>
            </section>
          )}

          <section aria-labelledby="curriculum-heading" className="flex flex-col gap-6">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <h2 id="curriculum-heading" className="h3">
                Curriculum
              </h2>
              <span className="small">
                {sections.length} section{sections.length === 1 ? "" : "s"},{" "}
                {totalLessons} lesson{totalLessons === 1 ? "" : "s"}
              </span>
            </div>

            {sections.length === 0 ? (
              <div className="border-y border-line">
                <EmptyState
                  title="Curriculum coming soon"
                  description="This course has no published sections yet."
                />
              </div>
            ) : (
              <div className="border-t border-line-strong">
                {sections.map((section, index) => (
                  <SectionBlock
                    key={section.id}
                    section={section}
                    index={index}
                    defaultOpen={index === 0}
                  />
                ))}
              </div>
            )}
          </section>
        </div>

        {/* ----------------------------------------------------------- Sidebar */}
        <aside
          aria-label="Access"
          className="card lift overflow-hidden lg:sticky lg:top-24"
        >
          <AccessHeader course={course} previewLesson={previewLesson} />

          <div className="flex flex-col gap-4 p-7">
            <h2 className="h4">{free ? "Free with any account" : "Access"}</h2>
            <div className="flex items-baseline justify-between gap-3">
              <span className="font-serif text-[40px] leading-none num">
                {free ? "Free" : formatPrice(course.price)}
              </span>
              {!free && <span className="small">included in a plan</span>}
            </div>

            {accessible ? (
              firstAvailableLesson ? (
                <Link
                  to={`/watch/${firstAvailableLesson.id}`}
                  className="btn btn-gold btn-lg btn-block"
                >
                  {progress > 0 ? "Continue learning" : "Start course"}
                </Link>
              ) : (
                <p className="small">Lessons for this course are being prepared.</p>
              )
            ) : isAuthenticated ? (
              <Link to="/subscription" className="btn btn-gold btn-lg btn-block">
                View subscription plans
              </Link>
            ) : (
              <>
                <Link to="/register" className="btn btn-gold btn-lg btn-block">
                  Create an account to start
                </Link>
                <Link to="/login" className="btn btn-line btn-block">
                  Sign in
                </Link>
              </>
            )}

            {!accessible && previewLesson && (
              <Link
                to={`/watch/${previewLesson.id}`}
                className="btn btn-line btn-block"
              >
                Preview a free lesson
              </Link>
            )}

            <hr className="rule" />
            <ul className="m-0 flex list-none flex-col gap-3 p-0 text-[15px] text-ink2">
              <li className="flex gap-3">
                <Icon name="check" className="i-sm mt-1 text-ok" />
                {totalLessons} recorded lesson{totalLessons === 1 ? "" : "s"} you
                can resume
              </li>
              {(course.quiz_count ?? 0) > 0 && (
                <li className="flex gap-3">
                  <Icon name="check" className="i-sm mt-1 text-ok" />
                  {course.quiz_count} graded quiz
                  {course.quiz_count === 1 ? "" : "zes"} with explanations
                </li>
              )}
            </ul>
          </div>
        </aside>
      </div>
    </div>
  );
}

function AccessHeader({ course, previewLesson }) {
  const inner = (
    <>
      {previewLesson ? (
        <span className="tag self-start !bg-white/10 !text-[#B4BED6]">
          Free preview
        </span>
      ) : (
        <span aria-hidden="true" />
      )}
      <span className="flex justify-center">
        <span className="flex h-[60px] w-[60px] items-center justify-center rounded-full bg-[#C9A227] text-[#0B1220]">
          <Icon name={previewLesson ? "play" : "lock"} className="i-lg" />
        </span>
      </span>
      <span className="small !text-[#B4BED6]">
        {previewLesson ? previewLesson.title : course.title}
      </span>
    </>
  );

  const className =
    "navy-surface flex h-[220px] flex-col justify-between p-5 text-left";

  return previewLesson ? (
    <Link
      to={`/watch/${previewLesson.id}`}
      className={className}
      aria-label={`Watch the free preview: ${previewLesson.title}`}
    >
      {inner}
    </Link>
  ) : (
    <div className={className}>{inner}</div>
  );
}

function SectionBlock({ section, index, defaultOpen }) {
  const lessons = section.lessons || [];
  return (
    <details
      open={defaultOpen}
      className="group border-b border-line [&_summary::-webkit-details-marker]:hidden"
    >
      <summary className="flex min-h-[64px] cursor-pointer list-none items-center justify-between gap-4 py-4">
        <span className="flex items-center gap-4">
          <span className="mono cap">{String(index + 1).padStart(2, "0")}</span>
          <h3 className="h4">{section.title}</h3>
        </span>
        <span className="flex items-center gap-4">
          <span className="small">
            {lessons.length} lesson{lessons.length === 1 ? "" : "s"}
          </span>
          <Icon name="caretDown" className="group-open:rotate-180" />
        </span>
      </summary>

      <ul className="rows m-0 mb-5 flex list-none flex-col rounded-[10px] border border-line bg-card p-0">
        {lessons.map((lesson) => (
          <LessonRow key={lesson.id} lesson={lesson} />
        ))}
        {lessons.length === 0 && (
          <li className="small px-5 py-4">
            No lessons published in this section yet.
          </li>
        )}
      </ul>
    </details>
  );
}

/**
 * One lesson row.
 *
 * Locked lessons render as non-interactive rows (not a link) so there is no
 * clickable path to a page that would only 403.
 */
function LessonRow({ lesson }) {
  const playable = !lesson.is_locked;

  const content = (
    <>
      <Icon
        name={lesson.is_completed ? "check" : playable ? "play" : "lock"}
        className={
          lesson.is_completed
            ? "text-ok"
            : playable
              ? "text-gold-ink"
              : "text-ink3"
        }
      />
      <span
        className={`min-w-0 flex-1 ${playable ? "text-ink" : "text-ink2"}`}
      >
        {lesson.title}
      </span>
      {lesson.is_preview && <span className="tag tag-gold">Free preview</span>}
      {lesson.quiz_id && <span className="tag">Quiz</span>}
      {lesson.is_completed && <span className="tag tag-ok">Completed</span>}
      <span className="mono cap">{lesson.duration_display}</span>
      {lesson.is_locked && <span className="sr-only">Locked</span>}
    </>
  );

  const rowClass = "flex min-h-[52px] items-center gap-4 px-5 py-3.5";

  return playable ? (
    <li>
      <Link
        to={`/watch/${lesson.id}`}
        className={`${rowClass} transition-colors hover:bg-sunken`}
      >
        {content}
      </Link>
    </li>
  ) : (
    <li className={rowClass}>{content}</li>
  );
}
