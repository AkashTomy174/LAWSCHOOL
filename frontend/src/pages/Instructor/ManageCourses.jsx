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
import quizService from "../../services/quizService";
import { fieldErrorsFrom } from "../../utils/validation";

/**
 * Section and lesson authoring for one of the caller's own courses.
 *
 * Instructors can add a course (it is theirs and starts as a draft until an admin
 * publishes it), then build out its sections and lessons. Ownership is enforced
 * by the API -- the course picker is only a convenience, not the access control.
 */
function NewCourseForm({ onCreated }) {
  const { pushToast } = useUI();
  const [form, setForm] = useState({ title: "", description: "", price: "0" });
  const [errors, setErrors] = useState({});
  const [busy, setBusy] = useState(false);
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  async function submit(e) {
    e.preventDefault();
    setErrors({});
    setBusy(true);
    try {
      const created = await courseService.create(form);
      pushToast({ message: "Course created as a draft", tone: "success" });
      setForm({ title: "", description: "", price: "0" });
      onCreated(created.slug);
    } catch (caught) {
      setErrors(fieldErrorsFrom(caught));
      if (!Object.keys(fieldErrorsFrom(caught)).length) {
        pushToast({ message: caught?.message || "Could not create course", tone: "error" });
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel className="mb-6 p-5">
      <h2 className="h4 mb-4">New course</h2>
      <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
        <TextField id="nc-title" label="Title" required value={form.title} onChange={set("title")} error={errors.title} />
        <TextField id="nc-price" label="Price (INR)" type="number" min="0" step="0.01" value={form.price} onChange={set("price")} error={errors.price} />
        <TextField
          id="nc-desc"
          label="Description"
          as="textarea"
          rows={3}
          required
          className="sm:col-span-2"
          value={form.description}
          onChange={set("description")}
          error={errors.description}
        />
        <div className="sm:col-span-2">
          <Button type="submit" loading={busy}>Create course</Button>
        </div>
      </form>
    </Panel>
  );
}

export default function ManageCourses() {
  const { pushToast } = useUI();
  const courses = useAsync(
    async () => (await courseService.list({ scope: "mine", page_size: 100 })).results,
    [],
  );
  const [slug, setSlug] = useState("");
  const selected = slug || courses.data?.[0]?.slug || "";

  function created(newSlug) {
    setSlug(newSlug);
    courses.refetch({ silent: true });
  }

  const tree = useAsync(async () => {
    if (!selected) return { sections: [], lessons: [], quizzes: [] };
    const [sections, lessons, quizzes] = await Promise.all([
      courseService.listSections(selected),
      courseService.listLessons(selected),
      quizService.list({ course: selected }),
    ]);
    const ids = new Set(sections.map((s) => s.id));
    return { sections, lessons: lessons.filter((l) => ids.has(l.section)), quizzes };
  }, [selected]);

  const [newSection, setNewSection] = useState("");
  const [newLesson, setNewLesson] = useState({});
  const [newQuiz, setNewQuiz] = useState({});
  const [formError, setFormError] = useState("");

  async function run(fn, message) {
    setFormError("");
    try {
      await fn();
      if (message) pushToast({ message, tone: "success" });
      tree.refetch({ silent: true });
    } catch (caught) {
      const fields = Object.values(fieldErrorsFrom(caught));
      setFormError(fields[0] || caught?.message || "That change could not be saved.");
    }
  }

  const course = courses.data?.find((c) => c.slug === selected);
  const sections = tree.data?.sections || [];
  const lessons = tree.data?.lessons || [];
  const quizzes = tree.data?.quizzes || [];
  const nextOrder = (items) => items.reduce((max, i) => Math.max(max, i.ordering), 0) + 1;

  return (
    <div className="wrap pb-24 pt-12 lg:pt-14">
      <PageHeader
        title="Manage courses"
        description="Add and arrange sections and lessons in your courses, and choose what students can see."
        breadcrumbs={[{ label: "Teaching", to: "/instructor" }, { label: "Manage courses" }]}
      />

      <NewCourseForm onCreated={created} />

      {courses.loading ? (
        <Skeleton className="h-40 w-full" />
      ) : courses.error ? (
        <ErrorState error={courses.error} onRetry={courses.refetch} />
      ) : !courses.data?.length ? (
        <Panel>
          <EmptyState
            title="No courses to manage"
            description="Create your first course above, then build it out here."
          />
        </Panel>
      ) : (
        <>
          <div className="mb-6 max-w-md">
            <label htmlFor="mc-course" className="label">Course</label>
            <select id="mc-course" className="input" value={selected} onChange={(e) => setSlug(e.target.value)}>
              {courses.data.map((c) => (
                <option key={c.id} value={c.slug}>
                  {c.title} ({c.status})
                </option>
              ))}
            </select>
          </div>

          {formError && (
            <p role="alert" className="mb-4 rounded-lg bg-sunken px-4 py-3 text-sm text-bad">{formError}</p>
          )}

          {tree.loading ? (
            <Skeleton className="h-48 w-full" />
          ) : tree.error ? (
            <ErrorState error={tree.error} onRetry={tree.refetch} />
          ) : (
            <div className="space-y-6">
              {sections.length === 0 && (
                <Panel>
                  <EmptyState title="No sections yet" description={`Add the first section of ${course?.title}.`} />
                </Panel>
              )}

              {sections.map((section) => {
                const own = lessons.filter((l) => l.section === section.id);
                return (
                  <Panel key={section.id} className="p-5">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <h2 className="h4">
                        {section.ordering}. {section.title}
                      </h2>
                      <div className="flex items-center gap-3 text-xs">
                        <Badge tone={section.is_published ? "success" : "muted"}>
                          {section.is_published ? "Visible" : "Hidden"}
                        </Badge>
                        <button
                          type="button"
                          className="text-gold-ink hover:underline"
                          onClick={() =>
                            run(() => courseService.updateSection(section.id, { is_published: !section.is_published }))
                          }
                        >
                          {section.is_published ? "Hide" : "Show"}
                        </button>
                        <button
                          type="button"
                          className="text-bad hover:underline"
                          onClick={() => {
                            if (window.confirm(`Delete section "${section.title}" and its lessons?`)) {
                              run(() => courseService.deleteSection(section.id), "Section deleted.");
                            }
                          }}
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                    <div className="rule my-4" />

                    {own.length === 0 ? (
                      <p className="small">No lessons in this section.</p>
                    ) : (
                      <ul className="divide-y divide-line">
                        {own.map((lesson) => (
                          <li key={lesson.id} className="flex flex-wrap items-center justify-between gap-3 py-2.5">
                            <span className="text-sm text-ink">
                              {lesson.ordering}. {lesson.title}
                              {lesson.is_preview && <Badge tone="gold" className="ml-2">Preview</Badge>}
                            </span>
                            <span className="flex items-center gap-3 text-xs">
                              <Badge tone={lesson.status === "published" ? "success" : "muted"}>{lesson.status}</Badge>
                              <button
                                type="button"
                                className="text-gold-ink hover:underline"
                                onClick={() =>
                                  run(() =>
                                    courseService.updateLesson(lesson.id, {
                                      status: lesson.status === "published" ? "draft" : "published",
                                    }),
                                  )
                                }
                              >
                                {lesson.status === "published" ? "Unpublish" : "Publish"}
                              </button>
                              <button
                                type="button"
                                className="text-bad hover:underline"
                                onClick={() => {
                                  if (window.confirm(`Delete lesson "${lesson.title}"?`)) {
                                    run(() => courseService.deleteLesson(lesson.id), "Lesson deleted.");
                                  }
                                }}
                              >
                                Delete
                              </button>
                            </span>
                          </li>
                        ))}
                      </ul>
                    )}

                    <form
                      className="mt-4 flex flex-wrap items-end gap-3"
                      onSubmit={(event) => {
                        event.preventDefault();
                        const title = (newLesson[section.id] || "").trim();
                        const quiz = newQuiz[section.id];
                        if (!title || !quiz) return;
                        run(async () => {
                          await courseService.createLesson({
                            section: section.id,
                            title,
                            quiz,
                            ordering: nextOrder(own),
                            status: "draft",
                          });
                          setNewLesson((current) => ({ ...current, [section.id]: "" }));
                        }, "Lesson added as a draft.");
                      }}
                    >
                      <TextField
                        id={`lesson-${section.id}`}
                        label="New lesson"
                        className="min-w-[14rem] flex-1"
                        value={newLesson[section.id] || ""}
                        onChange={(e) => setNewLesson((c) => ({ ...c, [section.id]: e.target.value }))}
                      />
                      <div>
                        <label htmlFor={`quiz-${section.id}`} className="label">Quiz</label>
                        <select
                          id={`quiz-${section.id}`}
                          className="input"
                          value={newQuiz[section.id] || ""}
                          onChange={(e) => setNewQuiz((c) => ({ ...c, [section.id]: e.target.value }))}
                        >
                          <option value="">Select a quiz…</option>
                          {quizzes.map((q) => (
                            <option key={q.id} value={q.id}>{q.title}</option>
                          ))}
                        </select>
                      </div>
                      <Button type="submit" variant="ghost" disabled={!newQuiz[section.id] || !(newLesson[section.id] || "").trim()}>
                        Add lesson
                      </Button>
                      {quizzes.length === 0 && (
                        <p className="cap w-full">
                          A lesson needs a quiz. Create one under Quizzes first, then add its video from the Videos tab.
                        </p>
                      )}
                    </form>
                  </Panel>
                );
              })}

              <Panel className="p-5">
                <form
                  className="flex flex-wrap items-end gap-3"
                  onSubmit={(event) => {
                    event.preventDefault();
                    const title = newSection.trim();
                    if (!title) return;
                    run(async () => {
                      await courseService.createSection({
                        course: course.id,
                        title,
                        ordering: nextOrder(sections),
                        is_published: false,
                      });
                      setNewSection("");
                    }, "Section added (hidden until you show it).");
                  }}
                >
                  <TextField
                    id="new-section"
                    label="New section"
                    className="min-w-[14rem] flex-1"
                    value={newSection}
                    onChange={(e) => setNewSection(e.target.value)}
                  />
                  <Button type="submit">Add section</Button>
                </form>
              </Panel>
            </div>
          )}
        </>
      )}
    </div>
  );
}
