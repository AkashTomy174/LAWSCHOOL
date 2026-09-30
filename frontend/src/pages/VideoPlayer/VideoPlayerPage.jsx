import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { PageHeader } from "../../components/Layout";
import VideoPlayer from "../../components/VideoPlayer";
import {
  Badge,
  Button,
  Callout,
  ErrorState,
  Panel,
  Skeleton,
} from "../../components/ui";
import useAsync from "../../hooks/useAsync";
import courseService from "../../services/courseService";
import videoService from "../../services/videoService";

/**
 * Watch page: player on the left, lesson navigation on the right.
 *
 * The page fetches lesson metadata and the course's lesson list, but **not** the
 * playback token — `VideoPlayer` requests that itself so the token is minted as
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
      <div className="mx-auto w-full max-w-7xl px-4 py-8">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="mt-4 aspect-video w-full" />
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
      <div className="mx-auto w-full max-w-3xl px-4 py-16">
        <Panel className="p-8 text-center">
          <h1 className="font-display text-2xl text-gold-300">
            {locked ? "This lesson is locked" : "Lesson unavailable"}
          </h1>
          <p className="mt-3 text-sm text-white/70">
            {error.message ||
              "This lesson could not be loaded. It may have been unpublished."}
          </p>
          <div className="mt-6 flex flex-wrap justify-center gap-3">
            {locked ? (
              <Link to="/subscription" className="btn btn-primary">
                View subscription plans
              </Link>
            ) : (
              <Button variant="ghost" onClick={refetch}>
                Try again
              </Button>
            )}
            <Link to="/courses" className="btn btn-ghost">
              Back to courses
            </Link>
          </div>
        </Panel>
      </div>
    );
  }

  if (!watch) return null;

  const { lesson, course, access, playback } = watch;
  const lessons = lessonList?.lessons || [];
  const currentIndex = lessons.findIndex((row) => row.id === lesson.id);
  const previous = currentIndex > 0 ? lessons[currentIndex - 1] : null;
  const next =
    currentIndex >= 0 && currentIndex < lessons.length - 1
      ? lessons[currentIndex + 1]
      : null;

  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-6 sm:py-8">
      <PageHeader
        title={lesson.title}
        breadcrumbs={[
          { label: "Courses", to: "/courses" },
          { label: course.title, to: `/courses/${course.slug}` },
          { label: lesson.title },
        ]}
        actions={
          lesson.is_preview ? (
            <Badge tone="success">Free preview</Badge>
          ) : (
            <Badge tone="gold">Enrolled</Badge>
          )
        }
      />

      <div className="grid gap-6 lg:grid-cols-[1.7fr_1fr] lg:items-start">
        <div className="space-y-5">
          {playback?.video_uid ? (
            <VideoPlayer
              videoUid={playback.video_uid}
              lessonTitle={lesson.title}
              resumeAt={resumeAt}
              onCompleted={() => refetch({ silent: true })}
            />
          ) : (
            <Callout tone="info">
              This lesson does not have a video attached yet. Check back soon.
            </Callout>
          )}

          <Panel className="p-5">
            <h2 className="font-display text-lg text-parchment">
              About this lesson
            </h2>
            <div className="gold-rule my-3" />
            <p className="whitespace-pre-line text-sm leading-relaxed text-white/70">
              {lesson.description ||
                "No description has been added for this lesson."}
            </p>
          </Panel>

          <div className="flex flex-wrap items-center justify-between gap-3">
            <Button
              variant="ghost"
              disabled={!previous || previous.is_locked}
              onClick={() => previous && navigate(`/watch/${previous.id}`)}
            >
              ← Previous lesson
            </Button>
            <Link
              to={`/courses/${course.slug}`}
              className="text-sm text-gold-300 hover:underline"
            >
              Back to course
            </Link>
            <Button
              variant="ghost"
              disabled={!next || next.is_locked}
              onClick={() => next && navigate(`/watch/${next.id}`)}
            >
              Next lesson →
            </Button>
          </div>
        </div>

        <aside aria-labelledby="lesson-list-heading">
          <Panel className="overflow-hidden">
            <div className="border-b border-[var(--color-border-subtle)] px-4 py-3">
              <h2
                id="lesson-list-heading"
                className="font-display text-base text-parchment"
              >
                Course contents
              </h2>
              <p className="mt-0.5 text-xs text-white/45">
                {lessons.filter((row) => row.is_completed).length} of{" "}
                {lessons.length} completed
              </p>
            </div>

            <ol className="max-h-[70vh] divide-y divide-white/5 overflow-y-auto">
              {lessons.map((row, index) => {
                const isCurrent = row.id === lesson.id;
                return (
                  <li key={row.id}>
                    {row.is_locked ? (
                      <div className="flex items-center gap-3 px-4 py-3 opacity-60">
                        <span
                          className="text-xs text-white/40"
                          aria-hidden="true"
                        >
                          {"\u{1F512}"}
                        </span>
                        <span className="min-w-0 flex-1 truncate text-sm">
                          {row.title}
                        </span>
                        <Badge tone="muted">Locked</Badge>
                      </div>
                    ) : (
                      <Link
                        to={`/watch/${row.id}`}
                        aria-current={isCurrent ? "page" : undefined}
                        className={`flex items-center gap-3 px-4 py-3 transition-colors ${
                          isCurrent ? "bg-gold-500/10" : "hover:bg-white/5"
                        }`}
                      >
                        <span
                          className={`text-xs ${row.is_completed ? "text-emerald-300" : "text-white/40"}`}
                          aria-hidden="true"
                        >
                          {row.is_completed
                            ? "\u2713"
                            : String(index + 1).padStart(2, "0")}
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm text-parchment">
                            {row.title}
                          </span>
                          <span className="text-xs text-white/40">
                            {row.duration_display}
                          </span>
                        </span>
                        {row.quiz_id && <Badge tone="gold">Quiz</Badge>}
                      </Link>
                    )}
                  </li>
                );
              })}
            </ol>
          </Panel>
        </aside>
      </div>
    </div>
  );
}
