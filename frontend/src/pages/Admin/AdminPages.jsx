import { Link } from "react-router-dom";

import { PageHeader } from "../../components/Layout";
import { useAuth } from "../../context/AuthContext";
import { Badge, ErrorState, Panel, Skeleton } from "../../components/ui";
import useAsync from "../../hooks/useAsync";
import courseService from "../../services/courseService";
import {
  paymentService,
  subscriptionService,
} from "../../services/paymentService";
import {
  leaderboardService,
  quizService,
  userService,
} from "../../services/quizService";
import videoService from "../../services/videoService";
import { formatMoney } from "../../utils/format";

/**
 * Admin overview.
 *
 * Every counter comes from a **paginated list endpoint read with `page_size=1`**, so
 * we get the authoritative `count` without transferring rows. That keeps the
 * dashboard O(1) in payload size while still showing real numbers from the database
 * rather than a separate stats table that could drift.
 */
export default function AdminDashboard() {
  const stats = useAsync(async () => {
    const [courses, users, subscriptions, payments, videos, quizzes, attempts] =
      await Promise.all([
        courseService.list({ scope: "all", page_size: 1 }),
        userService.list({ page_size: 1 }),
        subscriptionService.all({ page_size: 1 }),
        paymentService.all({ page_size: 1 }),
        videoService.list(),
        quizService.list(),
        quizService.allAttempts({ page_size: 1 }),
      ]);

    const captured = (payments.results || []).filter(
      (row) => row.status === "captured",
    );
    return {
      courses: courses.count,
      users: users.count,
      subscriptions: subscriptions.count,
      payments: payments.count,
      videos: (videos || []).length,
      quizzes: (quizzes || []).length,
      attempts: attempts.count,
      activeSubscriptions: (subscriptions.results || []).filter(
        (r) => r.status === "active",
      ).length,
      capturedTotal: captured.reduce(
        (sum, row) => sum + Number(row.amount || 0),
        0,
      ),
    };
  }, []);

  const cards = [
    { label: "Students & staff", value: stats.data?.users, to: "/admin/users" },
    { label: "Courses", value: stats.data?.courses, to: "/admin/courses" },
    {
      label: "Active subscriptions",
      value: stats.data?.activeSubscriptions,
      to: "/admin/subscriptions",
    },
    { label: "Payments", value: stats.data?.payments, to: "/admin/payments" },
    { label: "Videos", value: stats.data?.videos, to: "/admin/videos" },
    { label: "Quizzes", value: stats.data?.quizzes, to: "/admin/quizzes" },
    {
      label: "Quiz attempts",
      value: stats.data?.attempts,
      to: "/admin/quizzes",
    },
  ];

  return (
    <div className="wrap pb-24 pt-12 lg:pt-14">
      <PageHeader
        title="Platform administration"
        description="System overview. Counts are read from the live database, not a cached summary table."
        breadcrumbs={[{ label: "Home", to: "/" }, { label: "Admin" }]}
      />

      {stats.error ? (
        <ErrorState error={stats.error} onRetry={stats.refetch} />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {cards.map((card) => (
              <Link
                key={card.label}
                to={card.to}
                className="panel panel-interactive p-4"
              >
                <p className="small">
                  {card.label}
                </p>
                {card.value === undefined ? (
                  <Skeleton className="mt-2 h-8 w-16" />
                ) : (
                  <p className="mt-1 font-serif text-[32px] leading-none num">
                    {card.value}
                  </p>
                )}
              </Link>
            ))}
          </div>

          <Panel className="mt-6 p-5">
            <h2 className="h4">
              Operational notes
            </h2>
            <div className="rule my-4" />
            <ul className="space-y-3 text-sm text-ink3">
              <li className="flex gap-3">
                <Badge tone="gold">Django admin</Badge>
                <span>
                  Full CRUD, filters and inlines live in{" "}
                  <a href="/admin/" className="text-gold-ink underline">
                    Django&apos;s admin
                  </a>
                  . This area is a read-friendly overview for day-to-day checks.
                </span>
              </li>
              <li className="flex gap-3">
                <Badge tone="gold">Payments</Badge>
                <span>
                  Payment status can only change through a verified Razorpay
                  callback or webhook — never from this UI. Use the Payments
                  page to investigate a dispute.
                </span>
              </li>
              <li className="flex gap-3">
                <Badge tone="gold">Leaderboard</Badge>
                <span>
                  Rankings are recomputed nightly by a background job; an admin
                  can force a rebuild from the leaderboard page.
                </span>
              </li>
            </ul>
          </Panel>
        </>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Users                                                                      */
/* -------------------------------------------------------------------------- */
export function AdminUsers() {
  const users = useAsync(() => userService.list({ page_size: 50 }), []);

  return (
    <div className="wrap pb-24 pt-12 lg:pt-14">
      <PageHeader
        title="Users"
        description="Search the people directory. Role changes and deactivation are done in Django admin for auditability."
        breadcrumbs={[{ label: "Admin", to: "/admin" }, { label: "Users" }]}
      />

      {users.loading ? (
        <Skeleton className="h-64 w-full" />
      ) : users.error ? (
        <ErrorState error={users.error} onRetry={users.refetch} />
      ) : (
        <Panel className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-sunken text-[13px] text-ink3 [&_th]:font-medium">
              <tr>
                <th scope="col" className="px-4 py-3">
                  Name
                </th>
                <th scope="col" className="px-4 py-3">
                  Email
                </th>
                <th scope="col" className="px-4 py-3">
                  Role
                </th>
                <th scope="col" className="px-4 py-3">
                  Status
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {(users.data?.results || []).map((row) => (
                <tr key={row.id}>
                  <td className="px-4 py-3 text-ink">{row.name}</td>
                  <td className="px-4 py-3 text-ink3">{row.email}</td>
                  <td className="px-4 py-3">
                    <Badge tone={row.role === "admin" ? "gold" : "muted"}>
                      {row.role_display}
                    </Badge>
                  </td>
                  <td className="px-4 py-3">
                    <Badge tone={row.is_email_verified ? "success" : "warning"}>
                      {row.is_email_verified ? "Verified" : "Unverified"}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Courses                                                                    */
/* -------------------------------------------------------------------------- */
export function AdminCourses() {
  // Course creation and ownership are admin-only; instructors get a read-only view.
  const { isAdmin } = useAuth();
  const courses = useAsync(
    () => courseService.list({ scope: "all", page_size: 50 }),
    [],
  );

  return (
    <div className="wrap pb-24 pt-12 lg:pt-14">
      <PageHeader
        title="Courses"
        description="All courses including drafts. Create and edit through Django admin so validation and audit trails stay server-side."
        breadcrumbs={[{ label: "Admin", to: "/admin" }, { label: "Courses" }]}
        actions={
          isAdmin ? (
            <a href="/admin/courses/course/add/" className="btn btn-primary">
              New course
            </a>
          ) : null
        }
      />

      {courses.loading ? (
        <Skeleton className="h-64 w-full" />
      ) : courses.error ? (
        <ErrorState error={courses.error} onRetry={courses.refetch} />
      ) : (
        <Panel className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-sunken text-[13px] text-ink3 [&_th]:font-medium">
              <tr>
                <th scope="col" className="px-4 py-3">
                  Title
                </th>
                <th scope="col" className="px-4 py-3">
                  Instructor
                </th>
                <th scope="col" className="px-4 py-3">
                  Status
                </th>
                <th scope="col" className="px-4 py-3">
                  Lessons
                </th>
                <th scope="col" className="px-4 py-3">
                  Price
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {(courses.data?.results || []).map((row) => (
                <tr key={row.id}>
                  <td className="px-4 py-3">
                    <Link
                      to={`/courses/${row.slug}`}
                      className="text-ink hover:text-gold-ink"
                    >
                      {row.title}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-ink3">
                    {row.instructor?.name || "—"}
                  </td>
                  <td className="px-4 py-3">
                    <Badge
                      tone={row.status === "published" ? "success" : "muted"}
                    >
                      {row.status}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 text-ink3">
                    {row.lesson_count}
                  </td>
                  <td className="px-4 py-3 text-ink3">
                    {formatMoney(row.price)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Subscriptions                                                              */
/* -------------------------------------------------------------------------- */
export function AdminSubscriptions() {
  const subscriptions = useAsync(
    () => subscriptionService.all({ page_size: 50 }),
    [],
  );

  return (
    <div className="wrap pb-24 pt-12 lg:pt-14">
      <PageHeader
        title="Subscriptions"
        description="Every subscription record with its validity window. Status corrections happen in Django admin."
        breadcrumbs={[
          { label: "Admin", to: "/admin" },
          { label: "Subscriptions" },
        ]}
      />

      {subscriptions.loading ? (
        <Skeleton className="h-64 w-full" />
      ) : subscriptions.error ? (
        <ErrorState
          error={subscriptions.error}
          onRetry={subscriptions.refetch}
        />
      ) : (
        <Panel className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-sunken text-[13px] text-ink3 [&_th]:font-medium">
              <tr>
                <th scope="col" className="px-4 py-3">
                  User
                </th>
                <th scope="col" className="px-4 py-3">
                  Plan
                </th>
                <th scope="col" className="px-4 py-3">
                  Status
                </th>
                <th scope="col" className="px-4 py-3">
                  Ends
                </th>
                <th scope="col" className="px-4 py-3">
                  Payment ref
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {(subscriptions.data?.results || []).map((row) => (
                <tr key={row.id}>
                  <td className="px-4 py-3 text-ink">{row.user_email}</td>
                  <td className="px-4 py-3 text-ink3">{row.plan?.name}</td>
                  <td className="px-4 py-3">
                    <Badge tone={row.is_currently_active ? "success" : "muted"}>
                      {row.status}
                    </Badge>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-ink3">
                    {row.end_date
                      ? new Date(row.end_date).toLocaleDateString("en-IN")
                      : "—"}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-ink3">
                    {row.payment_reference || "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Payments                                                                   */
/* -------------------------------------------------------------------------- */
export function AdminPayments() {
  const payments = useAsync(() => paymentService.all({ page_size: 50 }), []);
  const webhooks = useAsync(
    () => paymentService.webhookEvents({ page_size: 20 }),
    [],
  );

  return (
    <div className="wrap pb-24 pt-12 lg:pt-14">
      <PageHeader
        title="Payments"
        description="Read-only ledger. Status changes come exclusively from verified Razorpay events."
        breadcrumbs={[{ label: "Admin", to: "/admin" }, { label: "Payments" }]}
      />

      {payments.loading ? (
        <Skeleton className="h-64 w-full" />
      ) : payments.error ? (
        <ErrorState error={payments.error} onRetry={payments.refetch} />
      ) : (
        <Panel className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-sunken text-[13px] text-ink3 [&_th]:font-medium">
              <tr>
                <th scope="col" className="px-4 py-3">
                  Order
                </th>
                <th scope="col" className="px-4 py-3">
                  User
                </th>
                <th scope="col" className="px-4 py-3">
                  Amount
                </th>
                <th scope="col" className="px-4 py-3">
                  Status
                </th>
                <th scope="col" className="px-4 py-3">
                  Created
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {(payments.data?.results || []).map((row) => (
                <tr key={row.id}>
                  <td className="px-4 py-3 font-mono text-xs text-ink3">
                    {row.provider_order_id}
                  </td>
                  <td className="px-4 py-3 text-ink">{row.user_email}</td>
                  <td className="px-4 py-3 text-ink2">
                    {formatMoney(row.amount, row.currency)}
                  </td>
                  <td className="px-4 py-3">
                    <Badge
                      tone={
                        row.status === "captured"
                          ? "success"
                          : row.status === "failed"
                            ? "danger"
                            : "muted"
                      }
                    >
                      {row.status}
                    </Badge>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-ink3">
                    {new Date(row.created_at).toLocaleString("en-IN")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      )}

      <h2 className="h4 mt-10">
        Webhook events
      </h2>
      <div className="rule my-4" />

      {webhooks.loading ? (
        <Skeleton className="h-40 w-full" />
      ) : (
        <Panel className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-sunken text-[13px] text-ink3 [&_th]:font-medium">
              <tr>
                <th scope="col" className="px-4 py-3">
                  Event
                </th>
                <th scope="col" className="px-4 py-3">
                  Event id
                </th>
                <th scope="col" className="px-4 py-3">
                  Signature
                </th>
                <th scope="col" className="px-4 py-3">
                  Processed
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {(webhooks.data?.results || []).map((row) => (
                <tr key={row.id}>
                  <td className="px-4 py-3 text-ink2">{row.event_type}</td>
                  <td className="px-4 py-3 font-mono text-xs text-ink3">
                    {row.event_id}
                  </td>
                  <td className="px-4 py-3">
                    <Badge tone={row.signature_valid ? "success" : "danger"}>
                      {row.signature_valid ? "Valid" : "Invalid"}
                    </Badge>
                  </td>
                  <td className="px-4 py-3">
                    <Badge tone={row.processed ? "success" : "warning"}>
                      {row.processed ? "Yes" : "No"}
                    </Badge>
                    {row.processing_error && (
                      <span className="mt-1 block text-xs text-bad/80">
                        {row.processing_error}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
              {(webhooks.data?.results || []).length === 0 && (
                <tr>
                  <td
                    colSpan={4}
                    className="px-4 py-6 text-center text-ink3"
                  >
                    No webhook events received yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </Panel>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Videos                                                                     */
/* -------------------------------------------------------------------------- */
export function AdminVideos() {
  // Video editing is admin-only; instructors get a read-only view.
  const { isAdmin } = useAuth();
  const videos = useAsync(() => videoService.list(), []);

  async function sync(uid) {
    await videoService.sync(uid);
    videos.refetch({ silent: true });
  }

  return (
    <div className="wrap pb-24 pt-12 lg:pt-14">
      <PageHeader
        title="Videos"
        description="Cloudflare Stream assets. Files are never stored on the application server — only metadata lives in the database."
        breadcrumbs={[{ label: "Admin", to: "/admin" }, { label: "Videos" }]}
      />

      {videos.loading ? (
        <Skeleton className="h-64 w-full" />
      ) : videos.error ? (
        <ErrorState error={videos.error} onRetry={videos.refetch} />
      ) : (
        <Panel className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-sunken text-[13px] text-ink3 [&_th]:font-medium">
              <tr>
                <th scope="col" className="px-4 py-3">
                  Title
                </th>
                <th scope="col" className="px-4 py-3">
                  Cloudflare id
                </th>
                <th scope="col" className="px-4 py-3">
                  Status
                </th>
                <th scope="col" className="px-4 py-3">
                  Duration
                </th>
                <th scope="col" className="px-4 py-3">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {(videos.data || []).map((row) => (
                <tr key={row.id}>
                  <td className="px-4 py-3 text-ink">{row.title}</td>
                  <td className="px-4 py-3 font-mono text-xs text-ink3">
                    {row.cloudflare_video_id}
                  </td>
                  <td className="px-4 py-3">
                    <Badge
                      tone={
                        row.status === "ready"
                          ? "success"
                          : row.status === "failed"
                            ? "danger"
                            : "warning"
                      }
                    >
                      {row.status}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 text-ink3">
                    {Math.floor((row.duration_seconds || 0) / 60)}m
                  </td>
                  <td className="px-4 py-3">
                    {isAdmin ? (
                      <button
                        type="button"
                        onClick={() => sync(row.playback_uid)}
                        className="text-xs text-gold-ink hover:underline"
                      >
                        Re-sync
                      </button>
                    ) : (
                      <span className="text-xs text-ink3">View only</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Quizzes                                                                    */
/* -------------------------------------------------------------------------- */
export function AdminQuizzes() {
  const quizzes = useAsync(() => quizService.list(), []);
  const attempts = useAsync(
    () => quizService.allAttempts({ page_size: 20 }),
    [],
  );

  return (
    <div className="wrap pb-24 pt-12 lg:pt-14">
      <PageHeader
        title="Quizzes"
        description="Quiz inventory and the latest graded attempts. Scoring is always computed server-side."
        breadcrumbs={[{ label: "Admin", to: "/admin" }, { label: "Quizzes" }]}
      />

      {quizzes.loading ? (
        <Skeleton className="h-48 w-full" />
      ) : quizzes.error ? (
        <ErrorState error={quizzes.error} onRetry={quizzes.refetch} />
      ) : (
        <Panel className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-sunken text-[13px] text-ink3 [&_th]:font-medium">
              <tr>
                <th scope="col" className="px-4 py-3">
                  Title
                </th>
                <th scope="col" className="px-4 py-3">
                  Questions
                </th>
                <th scope="col" className="px-4 py-3">
                  Pass mark
                </th>
                <th scope="col" className="px-4 py-3">
                  Published
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {(quizzes.data || []).map((row) => (
                <tr key={row.id}>
                  <td className="px-4 py-3 text-ink">{row.title}</td>
                  <td className="px-4 py-3 text-ink3">
                    {row.question_count}
                  </td>
                  <td className="px-4 py-3 text-ink3">
                    {row.pass_percentage}%
                  </td>
                  <td className="px-4 py-3">
                    <Badge tone={row.is_published ? "success" : "muted"}>
                      {row.is_published ? "Live" : "Draft"}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      )}

      <h2 className="h4 mt-10">
        Recent attempts
      </h2>
      <div className="rule my-4" />

      <Panel className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="bg-sunken text-[13px] text-ink3 [&_th]:font-medium">
            <tr>
              <th scope="col" className="px-4 py-3">
                Quiz
              </th>
              <th scope="col" className="px-4 py-3">
                Score
              </th>
              <th scope="col" className="px-4 py-3">
                Result
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {(attempts.data?.results || []).map((row) => (
              <tr key={row.id}>
                <td className="px-4 py-3 text-ink2">{row.quiz_title}</td>
                <td className="px-4 py-3 text-ink3">
                  {row.score}/{row.max_score} (
                  {Math.round(Number(row.percentage))}%)
                </td>
                <td className="px-4 py-3">
                  <Badge tone={row.passed ? "success" : "danger"}>
                    {row.passed ? "Passed" : "Failed"}
                  </Badge>
                </td>
              </tr>
            ))}
            {(attempts.data?.results || []).length === 0 && (
              <tr>
                <td colSpan={3} className="px-4 py-6 text-center text-ink3">
                  No attempts recorded yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Panel>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Leaderboard admin                                                          */
/* -------------------------------------------------------------------------- */
export function AdminLeaderboard() {
  const board = useAsync(() => leaderboardService.list({ page: 1 }), []);

  async function recalculate() {
    await leaderboardService.recalculate();
    board.refetch({ silent: true });
  }

  return (
    <div className="wrap pb-24 pt-12 lg:pt-14">
      <PageHeader
        title="Leaderboard"
        description="Rankings are denormalised for performance and rebuilt by a nightly job."
        breadcrumbs={[
          { label: "Admin", to: "/admin" },
          { label: "Leaderboard" },
        ]}
        actions={
          <button type="button" onClick={recalculate} className="btn btn-ghost">
            Recalculate now
          </button>
        }
      />

      {board.loading ? (
        <Skeleton className="h-64 w-full" />
      ) : board.error ? (
        <ErrorState error={board.error} onRetry={board.refetch} />
      ) : (
        <Panel className="overflow-hidden">
          <table className="w-full text-left text-sm">
            <thead className="bg-sunken text-[13px] text-ink3 [&_th]:font-medium">
              <tr>
                <th scope="col" className="px-4 py-3">
                  Rank
                </th>
                <th scope="col" className="px-4 py-3">
                  Student
                </th>
                <th scope="col" className="px-4 py-3">
                  Quiz
                </th>
                <th scope="col" className="px-4 py-3">
                  Lessons
                </th>
                <th scope="col" className="px-4 py-3 text-right">
                  Total
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {(board.data?.results || []).map((row) => (
                <tr key={row.user_id}>
                  <td className="px-4 py-3 text-ink2">{row.rank}</td>
                  <td className="px-4 py-3 text-ink">{row.name}</td>
                  <td className="px-4 py-3 text-ink3">{row.quiz_score}</td>
                  <td className="px-4 py-3 text-ink3">
                    {row.lessons_completed}
                  </td>
                  <td className="px-4 py-3 mono text-right font-medium">
                    {row.total_score}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      )}
    </div>
  );
}
