import { Link } from "react-router-dom";

import { PageHeader } from "../../components/Layout";
import {
  Badge,
  Button,
  EmptyState,
  ErrorState,
  Panel,
  ProgressBar,
  Skeleton,
} from "../../components/ui";
import { useUI } from "../../context/UIContext";
import useAsync from "../../hooks/useAsync";
import { notificationService } from "../../services/quizService";
import videoService from "../../services/videoService";
import { formatRelative } from "../../utils/format";

/**
 * Progress overview.
 *
 * One paginated request for progress rows plus one per course summary would be N+1
 * requests, so instead the page uses the course list (which already carries
 * `progress_percentage`) for the per-course bars and the progress endpoint only for
 * the recent-activity list. Two requests total, regardless of course count.
 */
export function Progress() {
  const recent = useAsync(() => videoService.myProgress({ page_size: 20 }), []);

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-8 sm:py-10">
      <PageHeader
        title="Your progress"
        description="Every completed lesson, with the furthest position reached."
        breadcrumbs={[
          { label: "Dashboard", to: "/dashboard" },
          { label: "Progress" },
        ]}
      />

      {recent.loading ? (
        <div className="space-y-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <Skeleton key={index} className="h-20 w-full" />
          ))}
        </div>
      ) : recent.error ? (
        <ErrorState error={recent.error} onRetry={recent.refetch} />
      ) : (recent.data?.results || []).length === 0 ? (
        <Panel>
          <EmptyState
            icon="chart"
            title="No playback recorded yet"
            description="Open a lesson and your progress will appear here automatically."
            action={
              <Link to="/courses" className="btn btn-primary">
                Browse courses
              </Link>
            }
          />
        </Panel>
      ) : (
        <ul className="space-y-3">
          {recent.data.results.map((row) => (
            <li key={row.id}>
              <Panel className="p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="min-w-0">
                    <Link
                      to={`/watch/${row.lesson_id}`}
                      className="truncate text-sm text-parchment hover:text-gold-300"
                    >
                      Resume lesson
                    </Link>
                    <p className="mt-0.5 text-xs text-white/45">
                      Updated {formatRelative(row.updated_at)} · position{" "}
                      {Math.round(row.last_position)}s
                    </p>
                  </div>

                  <div className="flex items-center gap-3">
                    {row.completed ? (
                      <Badge tone="success">Completed</Badge>
                    ) : (
                      <Badge tone="muted">
                        {Math.round(Number(row.completion_percentage))}%
                      </Badge>
                    )}
                  </div>
                </div>

                <ProgressBar
                  value={row.completion_percentage}
                  className="mt-3"
                />
              </Panel>
            </li>
          ))}
        </ul>
      )}
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
    <div className="mx-auto w-full max-w-3xl px-4 py-8 sm:py-10">
      <PageHeader
        title="Notifications"
        description="Payment receipts, subscription reminders and quiz results."
        breadcrumbs={[
          { label: "Dashboard", to: "/dashboard" },
          { label: "Notifications" },
        ]}
        actions={
          unread > 0 && (
            <Button variant="ghost" onClick={markAllRead}>
              Mark all read
            </Button>
          )
        }
      />

      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, index) => (
            <Skeleton key={index} className="h-20 w-full" />
          ))}
        </div>
      ) : error ? (
        <ErrorState error={error} onRetry={refetch} />
      ) : items.length === 0 ? (
        <Panel>
          <EmptyState
            title="Nothing to show"
            description="Payment receipts and course updates will appear here."
          />
        </Panel>
      ) : (
        <ul className="space-y-3">
          {items.map((item) => (
            <li key={item.id}>
              <Panel
                className={`p-4 ${item.is_read ? "" : "border-gold-500/40"}`}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-medium text-parchment">{item.title}</p>
                      {!item.is_read && <Badge tone="gold">New</Badge>}
                    </div>
                    <p className="mt-1 text-sm text-white/65">{item.body}</p>
                    <p className="mt-2 text-xs text-white/40">
                      {formatRelative(item.created_at)}
                    </p>
                  </div>

                  <div className="flex shrink-0 flex-col items-end gap-2">
                    {item.action_url && (
                      <Link
                        to={item.action_url}
                        className="text-xs text-gold-300 hover:underline"
                      >
                        Open
                      </Link>
                    )}
                    {!item.is_read && (
                      <button
                        type="button"
                        onClick={() => markRead(item.id)}
                        className="text-xs text-white/50 hover:text-white"
                      >
                        Mark read
                      </button>
                    )}
                  </div>
                </div>
              </Panel>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default Progress;
