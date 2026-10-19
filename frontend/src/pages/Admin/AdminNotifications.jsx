import { useState } from "react";

import { PageHeader } from "../../components/Layout";
import {
  Badge,
  Button,
  Callout,
  EmptyState,
  ErrorState,
  Panel,
  Skeleton,
  TextField,
} from "../../components/ui";
import { useUI } from "../../context/UIContext";
import useAsync from "../../hooks/useAsync";
import notificationService from "../../services/notificationService";
import { formatDateTime } from "../../utils/format";

const TABS = [
  ["overview", "Overview"],
  ["log", "Delivery log"],
  ["templates", "Templates"],
  ["settings", "Settings"],
  ["announce", "Announcements"],
];

const STATUS_TONE = { delivered: "success", read: "success", failed: "danger", cancelled: "muted", suppressed: "muted" };
const REASONS = {
  rate_limited: "WhatsApp rate limit",
  auth_error: "Access token rejected",
  invalid_recipient: "Number not on WhatsApp",
  template_rejected: "Template not approved",
  window_closed: "Outside the 24-hour window",
  server_error: "WhatsApp server error",
  network_error: "Network error",
  stuck_processing: "Send did not complete",
  bad_variables: "Template values missing",
};
const reason = (code) => REASONS[code] || code.replaceAll("_", " ");
const APPROVAL = [
  ["unknown", "Not submitted"],
  ["pending", "Pending Meta review"],
  ["approved", "Approved"],
  ["rejected", "Rejected"],
];

/**
 * WhatsApp operations for administrators. The API re-checks the admin role on every
 * call; this page only presents what it returns. Numbers arrive pre-masked.
 */
