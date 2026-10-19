import { useState } from "react";

import { PageHeader } from "../../components/Layout";
import {
  Badge,
  Button,
  EmptyState,
  ErrorState,
  Panel,
  Skeleton,
  TextField,
} from "../../components/ui";
import { useUI } from "../../context/UIContext";
import useAsync from "../../hooks/useAsync";
import courseService from "../../services/courseService";
import liveService from "../../services/liveService";
import { formatDateTime } from "../../utils/format";
import { fieldErrorsFrom } from "../../utils/validation";

const EMPTY = {
  course: "",
  title: "",
  scheduled_start: "",
  duration_minutes: 60,
  meeting_provider: "zoom",
  meeting_url: "",
  is_published: true,
};

/**
 * Live classes for the caller's own courses. The API lists and accepts only
 * courses the caller owns (admins: all), so nothing is filtered here.
 */
export default function LiveClasses() {
  const { pushToast } = useUI();
  const classes = useAsync(() => liveService.list(), []);
  const courses = useAsync(
    async () => (await courseService.list({ scope: "mine", page_size: 100 })).results,
    [],
  );
  const [form, setForm] = useState(EMPTY);
  const [errors, setErrors] = useState({});
  const [saving, setSaving] = useState(false);

  const set = (field) => (event) =>
    setForm((current) => ({ ...current, [field]: event.target.value }));

  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    setErrors({});
    try {
      await liveService.create({
        ...form,
        duration_minutes: Number(form.duration_minutes),
        // datetime-local has no zone; the browser's local time is what was typed.
        scheduled_start: new Date(form.scheduled_start).toISOString(),
      });
      setForm(EMPTY);
      pushToast({ message: "Live class scheduled.", tone: "success" });
      classes.refetch({ silent: true });
    } catch (caught) {
      setErrors({ ...fieldErrorsFrom(caught), _: caught?.message });
    } finally {
      setSaving(false);
    }
  }

  async function act(fn, message) {
    try {
      await fn();
      pushToast({ message, tone: "success" });
      classes.refetch({ silent: true });
    } catch (caught) {
      pushToast({ message: caught?.message || "Action failed.", tone: "error" });
    }
  }

  const rows = classes.data || [];
  const myCourses = courses.data || [];
  const titleOf = (id) => myCourses.find((c) => c.id === id)?.title || "—";

  return (
    <div className="wrap pb-24 pt-12 lg:pt-14">
      <PageHeader
        title="Live classes"
        description="Schedule Zoom or Google Meet sessions for your courses. Students get the join link only if their plan covers the course."
        breadcrumbs={[{ label: "Teaching", to: "/instructor" }, { label: "Live classes" }]}
      />

      <Panel className="mb-8 p-5">
        <h2 className="h4">Schedule a class</h2>
        <div className="rule my-4" />
        {courses.loading ? (
          <Skeleton className="h-24 w-full" />
        ) : myCourses.length === 0 ? (
          <p className="small">You have no courses yet, so there is nothing to schedule.</p>
        ) : (
          <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2" noValidate>
            <div>
              <label htmlFor="lc-course" className="label">Course</label>
              <select id="lc-course" className="input" required value={form.course} onChange={set("course")}>
                <option value="">Select a course…</option>
                {myCourses.map((c) => (
                  <option key={c.id} value={c.id}>{c.title}</option>
                ))}
              </select>
              {errors.course && <p role="alert" className="mt-1 text-[13px] text-bad">{errors.course}</p>}
            </div>
            <TextField id="lc-title" label="Title" required value={form.title} onChange={set("title")} error={errors.title} />
            <TextField id="lc-start" label="Starts" type="datetime-local" required value={form.scheduled_start} onChange={set("scheduled_start")} error={errors.scheduled_start} />
            <TextField id="lc-dur" label="Duration (minutes)" type="number" min="5" value={form.duration_minutes} onChange={set("duration_minutes")} error={errors.duration_minutes} />
            <div>
              <label htmlFor="lc-provider" className="label">Provider</label>
              <select id="lc-provider" className="input" value={form.meeting_provider} onChange={set("meeting_provider")}>
                <option value="zoom">Zoom</option>
                <option value="google_meet">Google Meet</option>
                <option value="other">Other</option>
              </select>
            </div>
            <TextField id="lc-url" label="Meeting link" type="url" required value={form.meeting_url} onChange={set("meeting_url")} error={errors.meeting_url} />
            <div className="sm:col-span-2 flex items-center gap-4">
              <Button type="submit" loading={saving} disabled={!form.course || !form.title || !form.scheduled_start || !form.meeting_url}>
                Schedule
              </Button>
              {errors._ && !Object.keys(errors).some((k) => k !== "_") && (
                <p role="alert" className="text-[13px] text-bad">{errors._}</p>
              )}
            </div>
          </form>
        )}
      </Panel>

      {classes.loading ? (
        <Skeleton className="h-40 w-full" />
      ) : classes.error ? (
        <ErrorState error={classes.error} onRetry={classes.refetch} />
      ) : rows.length === 0 ? (
        <Panel>
          <EmptyState title="No live classes yet" description="Classes you schedule appear here." />
        </Panel>
      ) : (
        <Panel className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-sunken text-[13px] text-ink3 [&_th]:font-medium">
              <tr>
                <th scope="col" className="px-4 py-3">Class</th>
                <th scope="col" className="px-4 py-3">Course</th>
                <th scope="col" className="px-4 py-3">When</th>
                <th scope="col" className="px-4 py-3">Status</th>
                <th scope="col" className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {rows.map((row) => (
                <tr key={row.id}>
                  <td className="px-4 py-3 text-ink">{row.title}</td>
                  <td className="px-4 py-3 text-ink3">{titleOf(row.course)}</td>
                  <td className="px-4 py-3 text-ink3">
                    {formatDateTime(row.scheduled_start)} · {row.duration_minutes} min
                  </td>
                  <td className="px-4 py-3">
                    <Badge tone={row.is_published ? "success" : "muted"}>
                      {row.is_published ? "Published" : "Draft"}
                    </Badge>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-3 text-xs">
                      <button
                        type="button"
                        className="text-gold-ink hover:underline"
                        onClick={() =>
                          act(
                            () => liveService.update(row.id, { is_published: !row.is_published }),
                            row.is_published ? "Moved to draft." : "Published.",
                          )
                        }
                      >
                        {row.is_published ? "Unpublish" : "Publish"}
                      </button>
                      <button
                        type="button"
                        className="text-bad hover:underline"
                        onClick={() => {
                          if (window.confirm(`Delete "${row.title}"?`)) {
                            act(() => liveService.remove(row.id), "Live class deleted.");
                          }
                        }}
                      >
                        Delete
                      </button>
                    </div>
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
