import { Link, useSearchParams } from "react-router-dom";

import Icon from "../../components/Icon";
import { Callout, ErrorState, Skeleton } from "../../components/ui";
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
  formatPrice,
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
  const { refreshUser } = useAuth();
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
        message: "Payment verified. Your subscription is active.",
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

  const statusTag = (status) =>
    status === "captured" || status === "active"
      ? "tag-ok"
      : status === "failed"
        ? "tag-bad"
        : "";

  return (
    <div className="wrap pb-24 pt-12 lg:pt-16">
      <div className="flex flex-col gap-3 pb-10">
        <h1 className="d2">Plans</h1>
        <p className="body max-w-[600px]">
          One payment unlocks every course in your plan, with graded quizzes and
          leaderboard ranking. Access runs to the end of your term and does not
          renew by itself.
        </p>
      </div>

      {justPaid && (
        <div className="mb-10">
          <Callout tone="success" title="Payment successful">
            Your subscription is active. Head to{" "}
            <Link to="/courses" className="font-medium underline">
              the course catalogue
            </Link>{" "}
            to start learning.
          </Callout>
        </div>
      )}

      {/* ------------------------------------------------------- Current plan */}
      <section aria-labelledby="current-heading" className="mb-16">
        <h2 id="current-heading" className="sr-only">
          Your subscription
        </h2>

        {mine.loading ? (
          <Skeleton className="h-36 w-full" />
        ) : mine.error ? (
          <ErrorState error={mine.error} onRetry={mine.refetch} />
        ) : active ? (
          <div className="navy-surface flex flex-col gap-6 rounded-[14px] p-8 md:flex-row md:items-center md:justify-between">
            <div className="flex flex-col gap-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="cap !text-[#B4BED6]">Your subscription</span>
                <span className="tag tag-ok">{active.status_display}</span>
                {active.plan.is_all_access && (
                  <span className="tag tag-gold">All courses</span>
                )}
              </div>
              <h3 className="h3">{active.plan.name}</h3>
              <p className="text-[15px] text-[#B4BED6]">
                {formatDaysRemaining(active.days_remaining)}, until{" "}
                {formatDate(active.end_date)}
              </p>
              {active.payment_reference && (
                <p className="mono cap !text-[#8E9AB8]">
                  Ref {active.payment_reference}
                </p>
              )}
            </div>
            <div className="flex flex-wrap gap-3">
              <Link to="/courses" className="btn btn-gold">
                Go to my courses
              </Link>
              <button
                type="button"
                className="btn btn-on-navy"
                onClick={handleCancel}
              >
                Cancel renewal
              </button>
            </div>
          </div>
        ) : (
          <div className="rounded-[10px] bg-gold-tint px-5 py-4 text-[15px] text-[#4A3A00]">
            <p className="font-medium text-[#0B1220]">No active subscription</p>
            <p className="mt-1">
              {mine.data?.history?.length
                ? "Your previous subscription has ended. Choose a plan below to restore access to your courses."
                : "Choose a plan below to unlock the full course library, quizzes and leaderboard."}
            </p>
          </div>
        )}
      </section>

      {/* ------------------------------------------------------------- Plans */}
      <section aria-labelledby="plans-heading" className="mb-20">
        <div className="flex flex-col gap-2 pb-8">
          <h2 id="plans-heading" className="h2">
            Choose how long you need.
          </h2>
          <p className="small">
            Payments are processed by Razorpay. Your card details never touch
            our servers.
          </p>
        </div>

        {plans.loading ? (
          <div className="grid gap-5 md:grid-cols-3">
            {Array.from({ length: 3 }).map((_, index) => (
              <Skeleton key={index} className="h-80 w-full" />
            ))}
          </div>
        ) : plans.error ? (
          <ErrorState error={plans.error} onRetry={plans.refetch} />
        ) : (
          <div className="grid gap-5 md:grid-cols-3">
            {(plans.data || []).map((plan) => {
              const isCurrent = active?.plan?.id === plan.id;
              const highlight = plan.is_featured;
              const tick = highlight ? "text-[#5FCB9D]" : "text-ok";
              return (
                <div
                  key={plan.id}
                  className={`flex flex-col gap-6 rounded-[14px] p-8 ${highlight ? "navy-surface" : "card"}`}
                >
                  <div className="flex flex-col gap-2">
                    <div className="flex items-center justify-between gap-3">
                      <h3 className="h3">{plan.name}</h3>
                      {highlight && (
                        <span className="tag tag-gold">Most popular</span>
                      )}
                    </div>
                    <span
                      className={`text-sm ${highlight ? "text-[#B4BED6]" : "small"}`}
                    >
                      {plan.duration_days} days of access
                    </span>
                  </div>

                  <span className="font-serif text-[52px] leading-none tracking-tight num">
                    {formatPrice(plan.price, plan.currency)}
                  </span>

                  <ul
                    className={`m-0 flex flex-1 list-none flex-col gap-3 border-t p-0 pt-6 text-[15px] ${highlight ? "border-white/[0.14] text-[#D5DBEA]" : "border-line text-ink2"}`}
                  >
                    <li className="flex gap-3">
                      <Icon name="check" className={`i-sm mt-1 ${tick}`} />
                      {plan.is_all_access
                        ? "Every published course"
                        : `${plan.course_count} course${plan.course_count === 1 ? "" : "s"} included`}
                    </li>
                    {plan.description && (
                      <li className="flex gap-3">
                        <Icon name="check" className={`i-sm mt-1 ${tick}`} />
                        {plan.description}
                      </li>
                    )}
                    {!plan.is_all_access && plan.course_slugs?.length > 0 && (
                      <li className="cap !text-inherit opacity-80">
                        Includes {plan.course_slugs.slice(0, 3).join(", ")}
                        {plan.course_slugs.length > 3 ? " and more" : ""}
                      </li>
                    )}
                  </ul>

                  {isCurrent ? (
                    <button
                      type="button"
                      className={`btn btn-lg btn-block ${highlight ? "btn-on-navy" : "btn-line"}`}
                      disabled
                    >
                      Current plan
                    </button>
                  ) : (
                    <button
                      type="button"
                      className={`btn btn-lg btn-block ${highlight ? "btn-gold" : "btn-line"}`}
                      disabled={checkout.isBusy}
                      aria-busy={checkout.isBusy || undefined}
                      onClick={() => handlePurchase(plan.slug)}
                    >
                      {active ? "Extend with this plan" : `Choose ${plan.name}`}
                    </button>
                  )}
                </div>
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
      <section aria-labelledby="history-heading" className="mb-16">
        <h2 id="history-heading" className="h3 pb-4">
          Payment history
        </h2>

        {payments.loading ? (
          <Skeleton className="h-32 w-full" />
        ) : (payments.data?.results || []).length === 0 ? (
          <p className="small border-y border-line py-6">
            No payments recorded yet.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[480px] border-collapse text-[15px]">
              <thead>
                <tr className="border-b border-line-strong text-left text-[13px] text-ink3">
                  <th scope="col" className="pb-3 font-medium">
                    Date
                  </th>
                  <th scope="col" className="pb-3 font-medium">
                    Plan
                  </th>
                  <th scope="col" className="pb-3 text-right font-medium">
                    Amount
                  </th>
                  <th scope="col" className="w-32 pb-3 text-right font-medium">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody>
                {(payments.data?.results || []).map((payment) => (
                  <tr key={payment.id} className="border-b border-line">
                    <td className="small whitespace-nowrap py-[18px] pr-4">
                      {formatDate(payment.created_at)}
                    </td>
                    <td className="pr-4">{payment.plan_name}</td>
                    <td className="mono text-right">
                      {formatMoney(payment.amount, payment.currency)}
                    </td>
                    <td className="text-right">
                      <span className={`tag ${statusTag(payment.status)}`}>
                        {payment.status_display}
                      </span>
                      {payment.failure_reason && (
                        <span className="mt-1 block text-[13px] text-bad">
                          {payment.failure_reason}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* ------------------------------------------------- Previous terms */}
      {(mine.data?.history || []).length > 0 && (
        <section aria-labelledby="terms-heading">
          <h2 id="terms-heading" className="h3 pb-4">
            Subscription history
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[480px] border-collapse text-[15px]">
              <thead>
                <tr className="border-b border-line-strong text-left text-[13px] text-ink3">
                  <th scope="col" className="pb-3 font-medium">
                    Plan
                  </th>
                  <th scope="col" className="pb-3 font-medium">
                    Period
                  </th>
                  <th scope="col" className="w-32 pb-3 text-right font-medium">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody>
                {mine.data.history.map((row) => (
                  <tr key={row.id} className="border-b border-line">
                    <td className="py-[18px] pr-4">{row.plan.name}</td>
                    <td className="small whitespace-nowrap pr-4">
                      {formatDate(row.start_date)} to {formatDate(row.end_date)}
                    </td>
                    <td className="text-right">
                      <span className={`tag ${statusTag(row.status)}`}>
                        {row.status_display}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
