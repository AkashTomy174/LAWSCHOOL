import { Link } from "react-router-dom";

import { formatDurationLabel, formatMoney, truncate } from "../utils/format";
import { Badge, ProgressBar } from "./ui";

/**
 * Course card.
 *
 * Access state is rendered from the server's `is_accessible` flag — the card never
 * decides entitlement itself. Locked courses are still *shown* (it is a
 * catalogue), but the CTA becomes "View plans" and the progress bar is hidden,
 * because partial progress on inaccessible content makes no sense.
 */
export default function CourseCard({ course }) {
  const accessible = Boolean(course.is_accessible);
  const progress = Number(course.progress_percentage) || 0;

  return (
    <article className="panel panel-interactive flex h-full flex-col overflow-hidden">
      <Link
        to={`/courses/${course.slug}`}
        className="block focus-visible:outline focus-visible:outline-2 focus-visible:outline-gold-500"
        aria-label={`View ${course.title}`}
      >
        <div className="relative aspect-video w-full overflow-hidden bg-navy-800">
          {course.thumbnail_url ? (
            <img
              src={course.thumbnail_url}
              alt=""
              loading="lazy"
              className="h-full w-full object-cover"
            />
          ) : (
            <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-navy-800 to-ink-900">
              <span
                className="font-display text-3xl text-gold-500/40"
                aria-hidden="true"
              >
                {"\u2696"}
              </span>
            </div>
          )}

          <div className="absolute left-3 top-3 flex flex-wrap gap-2">
            {course.unlock_rule === "free" && (
              <Badge tone="success">Free</Badge>
            )}
            {!accessible && course.unlock_rule !== "free" && (
              <Badge tone="muted">Locked</Badge>
            )}
            {accessible && progress > 0 && (
              <Badge tone="gold">In progress</Badge>
            )}
          </div>
        </div>
      </Link>

      <div className="flex flex-1 flex-col p-4">
        <div className="mb-2 flex items-center gap-2 text-xs text-white/45">
          {course.level && <span>{course.level}</span>}
          {course.level && <span aria-hidden="true">·</span>}
          <span>{course.lesson_count} lessons</span>
          {course.duration_minutes > 0 && (
            <>
              <span aria-hidden="true">·</span>
              <span>{formatDurationLabel(course.duration_minutes * 60)}</span>
            </>
          )}
        </div>

        <h3 className="font-display text-lg leading-snug text-parchment">
          <Link to={`/courses/${course.slug}`} className="hover:text-gold-300">
            {course.title}
          </Link>
        </h3>

        <p className="mt-2 flex-1 text-sm text-white/60">
          {truncate(course.summary || course.subtitle || "", 110)}
        </p>

        {course.instructor?.name && (
          <p className="mt-3 text-xs text-white/45">
            By {course.instructor.name}
          </p>
        )}

        {accessible && progress > 0 && (
          <ProgressBar
            value={progress}
            label="Your progress"
            className="mt-4"
          />
        )}

        <div className="mt-4 flex items-center justify-between gap-3">
          <span className="text-sm font-semibold text-gold-300">
            {course.unlock_rule === "free"
              ? "Included free"
              : formatMoney(course.price)}
          </span>

          <Link
            to={`/courses/${course.slug}`}
            className={`btn !min-h-0 !py-2 text-sm ${accessible ? "btn-ghost" : "btn-primary"}`}
          >
            {accessible ? "Continue" : "View course"}
          </Link>
        </div>
      </div>
    </article>
  );
}
