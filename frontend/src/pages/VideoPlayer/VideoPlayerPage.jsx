import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import Icon from "../../components/Icon";
import VideoPlayer from "../../components/VideoPlayer";
import { Skeleton } from "../../components/ui";
import useAsync from "../../hooks/useAsync";
import courseService from "../../services/courseService";
import videoService from "../../services/videoService";

/**
 * Watch page (focus mode): player and lesson on the left, curriculum on the right.
 *
 * The page fetches lesson metadata and the course's lesson list, but **not** the
 * playback token: `VideoPlayer` requests that itself so the token is minted as
 * late as possible and lives only in the player's memory.
 */
export default function VideoPlayerPage() {
  const { lessonId } = useParams();
  const navigate = useNavigate();
  const [resumeAt, setResumeAt] = useState(0);

  const {
    data: watch,
    loading,
    error,
    refetch,
  } = useAsync(async () => {
    const payload = await courseService.watchLesson(lessonId);
    // Fetch the student's own progress for this lesson to resume playback.
    const progress = await videoService.myProgress();
    const record = (progress?.results || []).find(
      (row) => row.lesson_id === lessonId,
    );
    setResumeAt(record?.completed ? 0 : record?.last_position || 0);
    return payload;
  }, [lessonId]);

  // The lesson list is a separate concern (navigation), so it loads in parallel
  // and its failure must not blank the player.
  const courseSlug = watch?.course?.slug;
  const { data: lessonList } = useAsync(
    () =>
      courseSlug ? courseService.lessons(courseSlug) : Promise.resolve(null),
    [courseSlug],
  );

  if (loading) {
    return (
      <div className="px-4 py-8 sm:px-8">
        <Skeleton className="h-11 w-48" />
        <Skeleton className="mt-6 aspect-video w-full max-w-5xl" />
      </div>
    );
  }

  if (error) {
    const locked = [
      "subscription_required",
      "subscription_expired",
      "not_in_plan",
    ].includes(error.code);
    return (
      <div className="wrap max-w-3xl py-16">
        <div className="card flex flex-col items-center gap-4 p-8 text-center sm:p-10">
          <Icon name="lock" className="i-lg text-ink3" />
          <h1 className="h3">
            {locked ? "This lesson is locked" : "Lesson unavailable"}
          </h1>
          <p className="body">
            {error.message ||
              "This lesson could not be loaded. It may have been unpublished."}
          </p>
          <div className="flex flex-wrap justify-center gap-3 pt-2">
            {locked ? (
              <Link to="/subscription" className="btn btn-gold">
                View subscription plans
              </Link>
            ) : (
              <button type="button" className="btn btn-line" onClick={refetch}>
                Try again
              </button>
            )}
            <Link to="/courses" className="btn btn-line">
              Back to courses
            </Link>
          </div>
        </div>
      </div>
    );
  }

  if (!watch) return null;

  const { lesson, course, playback } = watch;
  const lessons = lessonList?.lessons || [];
  const currentIndex = lessons.findIndex((row) => row.id === lesson.id);
  const previous = currentIndex > 0 ? lessons[currentIndex - 1] : null;
  const next =
    currentIndex >= 0 && currentIndex < lessons.length - 1
      ? lessons[currentIndex + 1]
      : null;
  const completed = lessons.filter((row) => row.is_completed).length;
  const percent = lessons.length
    ? Math.round((completed / lessons.length) * 100)
    : 0;

  return (
    <div>
      <header className="flex min-h-[68px] flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3 sm:px-8">
        <div className="flex min-w-0 items-center gap-4">
          <Link to={`/courses/${course.slug}`} className="btn btn-line">
            <Icon name="caretLeft" />
            Course
          </Link>
          <nav
            aria-label="Breadcrumb"
            className="small hidden min-w-0 items-center gap-2 md:flex"
          >
            <span className="truncate">{course.title}</span>
            <Icon name="caretRight" className="i-sm" />
            <span className="truncate text-ink" aria-current="page">
              {lesson.title}
            </span>
          </nav>
        </div>
        <div className="flex items-center gap-4">
          {lessons.length > 0 && (
            <span className="small num hidden sm:inline">
              {percent}% of the course complete
            </span>
          )}
          {next && !next.is_locked && (
            <Link to={`/watch/${next.id}`} className="btn btn-gold">
              Next lesson
              <Icon name="caretRight" />
            </Link>
          )}
        </div>
      </header>

      <div className="grid gap-10 px-4 pb-16 pt-7 sm:px-8 lg:grid-cols-[minmax(0,1fr)_400px]">
        <div className="flex min-w-0 flex-col gap-8">
          {playback?.video_uid ? (
            <VideoPlayer
              videoUid={playback.video_uid}
              lessonTitle={lesson.title}
              resumeAt={resumeAt}
              onCompleted={() => refetch({ silent: true })}
            />
          ) : (
            <div className="card flex aspect-video items-center justify-center p-8 text-center">
              <p className="body">
                This lesson does not have a video attached yet. Check back soon.
              </p>
            </div>
          )}

          <div className="flex flex-col gap-3">
            <h1 className="d2 !text-[34px] sm:!text-[46px]">{lesson.title}</h1>
            <p className="small flex flex-wrap items-center gap-2">
              {currentIndex >= 0
                ? `Lesson ${currentIndex + 1} of ${lessons.length}, `
                : ""}
              {course.title}
              {lesson.is_preview && (
                <span className="tag tag-gold">Free preview</span>
              )}
            </p>
          </div>

          <section aria-labelledby="about-lesson" className="flex flex-col gap-3">
            <h2 id="about-lesson" className="h4 !text-[20px]">
              About this lesson
            </h2>
            <p className="body max-w-[68ch] whitespace-pre-line !text-[17px]">
              {lesson.description ||
                "No description has been added for this lesson."}
            </p>
          </section>

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-6">
            <button
              type="button"
              className="btn btn-line btn-lg"
              disabled={!previous || previous.is_locked}
              onClick={() => previous && navigate(`/watch/${previous.id}`)}
            >
              <Icon name="caretLeft" />
              Previous
            </button>
            <button
              type="button"
              className="btn btn-gold btn-lg"
              disabled={!next || next.is_locked}
              onClick={() => next && navigate(`/watch/${next.id}`)}
            >
              Next lesson
              <Icon name="caretRight" />
            </button>
          </div>
        </div>

        <aside
          aria-labelledby="lesson-list-heading"
          className="card self-start overflow-hidden lg:sticky lg:top-6"
        >
          <div className="flex flex-col gap-1 p-6 pb-5">
            <h2 id="lesson-list-heading" className="h4">
              Curriculum
            </h2>
            <span className="small num">
              {completed} of {lessons.length} lessons complete
            </span>
          </div>

          <ol className="rows m-0 flex max-h-[70vh] list-none flex-col overflow-y-auto border-t border-line p-0">
            {lessons.map((row) => (
              <LessonItem
                key={row.id}
                row={row}
                current={row.id === lesson.id}
              />
            ))}
          </ol>
        </aside>
      </div>
    </div>
  );
}

