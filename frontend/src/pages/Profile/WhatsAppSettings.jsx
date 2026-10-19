import { useState } from "react";
import { Link } from "react-router-dom";

import { PageHeader } from "../../components/Layout";
import {
  Badge,
  Button,
  Callout,
  ErrorState,
  Panel,
  Skeleton,
  TextField,
} from "../../components/ui";
import { useUI } from "../../context/UIContext";
import useAsync from "../../hooks/useAsync";
import notificationService from "../../services/notificationService";
import { formatDateTime } from "../../utils/format";
import { isPhone } from "../../utils/validation";

/** One switch per server-side category (names match the API fields). */
const CATEGORIES = [
  ["live_class_enabled", "Live classes", "Scheduled classes and reminders."],
  ["schedule_change_enabled", "Schedule changes", "Reschedules, cancellations and new joining links."],
  ["quiz_updates_enabled", "Quiz updates", "When a quiz result is ready."],
  ["progress_updates_enabled", "Progress summaries", "A short weekly summary of what you completed."],
  ["study_reminders_enabled", "Study reminders", "A nudge if you have not studied for a while."],
  ["payment_updates_enabled", "Subscription and payments", "Payment receipts and plan expiry."],
  ["announcements_enabled", "Announcements", "Important platform news."],
];

const STATUS_TONE = { delivered: "success", read: "success", failed: "danger", cancelled: "muted", suppressed: "muted" };

/**
 * WhatsApp notification settings for the signed-in user.
 *
 * Linking is consent plus proof: the user ticks an explicit consent box, we send a
 * one-time code to that WhatsApp number, and only the correct code marks it
 * verified. Everything shown here comes from the server; the browser never decides
 * whether a number is verified or a message was delivered.
 */
