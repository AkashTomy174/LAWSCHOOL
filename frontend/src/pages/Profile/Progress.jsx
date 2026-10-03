import { Link } from "react-router-dom";

import { EmptyState, ErrorState, Skeleton } from "../../components/ui";
import { useUI } from "../../context/UIContext";
import useAsync from "../../hooks/useAsync";
import { notificationService } from "../../services/quizService";
import videoService from "../../services/videoService";
import { formatDuration, formatRelative } from "../../utils/format";

/** Page title block shared by the two pages in this file. */
function PageTitle({ title, description, action }) {
  return (
    <div className="flex flex-col justify-between gap-6 pb-10 md:flex-row md:items-end">
      <div className="flex flex-col gap-3">
        <h1 className="d2">{title}</h1>
        <p className="body max-w-[560px]">{description}</p>
      </div>
      {action}
    </div>
  );
}

/**
 * Progress overview.
 *
 * One paginated request for progress rows plus one per course summary would be N+1
 * requests, so instead the page uses the progress endpoint for the recent-activity
 * list only. Per-course bars live on the dashboard, which reads the course list.
 */
export function Progress() {
  const recent = useAsync(() => videoService.myProgress({ page_size: 20 }), []);
  const rows = recent.data?.results || [];

  return (
    <div className="wrap pb-24 pt-12 lg:pt-16">
      <div className="max-w-[960px]">
      <PageTitle
        title="Your progress"
        description="Every lesson you have opened, with the furthest position reached."
      />

      {recent.loading ? (
        <div className="flex flex-col gap-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <Skeleton key={index} className="h-20 w-full" />
          ))}
        </div>
      ) : recent.error ? (
        <ErrorState error={recent.error} onRetry={recent.refetch} />
      ) : rows.length === 0 ? (
        <div className="border-y border-line">
          <EmptyState
            title="No playback recorded yet"
            description="Open a lesson and your progress will appear here automatically."
            action={
              <Link to="/courses" className="btn btn-gold">
                Browse courses
              </Link>
            }
          />
        </div>
      ) : (
        <ul className="rows m-0 flex list-none flex-col border-t border-line-strong p-0">
          {rows.map((row) => {
            const percent = Math.round(Number(row.completion_percentage) || 0);
            return (
              <li key={row.id}>
                <Link
                  to={`/watch/${row.lesson_id}`}
                  className="flex flex-col gap-3 py-6 sm:flex-row sm:items-center sm:gap-6"
                >
                  <span className="flex min-w-0 flex-1 flex-col gap-2">
                    <span className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                      <span className="text-[17px] font-medium">
                        {row.completed ? "Review lesson" : "Resume lesson"}
                      </span>
                      <span className="cap">
                        Updated {formatRelative(row.updated_at)}, at{" "}
                        <span className="mono">
                          {formatDuration(row.last_position)}
                        </span>
                      </span>
                    </span>
                    <span
                      className="bar"
                      role="progressbar"
                      aria-label="Lesson progress"
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-valuenow={percent}
                    >
                      <i style={{ width: `${percent}%` }} />
                    </span>
                  </span>
                  {row.completed ? (
                    <span className="tag tag-ok self-start sm:self-center">
                      Completed
                    </span>
                  ) : (
                    <span className="mono w-14 text-right font-medium">
                      {percent}%
                    </span>
                  )}
                </Link>
              </li>
            );
          })}
        </ul>
      )}
      </div>
    </div>
  );
}

/**
 * Notification centre.
 *
 * In-app notifications are the durable record; emails are a delivery channel for the
 * same events. Marking as read is optimistic locally and confirmed by the API.
 */
export function Notifications() {
  const { setUnreadCount } = useUI();
  const { data, loading, error, refetch, setData } = useAsync(
    () => notificationService.list({ page_size: 30 }),
    [],
  );

  async function markRead(id) {
    try {
      await notificationService.markRead({ notification_id: id });
      setData((current) => ({
        ...current,
        results: current.results.map((row) =>
          row.id === id
            ? { ...row, is_read: true, read_at: new Date().toISOString() }
            : row,
        ),
      }));
      setUnreadCount((count) => Math.max(0, count - 1));
    } catch {
      refetch({ silent: true });
    }
  }

  async function markAllRead() {
    try {
      await notificationService.markRead({ all: true });
      setData((current) => ({
        ...current,
        results: current.results.map((row) => ({ ...row, is_read: true })),
      }));
      setUnreadCount(0);
    } catch {
      refetch({ silent: true });
    }
  }

  const items = data?.results || [];
  const unread = items.filter((row) => !row.is_read).length;

  return (
    <div className="wrap pb-24 pt-12 lg:pt-16">
      <div className="max-w-[860px]">
      <PageTitle
        title="Notifications"
        description="Payment receipts, subscription reminders and quiz results."
        action={
          unread > 0 && (
            <button type="button" className="btn btn-line" onClick={markAllRead}>
              Mark all read
            </button>
          )
        }
      />

      {loading ? (
        <div className="flex flex-col gap-3">
          {Array.from({ length: 5 }).map((_, index) => (
            <Skeleton key={index} className="h-20 w-full" />
          ))}
        </div>
      ) : error ? (
        <ErrorState error={error} onRetry={refetch} />
      ) : items.length === 0 ? (
        <div className="border-y border-line">
          <EmptyState
            title="Nothing to show"
            description="Payment receipts and course updates will appear here."
          />
        </div>
      ) : (
        <ul className="rows m-0 flex list-none flex-col border-t border-line-strong p-0">
          {items.map((item) => (
            <li
              key={item.id}
              className={`flex items-start justify-between gap-6 py-6 ${item.is_read ? "" : "bg-gold-tint px-4 -mx-4 rounded-[10px]"}`}
            >
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-medium">{item.title}</p>
                  {!item.is_read && <span className="tag tag-gold">New</span>}
                </div>
                <p className="body mt-1 !text-[15px]">{item.body}</p>
                <p className="cap mt-2">{formatRelative(item.created_at)}</p>
              </div>

              <div className="flex shrink-0 flex-col items-end">
                {item.action_url && (
                  <Link
                    to={item.action_url}
                    className="inline-flex h-11 items-center text-[15px] font-medium text-gold-ink underline-offset-4 hover:underline"
                  >
                    Open
                  </Link>
                )}
                {!item.is_read && (
                  <button
                    type="button"
                    onClick={() => markRead(item.id)}
                    className="h-11 text-[15px] text-ink3 underline-offset-4 hover:text-ink hover:underline"
                  >
                    Mark read
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      </div>
    </div>
  );
}

export default Progress;