export default function AdminNotifications() {
  const [tab, setTab] = useState("overview");

  return (
    <div className="wrap pb-24 pt-12 lg:pt-14">
      <PageHeader
        title="WhatsApp notifications"
        description="Delivery health, templates, reminder settings and announcements."
        breadcrumbs={[{ label: "Admin", to: "/admin" }, { label: "WhatsApp" }]}
      />
      <div role="tablist" aria-label="WhatsApp admin sections" className="mb-6 flex flex-wrap gap-2">
        {TABS.map(([id, label]) => (
          <button
            key={id}
            role="tab"
            type="button"
            id={`wa-tab-${id}`}
            aria-selected={tab === id}
            aria-controls="wa-panel"
            onClick={() => setTab(id)}
            className={`btn ${tab === id ? "btn-primary" : "btn-ghost"}`}
          >
            {label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id="wa-panel" aria-labelledby={`wa-tab-${tab}`}>
        {tab === "overview" && <Overview />}
        {tab === "log" && <DeliveryLog />}
        {tab === "templates" && <Templates />}
        {tab === "settings" && <Settings />}
        {tab === "announce" && <Announcements />}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ Overview */
function Overview() {
  const overview = useAsync(() => notificationService.adminOverview({ days: 30 }), []);
  if (overview.loading) return <Skeleton className="h-40 w-full" />;
  if (overview.error) return <ErrorState error={overview.error} onRetry={overview.refetch} />;
  const o = overview.data;
  const always = ["accepted", "delivered", "failed"];
  const statuses = ["pending", "scheduled", "processing", "accepted", "sent", "delivered", "read", "failed", "cancelled", "suppressed"]
    .filter((s) => always.includes(s) || o.by_status[s]);
  return (
    <div className="space-y-6">
      {!o.enabled && (
        <Callout tone="warning" title="WhatsApp is switched off">
          Nothing is being sent. Set WHATSAPP_ENABLED once the Meta account, templates and webhook are ready.
        </Callout>
      )}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {statuses.map((status) => (
          <Panel key={status} className="p-4">
            <p className="small capitalize">{status}</p>
            <p className="h3">{o.by_status[status] || 0}</p>
          </Panel>
        ))}
      </div>
      <Callout>{o.note}</Callout>
      {o.estimated_cost != null && (
        <Panel className="p-5">
          <h2 className="h4">Estimated spend (last {o.days} days)</h2>
          <p className="h3 mt-2">{o.estimated_cost}</p>
          <p className="cap mt-1">{o.estimated_cost_note}</p>
        </Panel>
      )}
      <Panel className="p-5">
        <h2 className="h4">By template</h2>
        {o.by_template.length === 0 ? (
          <p className="small mt-2">No messages yet.</p>
        ) : (
          <ul className="mt-3 divide-y divide-line text-sm">
            {o.by_template.map((row) => (
              <li key={row.template_name} className="flex justify-between py-2">
                <span>{row.template_name}</span>
                <span className="text-ink3">{row.n}</span>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}

/* ------------------------------------------------------------- Delivery log */
function DeliveryLog() {
  const { pushToast } = useUI();
  const [filters, setFilters] = useState({ status: "", recipient: "", date_from: "", date_to: "" });
  const [page, setPage] = useState(1);
  const params = Object.fromEntries(Object.entries({ ...filters, page }).filter(([, v]) => v));
  const log = useAsync(() => notificationService.adminHistory(params), [JSON.stringify(params)]);

  const set = (field) => (event) => {
    setPage(1);
    setFilters((f) => ({ ...f, [field]: event.target.value }));
  };

  async function retry(row) {
    try {
      await notificationService.adminRetry(row.id);
      pushToast({ message: "Queued for retry.", tone: "success" });
      log.refetch({ silent: true });
    } catch (caught) {
      pushToast({ message: caught?.message || "Retry failed.", tone: "error" });
    }
  }

  const rows = log.data?.results || [];
  return (
    <div className="space-y-4">
      <Panel className="grid gap-4 p-4 sm:grid-cols-4">
        <div>
          <label htmlFor="f-status" className="label">Status</label>
          <select id="f-status" className="input" value={filters.status} onChange={set("status")}>
            <option value="">All</option>
            {["pending", "accepted", "sent", "delivered", "read", "failed", "cancelled", "suppressed"].map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
        <TextField id="f-recipient" label="Recipient" value={filters.recipient} onChange={set("recipient")} placeholder="Name or email" />
        <TextField id="f-from" label="From" type="date" value={filters.date_from} onChange={set("date_from")} />
        <TextField id="f-to" label="To" type="date" value={filters.date_to} onChange={set("date_to")} />
      </Panel>

      {log.loading ? (
        <Skeleton className="h-48 w-full" />
      ) : log.error ? (
        <ErrorState error={log.error} onRetry={log.refetch} />
      ) : rows.length === 0 ? (
        <Panel><EmptyState title="No messages match" description="Try widening the filters." /></Panel>
      ) : (
        <Panel className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-sunken text-[13px] text-ink3 [&_th]:font-medium">
              <tr>
                <th scope="col" className="px-4 py-3">When</th>
                <th scope="col" className="px-4 py-3">Recipient</th>
                <th scope="col" className="px-4 py-3">Template</th>
                <th scope="col" className="px-4 py-3">Status</th>
                <th scope="col" className="px-4 py-3">Detail</th>
                <th scope="col" className="px-4 py-3"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {rows.map((row) => (
                <tr key={row.id}>
                  <td className="px-4 py-3 text-ink3">{formatDateTime(row.created_at)}</td>
                  <td className="px-4 py-3 text-ink">
                    {row.recipient}
                    <span className="cap block">{row.recipient_number}</span>
                  </td>
                  <td className="px-4 py-3 text-ink3">{row.template_name}</td>
                  <td className="px-4 py-3"><Badge tone={STATUS_TONE[row.status] || "gold"}>{row.status_label}</Badge></td>
                  <td className="px-4 py-3 text-ink3">{row.last_error_code ? reason(row.last_error_code) : row.delivered_at ? "Delivered" : "—"}</td>
                  <td className="px-4 py-3">
                    {row.status === "failed" && (
                      <button type="button" className="text-gold-ink hover:underline" onClick={() => retry(row)}>
                        Retry
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      )}

      {log.data && log.data.num_pages > 1 && (
        <div className="flex items-center gap-3">
          <Button variant="ghost" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</Button>
          <span className="small">Page {log.data.page} of {log.data.num_pages}</span>
          <Button variant="ghost" disabled={page >= log.data.num_pages} onClick={() => setPage((p) => p + 1)}>Next</Button>
        </div>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- Templates */
function Templates() {
  const { pushToast } = useUI();
  const templates = useAsync(() => notificationService.adminTemplates(), []);

  async function save(row, patch) {
    try {
      const updated = await notificationService.adminUpdateTemplate(row.id, patch);
      templates.setData((list) => list.map((t) => (t.id === row.id ? updated : t)));
      pushToast({ message: "Template updated.", tone: "success" });
    } catch (caught) {
      pushToast({ message: caught?.message || "Could not update.", tone: "error" });
    }
  }

  if (templates.loading) return <Skeleton className="h-48 w-full" />;
  if (templates.error) return <ErrorState error={templates.error} onRetry={templates.refetch} />;
  const live = templates.data.filter((t) => t.has_trigger);
  const idle = templates.data.filter((t) => !t.has_trigger);
  return (
    <div className="space-y-4">
      <Callout title="Approval is recorded, not assumed">
        Submit each template to Meta, then set its status here once Meta has approved it. Unapproved templates are never sent.
      </Callout>
      <Panel className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="bg-sunken text-[13px] text-ink3 [&_th]:font-medium">
            <tr>
              <th scope="col" className="px-4 py-3">Template</th>
              <th scope="col" className="px-4 py-3">Meta category</th>
              <th scope="col" className="px-4 py-3">Variables</th>
              <th scope="col" className="px-4 py-3">Approval</th>
              <th scope="col" className="px-4 py-3">Active</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {live.map((row) => (
              <tr key={row.id}>
                <td className="px-4 py-3 text-ink">
                  {row.internal_name}
                  <span className="cap block">{row.body_preview}</span>
                </td>
                <td className="px-4 py-3 text-ink3">{row.meta_category}</td>
                <td className="px-4 py-3 text-ink3">{row.variable_schema.join(", ")}</td>
                <td className="px-4 py-3">
                  <label className="sr-only" htmlFor={`approval-${row.id}`}>Approval for {row.internal_name}</label>
                  <select
                    id={`approval-${row.id}`}
                    className="input"
                    value={row.approval_status}
                    onChange={(event) => save(row, { approval_status: event.target.value })}
                  >
                    {APPROVAL.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                  </select>
                </td>
                <td className="px-4 py-3">
                  <input
                    type="checkbox"
                    aria-label={`${row.internal_name} active`}
                    checked={row.active}
                    onChange={(event) => save(row, { active: event.target.checked })}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
      {idle.length > 0 && (
        <Callout title="Not triggered yet">
          Nothing in the LMS sends these, so there is no need to submit them to Meta yet: {idle.map((t) => t.internal_name).join(", ")}.
        </Callout>
      )}
    </div>
  );
}

/* ----------------------------------------------------------------- Settings */
function Settings() {
  const { pushToast } = useUI();
  const settings = useAsync(() => notificationService.adminSettings(), []);
  const [form, setForm] = useState(null);
  const [errors, setErrors] = useState({});
  const [saving, setSaving] = useState(false);

  const current = form || settings.data;
  if (settings.loading) return <Skeleton className="h-48 w-full" />;
  if (settings.error) return <ErrorState error={settings.error} onRetry={settings.refetch} />;

  const set = (field, value) => setForm({ ...current, [field]: value });

  async function submit(event) {
    event.preventDefault();
    const offsets = String(current.offsetsText ?? current.reminder_offsets_minutes.join(", "))
      .split(",").map((s) => s.trim()).filter(Boolean).map(Number);
    if (offsets.some((n) => !Number.isInteger(n) || n < 0 || n > 10080) || offsets.length > 6) {
      return setErrors({ offsets: "Enter up to 6 whole minute values between 0 and 10080, e.g. 1440, 30." });
    }
    setSaving(true);
    setErrors({});
    try {
      const saved = await notificationService.adminUpdateSettings({
        reminder_offsets_minutes: offsets,
        schedule_notifications_enabled: current.schedule_notifications_enabled,
        weekly_summary_enabled: current.weekly_summary_enabled,
        inactivity_reminders_enabled: current.inactivity_reminders_enabled,
        inactivity_days: Number(current.inactivity_days),
        inactivity_max_reminders: Number(current.inactivity_max_reminders),
        send_rate_per_minute: Number(current.send_rate_per_minute),
      });
      settings.setData(saved);
      setForm(null);
      pushToast({ message: "Settings saved.", tone: "success" });
    } catch (caught) {
      setErrors({ form: caught?.message || "Could not save." });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Panel className="p-5">
      <form onSubmit={submit} noValidate className="grid gap-4 sm:grid-cols-2">
        {errors.form && <div className="sm:col-span-2"><ErrorState error={{ message: errors.form }} /></div>}
        <TextField
          id="s-offsets"
          label="Class reminders (minutes before start)"
          value={current.offsetsText ?? current.reminder_offsets_minutes.join(", ")}
          onChange={(event) => set("offsetsText", event.target.value)}
          error={errors.offsets}
          hint="1440 = 24 hours before, 30 = 30 minutes before, 0 = at start."
        />
        <TextField id="s-rate" label="Max sends per minute" type="number" min="1" value={current.send_rate_per_minute} onChange={(event) => set("send_rate_per_minute", event.target.value)} />
        <TextField id="s-days" label="Inactivity threshold (days)" type="number" min="2" max="90" value={current.inactivity_days} onChange={(event) => set("inactivity_days", event.target.value)} />
        <TextField id="s-max" label="Max inactivity reminders" type="number" min="1" max="5" value={current.inactivity_max_reminders} onChange={(event) => set("inactivity_max_reminders", event.target.value)} />
        {[
          ["schedule_notifications_enabled", "Class reminders and schedule notices"],
          ["weekly_summary_enabled", "Weekly progress summaries"],
          ["inactivity_reminders_enabled", "Inactivity reminders"],
        ].map(([field, label]) => (
          <label key={field} className="flex items-center gap-3 sm:col-span-2">
            <input type="checkbox" className="h-4 w-4" checked={current[field]} onChange={(event) => set(field, event.target.checked)} />
            <span className="text-ink">{label}</span>
          </label>
        ))}
        <div className="sm:col-span-2"><Button type="submit" loading={saving}>Save settings</Button></div>
      </form>
    </Panel>
  );
}

/* ------------------------------------------------------------ Announcements */
function Announcements() {
  const { pushToast } = useUI();
  const [form, setForm] = useState({ title: "", text: "", course: "" });
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const set = (field) => (event) => {
    setPreview(null);
    setForm((f) => ({ ...f, [field]: event.target.value }));
  };
  const valid = form.title.trim() && form.text.trim();

  async function check() {
    setBusy(true);
    setError(null);
    try {
      setPreview(await notificationService.adminAnnouncementPreview(form.course ? { course: form.course } : {}));
    } catch (caught) {
      setError(caught?.message);
    } finally {
      setBusy(false);
    }
  }

  async function send() {
    if (!window.confirm(`Send this announcement to ${preview.recipients} student(s)?`)) return;
    setBusy(true);
    setError(null);
    try {
      await notificationService.adminAnnounce({ ...form, confirm_recipient_count: preview.recipients });
      pushToast({ message: "Announcement queued.", tone: "success" });
      setForm({ title: "", text: "", course: "" });
      setPreview(null);
    } catch (caught) {
      setError(caught?.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel className="space-y-4 p-5">
      <p className="small">
        Only students who verified a number, opted in and kept announcements on are included. Check the recipient count before sending.
      </p>
      {error && <ErrorState error={{ message: error }} />}
      <TextField id="a-title" label="Title" maxLength={60} value={form.title} onChange={set("title")} />
      <TextField id="a-text" label="Message" as="textarea" rows={3} maxLength={300} value={form.text} onChange={set("text")} hint={`${form.text.length}/300 characters`} />
      <TextField id="a-course" label="Course slug (optional)" value={form.course} onChange={set("course")} hint="Leave blank to reach every consenting student." />
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="ghost" onClick={check} loading={busy} disabled={!valid}>Preview recipients</Button>
        {preview && (
          <>
            <span className="text-ink" role="status">{preview.recipients} recipient(s)</span>
            <Button onClick={send} loading={busy} disabled={preview.recipients === 0 || preview.recipients > preview.cap}>
              Send to {preview.recipients}
            </Button>
          </>
        )}
      </div>
    </Panel>
  );
}