function StatusDot({ row, current }) {
  if (row.is_locked) return <Icon name="lock" className="text-ink3" />;
  if (row.is_completed)
    return (
      <span className="flex h-[22px] w-[22px] flex-none items-center justify-center rounded-full bg-ok text-[#07211A]">
        <Icon name="check" className="i-sm" />
      </span>
    );
  if (current)
    return (
      <span className="flex h-[22px] w-[22px] flex-none items-center justify-center rounded-full border-2 border-gold">
        <i className="block h-2 w-2 rounded-full bg-gold" />
      </span>
    );
  return (
    <span className="h-[22px] w-[22px] flex-none rounded-full border-[1.5px] border-control" />
  );
}

function LessonItem({ row, current }) {
  const body = (
    <>
      <StatusDot row={row} current={current} />
      <span
        className={`min-w-0 flex-1 text-[15px] ${current ? "font-medium" : ""} ${row.is_locked ? "text-ink3" : ""}`}
      >
        {row.title}
        {row.is_locked && <span className="sr-only"> (locked)</span>}
      </span>
      {row.quiz_id && <span className="tag">Quiz</span>}
      <span className="mono cap">{row.duration_display}</span>
    </>
  );

  const rowClass = `flex min-h-[52px] items-center gap-3 px-6 py-3.5 ${current ? "bg-gold-tint" : ""}`;

  return (
    <li>
      {row.is_locked ? (
        <div className={rowClass}>{body}</div>
      ) : (
        <Link
          to={`/watch/${row.id}`}
          aria-current={current ? "true" : undefined}
          className={`${rowClass} transition-colors ${current ? "" : "hover:bg-sunken"}`}
        >
          {body}
        </Link>
      )}
    </li>
  );
}
