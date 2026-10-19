import { useState } from "react";
import { Link } from "react-router-dom";

import { Badge, Button, EmptyState, ErrorState, Skeleton } from "../../components/ui";
import useAsync from "../../hooks/useAsync";
import liveService from "../../services/liveService";
import { formatDateTime } from "../../utils/format";

const GROUPS = [
  { status: "live", title: "Live now" },
  { status: "upcoming", title: "Upcoming" },
  { status: "ended", title: "Recently ended" },
];

const STATUS_BADGE = {
  live: { tone: "success", label: "Live now" },
  upcoming: { tone: "muted", label: "Upcoming" },
  ended: { tone: "muted", label: "Ended" },
};

/** Only hand the browser a link it can safely open (the API validates it too). */
function safeMeetingUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
  } catch {
    return null;
  }
}

/**
 * A live class the student may attend.  ``status`` and ``can_join`` come from the
 * server clock; the join endpoint re-checks entitlement and the join window, so
 * these flags only decide what to show.
 */
export function LiveClassRow({ live }) {
  const [join, setJoin] = useState({ busy: false, url: null, error: null });
  const badge = STATUS_BADGE[live.status] || STATUS_BADGE.upcoming;

  async function getLink() {
    setJoin({ busy: true, url: null, error: null });
    try {
      const info = await liveService.join(live.id);
      const url = safeMeetingUrl(info.meeting_url);
      setJoin({
        busy: false,
        url,
        error: url ? null : "This class does not have a valid meeting link yet.",
      });
    } catch (caught) {
      setJoin({ busy: false, url: null, error: caught?.message || "Could not get the link." });
    }
  }

  return (
    <li className="flex flex-col gap-3 py-5 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex min-w-0 flex-col gap-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[17px] font-medium">{live.title}</span>
          <Badge tone={badge.tone}>{badge.label}</Badge>
        </div>
        <span className="small">
          <Link to={`/courses/${live.course_slug}`} className="underline">
            {live.course_title}
          </Link>
          {live.instructor_name ? ` · ${live.instructor_name}` : ""}
        </span>
        <span className="cap">
          {formatDateTime(live.scheduled_start)} · {live.duration_minutes} min
        </span>
      </div>
      <div className="flex flex-col items-start gap-1 sm:items-end">
        {join.url ? (
          <a href={join.url} target="_blank" rel="noopener noreferrer" className="btn btn-gold">
            Open meeting
          </a>
        ) : live.can_join ? (
          <Button onClick={getLink} loading={join.busy}>
            Join class
          </Button>
        ) : (
          <p className="cap">
            {live.status === "ended"
              ? "This class has ended."
              : "You can join 15 minutes before it starts."}
          </p>
        )}
        {join.error && (
          <p role="alert" className="cap !text-bad">
            {join.error}
          </p>
        )}
      </div>
    </li>
  );
}

export default function MyLiveClasses() {
  const classes = useAsync(() => liveService.mine(), []);
  const rows = classes.data || [];

  return (
    <div className="wrap pb-24 pt-12 lg:pt-16">
      <div className="flex flex-col gap-3 pb-8">
        <h1 className="d2">Live classes</h1>
        <p className="body max-w-[600px]">
          Sessions for the courses you can access, shown in your local time.
        </p>
      </div>

      {classes.loading ? (
        <Skeleton className="h-40 w-full" />
      ) : classes.error ? (
        <ErrorState error={classes.error} onRetry={classes.refetch} />
      ) : rows.length === 0 ? (
        <EmptyState
          title="No live classes scheduled"
          description="Classes for your courses will appear here once an instructor schedules them."
          action={
            <Link to="/courses" className="btn btn-line">
              Browse courses
            </Link>
          }
        />
      ) : (
        GROUPS.map(({ status, title }) => {
          const group = rows.filter((row) => row.status === status);
          if (!group.length) return null;
          return (
            <section key={status} aria-labelledby={`live-${status}`} className="mb-10">
              <h2 id={`live-${status}`} className="h4">
                {title}
              </h2>
              <ul className="rows m-0 flex list-none flex-col border-t border-line-strong p-0">
                {group.map((live) => (
                  <LiveClassRow key={live.id} live={live} />
                ))}
              </ul>
            </section>
          );
        })
      )}
    </div>
  );
}
