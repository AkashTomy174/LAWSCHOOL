import { Link } from "react-router-dom";

import { formatDurationLabel, formatPrice, truncate } from "../utils/format";
import { Badge, ProgressBar } from "./ui";

/**
 * Course row for the catalogue and the dashboard.
 *
 * Access state is rendered from the server's `is_accessible` flag; the row never
 * decides entitlement itself. Locked courses are still *shown* (it is a
 * catalogue), but the call to action becomes "View course" and the progress bar
 * is hidden, because partial progress on inaccessible content makes no sense.
 */
export default function CourseCard({ course }) {
  const accessible = Boolean(course.is_accessible);
  const progress = Number(course.progress_percentage) || 0;
  const free = course.unlock_rule === "free";

  const meta = [
    `${course.lesson_count} lessons`,
    course.duration_minutes > 0
      ? formatDurationLabel(course.duration_minutes * 60)
      : null,
    course.instructor?.name || null,
  ]
    .filter(Boolean)
    .join(", ");

  return (
    <article className="flex flex-col gap-5 py-7 sm:flex-row sm:items-stretch sm:gap-8">
      <Link
        to={`/courses/${course.slug}`}
        aria-label={`View ${course.title}`}
        className="navy-surface flex min-h-[124px] w-full flex-none flex-col justify-between overflow-hidden rounded-[10px] sm:w-[188px]"
      >
        {course.thumbnail_url ? (
          <img
            src={course.thumbnail_url}
            alt=""
            loading="lazy"
            className="h-full min-h-[124px] w-full object-cover"
          />
        ) : (
          <span className="flex min-h-[124px] flex-1 flex-col justify-between p-4">
            <span className="mono cap !text-[#B4BED6]">
              {course.level || "Course"}
            </span>
            <span className="font-serif text-[44px] leading-none text-[#EEF1F8] num">
              {course.lesson_count}
            </span>
          </span>
        )}
      </Link>

      <div className="flex min-w-0 flex-1 flex-col justify-center gap-2">
        <div className="flex flex-wrap gap-2">
          {free && <Badge tone="success">Free</Badge>}
          {!accessible && !free && <Badge tone="muted">Locked</Badge>}
          {accessible && progress > 0 && <Badge tone="gold">In progress</Badge>}
        </div>
        <h3 className="h3 !text-[26px] sm:!text-[28px]">
          <Link to={`/courses/${course.slug}`} className="hover:underline">
            {course.title}
          </Link>
        </h3>
        <p className="body !text-[15px]">
          {truncate(course.summary || course.subtitle || "", 130)}
        </p>
        <span className="mono cap">{meta}</span>

        {accessible && progress > 0 && (
          <ProgressBar
            value={progress}
            label="Your progress"
            className="mt-2 max-w-sm"
          />
        )}
      </div>

      <div className="flex flex-none flex-row items-center justify-between gap-3 sm:w-[150px] sm:flex-col sm:items-end sm:justify-center">
        <span className="font-serif text-[30px] leading-none num">
          {free ? "Included free" : formatPrice(course.price)}
        </span>
        <Link
          to={`/courses/${course.slug}`}
          className={`btn ${accessible ? "btn-gold" : "btn-line"}`}
        >
          {accessible ? "Continue" : "View course"}
        </Link>
      </div>
    </article>
  );
}
