import { Link, useSearchParams } from "react-router-dom";

import { PageHeader } from "../../components/Layout";
import {
  Badge,
  Button,
  Callout,
  EmptyState,
  ErrorState,
  Panel,
  Skeleton,
} from "../../components/ui";
import { useAuth } from "../../context/AuthContext";
import { useUI } from "../../context/UIContext";
import useAsync from "../../hooks/useAsync";
import useCheckout from "../../hooks/useCheckout";
import {
  paymentService,
  subscriptionService,
} from "../../services/paymentService";
import {
  formatDate,
  formatDaysRemaining,
  formatMoney,
} from "../../utils/format";

/**
 * Subscription management: current plan, plan comparison, checkout, history.
 *
 * The purchase flow deliberately ends with a **server-side verification** step. The
 * browser only reports the three Razorpay identifiers; activation happens in Django
 * after the HMAC signature checks out. A student who edits the JS or replays the
 * callback cannot activate a subscription without a valid signature.
 */
export default function Subscription() {
  const { user, refreshUser } = useAuth();
  const { pushToast } = useUI();
  const [searchParams, setSearchParams] = useSearchParams();
  const checkout = useCheckout();

  const mine = useAsync(() => subscriptionService.mine(), []);
  const plans = useAsync(() => subscriptionService.plans(), []);
  const payments = useAsync(() => paymentService.mine({ page_size: 5 }), []);

  const active = mine.data?.active;
  const justPaid = searchParams.get("status") === "success";

  async function handlePurchase(planSlug) {
    const result = await checkout.pay(planSlug);
    if (result) {
      pushToast({
        message: "Payment verified — your subscription is active.",
        tone: "success",
      });
      // Refresh every affected widget: entitlement changed, so courses and the
      // dashboard summary are stale.
      await Promise.all([
        mine.refetch({ silent: true }),
        refreshUser(),
        payments.refetch({ silent: true }),
      ]);
      const next = new URLSearchParams(searchParams);
      next.set("status", "success");
      setSearchParams(next, { replace: true });
    } else if (checkout.error) {
      pushToast({ message: checkout.error.message, tone: "error" });
    }
  }

  async function handleCancel() {
    if (
      !window.confirm(
        "Cancel your subscription? Access continues until the end of the paid term.",
      )
    ) {
      return;
    }
    try {
      await subscriptionService.cancel({ immediate: false });
      pushToast({
        message:
          "Subscription cancelled. Access continues until the term ends.",
        tone: "success",
      });
      mine.refetch({ silent: true });
    } catch (caught) {
      pushToast({ message: caught.message, tone: "error" });
    }
  }

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-8 sm:py-10">
      <PageHeader
        title="Subscription"
        description="One subscription unlocks every course included in your plan, with graded quizzes and leaderboard ranking."
        breadcrumbs={[{ label: "Home", to: "/" }, { label: "Subscription" }]}
      />

      {justPaid && (
        <div className="mb-6">
          <Callout tone="success" title="Payment successful">
            Your subscription is active. Head to{" "}
            <Link to="/courses" className="text-gold-300 underline">
              the course catalogue
            </Link>{" "}
            to start learning.
          </Callout>
        </div>
      )}

      {/* ------------------------------------------------------- Current plan */}
      <section aria-labelledby="current-heading" className="mb-10">
        <h2
          id="current-heading"
          className="font-display text-xl text-parchment"
        >
          Your subscription
        </h2>
        <div className="gold-rule my-4" />

        {mine.loading ? (
          <Skeleton className="h-32 w-full" />
        ) : mine.error ? (
          <ErrorState error={mine.error} onRetry={mine.refetch} />
        ) : active ? (
          <Panel className="p-5">
            <div className="flex flex-wrap items-start justify-between gap-5">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="font-display text-xl text-gold-300">
                    {active.plan.name}
                  </h3>
                  <Badge tone="success">{active.status_display}</Badge>
                  {active.plan.is_all_access && (
                    <Badge tone="gold">All access</Badge>
                  )}
                </div>
                <p className="mt-2 text-sm text-white/60">
                  {formatDaysRemaining(active.days_remaining)} · renews until{" "}
                  {formatDate(active.end_date)}
                </p>
                {active.payment_reference && (
                  <p className="mt-1 text-xs text-white/40">
                    Payment reference: {active.payment_reference}
                  </p>
                )}
              </div>

              <div className="flex flex-wrap gap-2">
                <Link to="/courses" className="btn btn-primary">
                  Go to my courses
                </Link>
                <Button variant="ghost" onClick={handleCancel}>
                  Cancel renewal
                </Button>
              </div>
            </div>
          </Panel>
        ) : (
          <Panel>
            <EmptyState
              icon="lock"
              title="No active subscription"
              description={
                mine.data?.history?.length
                  ? "Your previous subscription has ended. Choose a plan below to restore access to your courses."
                  : "Choose a plan below to unlock the full course library, quizzes and leaderboard."
              }
            />
          </Panel>
        )}
      </section>

      {/* ------------------------------------------------------------- Plans */}
      <section aria-labelledby="plans-heading">
        <h2 id="plans-heading" className="font-display text-xl text-parchment">
          Available plans
        </h2>
        <p className="mt-1 text-sm text-white/55">
          Prices are charged securely through Razorpay. Your card details never
          touch our servers.
        </p>
        <div className="gold-rule my-4" />

        {plans.loading ? (
          <div className="grid gap-5 md:grid-cols-3">
            {Array.from({ length: 3 }).map((_, index) => (
              <Skeleton key={index} className="h-72 w-full" />
            ))}
          </div>
        ) : plans.error ? (
          <ErrorState error={plans.error} onRetry={plans.refetch} />
        ) : (
          <div className="grid gap-5 md:grid-cols-3">
            {(plans.data || []).map((plan) => {
              const isCurrent = active?.plan?.id === plan.id;
              return (
                <Panel
                  key={plan.id}
                  className={`flex flex-col p-6 ${plan.is_featured ? "border-gold-500" : ""}`}
                >
                  {plan.is_featured && (
                    <div className="mb-3">
                      <Badge tone="gold">Most popular</Badge>
                    </div>
                  )}

                  <h3 className="font-display text-xl text-parchment">
                    {plan.name}
                  </h3>
                  <p className="mt-2 flex-1 text-sm text-white/55">
                    {plan.description}
                  </p>

                  <p className="mt-5 font-display text-3xl text-gold-300">
                    {formatMoney(plan.price, plan.currency)}
                  </p>
                  <p className="mt-1 text-xs text-white/45">
                    for {plan.duration_days} days
                    {plan.is_all_access
                      ? " · every published course"
                      : ` · ${plan.course_count} course${plan.course_count === 1 ? "" : "s"}`}
                  </p>

                  <div className="mt-6">
                    {isCurrent ? (
                      <Button variant="ghost" disabled className="w-full">
                        Current plan
                      </Button>
                    ) : (
                      <Button
                        className="w-full"
                        loading={checkout.isBusy}
                        onClick={() => handlePurchase(plan.slug)}
                      >
                        {active ? "Extend with this plan" : "Subscribe"}
                      </Button>
                    )}
                  </div>

                  {!plan.is_all_access && plan.course_slugs?.length > 0 && (
                    <p className="mt-3 text-xs text-white/40">
                      Includes: {plan.course_slugs.slice(0, 3).join(", ")}
                      {plan.course_slugs.length > 3 ? " and more" : ""}
                    </p>
                  )}
                </Panel>
              );
            })}
          </div>
        )}

        {checkout.error && (
          <div className="mt-5">
            <ErrorState error={checkout.error} />
          </div>
        )}
      </section>

      {/* --------------------------------------------------------- History */}
      <section aria-labelledby="history-heading" className="mt-12">
        <h2
          id="history-heading"
          className="font-display text-xl text-parchment"
        >
          Payment history
        </h2>
        <div className="gold-rule my-4" />

        {payments.loading ? (
          <Skeleton className="h-32 w-full" />
        ) : (payments.data?.results || []).length === 0 ? (
          <Panel className="p-6 text-sm text-white/55">
            No payments recorded yet.
          </Panel>
        ) : (
          <Panel className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-white/[0.03] text-xs uppercase tracking-wider text-white/50">
                <tr>
                  <th scope="col" className="px-4 py-3">
                    Date
                  </th>
                  <th scope="col" className="px-4 py-3">
                    Plan
                  </th>
                  <th scope="col" className="px-4 py-3">
                    Amount
                  </th>
                  <th scope="col" className="px-4 py-3">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {(payments.data?.results || []).map((payment) => (
                  <tr key={payment.id}>
                    <td className="whitespace-nowrap px-4 py-3 text-white/70">
                      {formatDate(payment.created_at)}
                    </td>
                    <td className="px-4 py-3 text-white/80">
                      {payment.plan_name}
                    </td>
                    <td className="px-4 py-3 text-white/80">
                      {formatMoney(payment.amount, payment.currency)}
                    </td>
                    <td className="px-4 py-3">
                      <Badge
                        tone={
                          payment.status === "captured"
                            ? "success"
                            : payment.status === "failed"
                              ? "danger"
                              : "muted"
                        }
                      >
                        {payment.status_display}
                      </Badge>
                      {payment.failure_reason && (
                        <span className="mt-1 block text-xs text-red-300/80">
                          {payment.failure_reason}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>
        )}
      </section>

      {/* ------------------------------------------------- Previous terms */}
      {(mine.data?.history || []).length > 0 && (
        <section aria-labelledby="terms-heading" className="mt-12">
          <h2
            id="terms-heading"
            className="font-display text-xl text-parchment"
          >
            Subscription history
          </h2>
          <div className="gold-rule my-4" />
          <Panel className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-white/[0.03] text-xs uppercase tracking-wider text-white/50">
                <tr>
                  <th scope="col" className="px-4 py-3">
                    Plan
                  </th>
                  <th scope="col" className="px-4 py-3">
                    Period
                  </th>
                  <th scope="col" className="px-4 py-3">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {mine.data.history.map((row) => (
                  <tr key={row.id}>
                    <td className="px-4 py-3 text-white/80">{row.plan.name}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-white/65">
                      {formatDate(row.start_date)} — {formatDate(row.end_date)}
                    </td>
                    <td className="px-4 py-3">
                      <Badge
                        tone={
                          row.status === "active"
                            ? "success"
                            : row.status === "failed"
                              ? "danger"
                              : "muted"
                        }
                      >
                        {row.status_display}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>
        </section>
      )}
    </div>
  );
}