export default function WhatsAppSettings() {
  const { pushToast } = useUI();
  const prefs = useAsync(() => notificationService.getPreferences(), []);
  const history = useAsync(() => notificationService.history({ page_size: 10 }), []);

  const [phone, setPhone] = useState("");
  const [consent, setConsent] = useState(false);
  const [code, setCode] = useState("");
  const [step, setStep] = useState("enter"); // enter -> code
  const [errors, setErrors] = useState({});
  const [busy, setBusy] = useState(false);

  const data = prefs.data;
  const available = data?.whatsapp_available;

  async function run(action, success) {
    setBusy(true);
    setErrors({});
    try {
      const result = await action();
      if (success) pushToast({ message: success, tone: "success" });
      return result;
    } catch (caught) {
      setErrors({ form: caught?.message || "Something went wrong." });
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function sendCode(event) {
    event.preventDefault();
    const problems = {};
    if (!phone.trim()) problems.phone = "Enter your WhatsApp number.";
    else if (!isPhone(phone) || !phone.trim().startsWith("+"))
      problems.phone = "Include the country code, e.g. +919876543210.";
    if (!consent) problems.consent = "Please agree to receive WhatsApp messages.";
    if (Object.keys(problems).length) return setErrors(problems);

    const result = await run(() => notificationService.requestLink({ phone: phone.trim(), consent }));
    if (result) {
      setStep("code");
      pushToast({ message: "If that number is on WhatsApp, a code is on its way.", tone: "info" });
    }
  }

  async function confirmCode(event) {
    event.preventDefault();
    if (!/^\d{6}$/.test(code)) return setErrors({ code: "Enter the 6-digit code." });
    const result = await run(() => notificationService.verify(code), "WhatsApp number verified.");
    if (result) {
      prefs.setData(result);
      setStep("enter");
      setCode("");
      setPhone("");
      setConsent(false);
      history.refetch({ silent: true });
    }
  }

  async function update(patch, message) {
    const result = await run(() => notificationService.updatePreferences(patch), message);
    if (result) prefs.setData(result);
  }

  async function optOut() {
    if (!window.confirm("Stop all WhatsApp messages? You will need to verify your number again to resume.")) return;
    const result = await run(() => notificationService.optOut(), "You have opted out of WhatsApp messages.");
    if (result) prefs.setData(result);
  }

  return (
    <div className="wrap pb-24 pt-12 lg:pt-14">
      <PageHeader
        title="WhatsApp notifications"
        description="Get class reminders and progress updates on WhatsApp. You choose what you receive and can stop any time."
        breadcrumbs={[{ label: "Profile", to: "/profile" }, { label: "WhatsApp notifications" }]}
      />

      {prefs.loading ? (
        <Skeleton className="h-48 w-full" />
      ) : prefs.error ? (
        <ErrorState error={prefs.error} onRetry={prefs.refetch} />
      ) : (
        <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <div className="space-y-8">
            {!available && (
              <Callout tone="warning" title="Not available yet">
                WhatsApp notifications have not been switched on for LawSchool. You will be able to link your number here once they are.
              </Callout>
            )}
            {errors.form && <ErrorState error={{ message: errors.form }} />}

            <Panel className="p-5">
              <h2 className="h4">Your number</h2>
              <div className="rule my-4" />
              {data.is_verified ? (
                <div className="space-y-4">
                  <p className="flex flex-wrap items-center gap-3">
                    <span className="text-ink">{data.whatsapp_number_masked}</span>
                    {data.consent_status !== "opted_out" && <Badge tone="success">Verified</Badge>}
                    {data.consent_status === "opted_out" && <Badge tone="muted">Opted out</Badge>}
                    {data.consent_status !== "opted_out" && !data.whatsapp_enabled && <Badge tone="muted">Paused</Badge>}
                  </p>
                  <label className="flex items-start gap-3">
                    <input
                      type="checkbox"
                      className="mt-1 h-4 w-4"
                      checked={data.whatsapp_enabled}
                      disabled={busy || data.consent_status === "opted_out"}
                      onChange={(event) => update({ whatsapp_enabled: event.target.checked })}
                    />
                    <span>
                      <span className="block text-ink">Send me WhatsApp messages</span>
                      <span className="cap">Turn off to pause everything without losing your settings.</span>
                    </span>
                  </label>
                  {data.consent_status === "opted_out" ? (
                    <p className="small">You opted out. Verify your number again below to resume.</p>
                  ) : (
                    <Button variant="ghost" onClick={optOut} disabled={busy}>
                      Opt out of all WhatsApp messages
                    </Button>
                  )}
                </div>
              ) : null}

              {(!data.is_verified || data.consent_status === "opted_out") && (
                <div className={data.is_verified ? "mt-6 border-t border-line pt-6" : ""}>
                  {step === "enter" ? (
                    <form onSubmit={sendCode} noValidate className="space-y-4">
                      <TextField
                        id="wa-phone"
                        label="WhatsApp number"
                        type="tel"
                        inputMode="tel"
                        autoComplete="tel"
                        placeholder="+919876543210"
                        value={phone}
                        onChange={(event) => setPhone(event.target.value)}
                        error={errors.phone}
                        disabled={!available}
                        hint="Include your country code. We send a 6-digit code to this number."
                      />
                      <div>
                        <label className="flex items-start gap-3">
                          <input
                            type="checkbox"
                            className="mt-1 h-4 w-4"
                            checked={consent}
                            disabled={!available}
                            onChange={(event) => setConsent(event.target.checked)}
                            aria-describedby={errors.consent ? "wa-consent-error" : undefined}
                          />
                          <span className="text-sm text-ink2">
                            I agree to receive LawSchool notifications on WhatsApp at this number. I can change my choices or reply STOP at any time.
                          </span>
                        </label>
                        {errors.consent && (
                          <p id="wa-consent-error" role="alert" className="mt-1 text-[13px] text-bad">
                            {errors.consent}
                          </p>
                        )}
                      </div>
                      <Button type="submit" loading={busy} disabled={!available}>
                        Send verification code
                      </Button>
                    </form>
                  ) : (
                    <form onSubmit={confirmCode} noValidate className="space-y-4">
                      <TextField
                        id="wa-code"
                        label="Verification code"
                        inputMode="numeric"
                        autoComplete="one-time-code"
                        maxLength={6}
                        value={code}
                        onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))}
                        error={errors.code}
                        hint="The code expires in 10 minutes."
                      />
                      <div className="flex flex-wrap gap-3">
                        <Button type="submit" loading={busy}>Verify</Button>
                        <Button variant="ghost" onClick={() => { setStep("enter"); setCode(""); setErrors({}); }}>
                          Use a different number
                        </Button>
                      </div>
                    </form>
                  )}
                </div>
              )}
            </Panel>

            <Panel className="p-5">
              <h2 className="h4">Recent messages</h2>
              <div className="rule my-4" />
              {history.loading ? (
                <Skeleton className="h-16 w-full" />
              ) : history.error ? (
                <ErrorState error={history.error} onRetry={history.refetch} />
              ) : (history.data?.results || []).length === 0 ? (
                <p className="small">No WhatsApp messages yet.</p>
              ) : (
                <ul className="divide-y divide-line">
                  {history.data.results.map((row) => (
                    <li key={row.id} className="flex items-center justify-between gap-3 py-2 text-sm">
                      <span className="text-ink2">
                        {row.template_name.replaceAll("_", " ")} · {formatDateTime(row.created_at)}
                      </span>
                      <Badge tone={STATUS_TONE[row.status] || "gold"}>{row.status_label}</Badge>
                    </li>
                  ))}
                </ul>
              )}
              <p className="cap mt-3">
                “Accepted by WhatsApp” means we handed the message over; it shows as “Delivered” only once WhatsApp confirms it reached your phone.
              </p>
            </Panel>
          </div>

          <Panel className="h-fit p-5">
            <h2 className="h4">What you receive</h2>
            <div className="rule my-4" />
            <fieldset disabled={busy || !data.is_verified} className="space-y-4">
              <legend className="sr-only">Notification categories</legend>
              {CATEGORIES.map(([field, label, hint]) => (
                <label key={field} className="flex items-start gap-3">
                  <input
                    type="checkbox"
                    className="mt-1 h-4 w-4"
                    checked={Boolean(data[field])}
                    onChange={(event) => update({ [field]: event.target.checked })}
                  />
                  <span>
                    <span className="block text-ink">{label}</span>
                    <span className="cap">{hint}</span>
                  </span>
                </label>
              ))}
              <TextField
                id="wa-pause"
                label="Pause study reminders until"
                type="date"
                value={data.study_reminders_paused_until || ""}
                onChange={(event) => update({ study_reminders_paused_until: event.target.value || null })}
              />
            </fieldset>
            {!data.is_verified && (
              <p className="small mt-4">Verify your number to choose what you receive.</p>
            )}
          </Panel>
        </div>
      )}

      <p className="small mt-8">
        <Link to="/notifications" className="underline">View your in-app notifications</Link>
      </p>
    </div>
  );
}
