import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { PageHeader } from "../../components/Layout";
import {
  Badge,
  Button,
  ErrorState,
  Panel,
  Skeleton,
  TextField,
} from "../../components/ui";
import { useAuth } from "../../context/AuthContext";
import { useUI } from "../../context/UIContext";
import useAsync from "../../hooks/useAsync";
import courseService from "../../services/courseService";
import quizService from "../../services/quizService";

/**
 * Build a quiz from the shared question bank: any mix of hand-picked questions
 * (in every attempt) and random draws per subject (a fresh, non-repeating set
 * each attempt -- the server does the rotation).
 */
const EMPTY_OPTIONS = ["", "", "", ""];

function NewQuiz({ base }) {
  const navigate = useNavigate();
  const { pushToast } = useUI();
  const courses = useAsync(
    async () => (await courseService.list({ scope: "mine", page_size: 100 })).results,
    [],
  );
  const [form, setForm] = useState({ course: "", title: "" });

  async function submit(e) {
    e.preventDefault();
    try {
      const quiz = await quizService.create(form);
      navigate(`${base}/${quiz.id}`);
    } catch (caught) {
      pushToast({ message: caught?.message || "Could not create quiz", tone: "error" });
    }
  }

  return (
    <Panel className="p-5">
      <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="nq-course" className="mb-1 block text-sm">Course</label>
          <select id="nq-course" className="input" required value={form.course}
            onChange={(e) => setForm({ ...form, course: e.target.value })}>
            <option value="">Select a course…</option>
            {(courses.data || []).map((c) => (
              <option key={c.id} value={c.id}>{c.title}</option>
            ))}
          </select>
        </div>
        <TextField id="nq-title" label="Title" required value={form.title}
          onChange={(e) => setForm({ ...form, title: e.target.value })} />
        <div className="sm:col-span-2"><Button type="submit">Create quiz</Button></div>
      </form>
    </Panel>
  );
}

function Settings({ quiz, onSaved }) {
  const { pushToast } = useUI();
  const [form, setForm] = useState({
    title: quiz.title,
    pass_percentage: quiz.pass_percentage,
    max_attempts: quiz.max_attempts,
    time_limit_minutes: quiz.time_limit_minutes,
    shuffle_questions: quiz.shuffle_questions,
    is_published: quiz.is_published,
  });
  const num = (key) => (e) => setForm({ ...form, [key]: Number(e.target.value) });

  async function save(e) {
    e.preventDefault();
    try {
      await quizService.update(quiz.id, form);
      pushToast({ message: "Quiz saved", tone: "success" });
      onSaved();
    } catch (caught) {
      pushToast({ message: caught?.message || "Could not save", tone: "error" });
    }
  }

  return (
    <Panel className="p-5">
      <h2 className="h4 mb-4">Settings</h2>
      <form onSubmit={save} className="grid gap-4 sm:grid-cols-4">
        <TextField id="qs-title" label="Title" className="sm:col-span-4" value={form.title}
          onChange={(e) => setForm({ ...form, title: e.target.value })} />
        <TextField id="qs-pass" label="Pass %" type="number" min="1" max="100"
          value={form.pass_percentage} onChange={num("pass_percentage")} />
        <TextField id="qs-attempts" label="Max attempts (0 = unlimited)" type="number" min="0"
          value={form.max_attempts} onChange={num("max_attempts")} />
        <TextField id="qs-time" label="Time limit, minutes (0 = none)" type="number" min="0"
          value={form.time_limit_minutes} onChange={num("time_limit_minutes")} />
        <div className="flex flex-col justify-end gap-2 text-sm">
          <label><input type="checkbox" checked={form.shuffle_questions}
            onChange={(e) => setForm({ ...form, shuffle_questions: e.target.checked })} /> Shuffle order</label>
          <label><input type="checkbox" checked={form.is_published}
            onChange={(e) => setForm({ ...form, is_published: e.target.checked })} /> Published</label>
        </div>
        <div className="sm:col-span-4"><Button type="submit">Save settings</Button></div>
      </form>
    </Panel>
  );
}

function RandomRules({ quiz, subjects, pool, reload }) {
  const { pushToast } = useUI();
  const rules = useAsync(() => quizService.rules(quiz.id), [quiz.id]);
  const [form, setForm] = useState({ subject: "", question_count: 10, marks_per_question: 1 });

  async function add(e) {
    e.preventDefault();
    try {
      await quizService.addRule({ ...form, quiz: quiz.id, ordering: (rules.data || []).length + 1 });
      rules.refetch();
      reload();
    } catch (caught) {
      pushToast({ message: caught?.message || "Could not add rule", tone: "error" });
    }
  }

  async function remove(id) {
    await quizService.removeRule(id);
    rules.refetch();
    reload();
  }

  const available = (name) => (pool?.rules || []).find((r) => r.subject === name)?.available;

  return (
    <Panel className="p-5">
      <h2 className="h4 mb-1">Random questions by subject</h2>
      <p className="mb-4 text-sm text-ink3">
        Each attempt draws a fresh set. A student never sees a question again until
        the subject&apos;s whole pool has been used.
      </p>
      <ul className="mb-4 divide-y divide-line text-sm">
        {(rules.data || []).map((r) => (
          <li key={r.id} className="flex items-center justify-between py-2">
            <span>
              {r.subject_name}: {r.question_count} × {r.marks_per_question} mark(s)
              <span className="ml-2 text-ink3">of {available(r.subject_name) ?? "?"} available</span>
            </span>
            <Button variant="ghost" onClick={() => remove(r.id)}>Remove</Button>
          </li>
        ))}
      </ul>
      <form onSubmit={add} className="flex flex-wrap items-end gap-3">
        <select aria-label="Subject" className="input" required value={form.subject}
          onChange={(e) => setForm({ ...form, subject: e.target.value })}>
          <option value="">Subject…</option>
          {subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        <TextField id="rr-count" label="Questions" type="number" min="1" value={form.question_count}
          onChange={(e) => setForm({ ...form, question_count: Number(e.target.value) })} />
        <TextField id="rr-marks" label="Marks each" type="number" min="1" value={form.marks_per_question}
          onChange={(e) => setForm({ ...form, marks_per_question: Number(e.target.value) })} />
        <Button type="submit">Add random rule</Button>
      </form>
    </Panel>
  );
}

function ManualPicks({ quiz, subjects, reload }) {
  const { pushToast } = useUI();
  const fixed = useAsync(() => quizService.fixedQuestions(quiz.id), [quiz.id]);
  const [filter, setFilter] = useState({ subject: "", search: "" });
  const bank = useAsync(
    async () => (await quizService.questions({ ...filter, page_size: 20 })).results,
    [filter.subject, filter.search],
  );
  const pinned = new Set((fixed.data || []).map((f) => f.question));

  async function pin(question) {
    try {
      await quizService.addFixedQuestion({
        quiz: quiz.id,
        question: question.id,
        marks: question.marks,
        ordering: (fixed.data || []).length + 1,
      });
      fixed.refetch();
      reload();
    } catch (caught) {
      pushToast({ message: caught?.message || "Could not add question", tone: "error" });
    }
  }

  async function unpin(id) {
    await quizService.removeFixedQuestion(id);
    fixed.refetch();
    reload();
  }

  return (
    <Panel className="p-5">
      <h2 className="h4 mb-1">Hand-picked questions</h2>
      <p className="mb-4 text-sm text-ink3">These appear in every attempt.</p>
      <ul className="mb-4 divide-y divide-line text-sm">
        {(fixed.data || []).map((f) => (
          <li key={f.id} className="flex items-center justify-between gap-3 py-2">
            <span className="line-clamp-2">{f.text} <Badge tone="muted">{f.marks} mark(s)</Badge></span>
            <Button variant="ghost" onClick={() => unpin(f.id)}>Remove</Button>
          </li>
        ))}
      </ul>

      <h3 className="mb-2 text-sm font-medium">Browse the question bank</h3>
      <div className="mb-3 flex flex-wrap gap-3">
        <select aria-label="Filter by subject" className="input" value={filter.subject}
          onChange={(e) => setFilter({ ...filter, subject: e.target.value })}>
          <option value="">All subjects</option>
          {subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        <input aria-label="Search questions" className="input" placeholder="Search text…"
          value={filter.search} onChange={(e) => setFilter({ ...filter, search: e.target.value })} />
      </div>
      {bank.loading ? <Skeleton className="h-24 w-full" /> : (
        <ul className="divide-y divide-line text-sm">
          {(bank.data || []).map((q) => (
            <li key={q.id} className="flex items-center justify-between gap-3 py-2">
              <span className="line-clamp-2">{q.text}</span>
              <Button variant="ghost" disabled={pinned.has(q.id)} onClick={() => pin(q)}>
                {pinned.has(q.id) ? "Added" : "Add"}
              </Button>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function NewQuestion({ subjects, onCreated }) {
  const { pushToast } = useUI();
  const [text, setText] = useState("");
  const [subject, setSubject] = useState("");
  const [options, setOptions] = useState(EMPTY_OPTIONS);
  const [correct, setCorrect] = useState(0);
  const [newSubject, setNewSubject] = useState("");

  async function addSubject() {
    if (!newSubject.trim()) return;
    const created = await quizService.createSubject({ name: newSubject.trim() });
    setNewSubject("");
    setSubject(created.id);
    onCreated();
  }

  async function submit(e) {
    e.preventDefault();
    const filled = options.map((t, i) => ({ t: t.trim(), i })).filter((o) => o.t);
    if (filled.length < 2 || !filled.some((o) => o.i === correct)) {
      pushToast({ message: "Add at least 2 options and mark one correct", tone: "error" });
      return;
    }
    try {
      const q = await quizService.createQuestion({ text, subjects: [subject] });
      for (const [n, o] of filled.entries()) {
        await quizService.createOption({
          question: q.id, text: o.t, is_correct: o.i === correct, ordering: n + 1,
        });
      }
      pushToast({ message: "Question added to the bank", tone: "success" });
      setText("");
      setOptions(EMPTY_OPTIONS);
      onCreated();
    } catch (caught) {
      pushToast({ message: caught?.message || "Could not add question", tone: "error" });
    }
  }

  return (
    <Panel className="p-5">
      <h2 className="h4 mb-4">Add a question to the bank</h2>
      <form onSubmit={submit} className="grid gap-3">
        <TextField id="nq-text" label="Question" as="textarea" rows={2} required value={text}
          onChange={(e) => setText(e.target.value)} />
        <div className="flex flex-wrap items-end gap-3">
          <select aria-label="Subject" className="input" required value={subject}
            onChange={(e) => setSubject(e.target.value)}>
            <option value="">Subject…</option>
            {subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <input aria-label="New subject name" className="input" placeholder="or new subject"
            value={newSubject} onChange={(e) => setNewSubject(e.target.value)} />
          <Button type="button" variant="ghost" onClick={addSubject}>Create subject</Button>
        </div>
        {options.map((value, i) => (
          <div key={i} className="flex items-center gap-2">
            <input type="radio" name="correct" aria-label={`Option ${i + 1} is correct`}
              checked={correct === i} onChange={() => setCorrect(i)} />
            <input aria-label={`Option ${i + 1}`} className="input flex-1" placeholder={`Option ${i + 1}`}
              value={value} onChange={(e) => setOptions(options.map((o, j) => (j === i ? e.target.value : o)))} />
          </div>
        ))}
        <div><Button type="submit">Add question</Button></div>
      </form>
    </Panel>
  );
}

export default function QuizBuilder() {
  const { id } = useParams();
  const { isAdmin } = useAuth();
  const base = isAdmin ? "/admin/quizzes" : "/instructor/quizzes";
  const isNew = id === "new";

  const quiz = useAsync(
    async () => (isNew ? null : (await quizService.list()).find((q) => q.id === id) || null),
    [id],
  );
  const subjects = useAsync(() => quizService.subjects(), []);
  const pool = useAsync(() => (isNew ? null : quizService.poolPreview(id)), [id]);

  const header = (
    <PageHeader
      title={isNew ? "New quiz" : quiz.data?.title || "Quiz"}
      description="Compose a quiz from the shared question bank."
      breadcrumbs={[
        isAdmin ? { label: "Admin", to: "/admin" } : { label: "Teaching", to: "/instructor" },
        { label: "Quizzes", to: base },
        { label: isNew ? "New" : "Edit" },
      ]}
    />
  );

  if (isNew) {
    return <div className="wrap pb-24 pt-12 lg:pt-14">{header}<NewQuiz base={base} /></div>;
  }
  if (quiz.loading) return <div className="wrap pt-12"><Skeleton className="h-48 w-full" /></div>;
  if (quiz.error) return <div className="wrap pt-12"><ErrorState error={quiz.error} onRetry={quiz.refetch} /></div>;
  if (!quiz.data) return <div className="wrap pt-12">Quiz not found.</div>;

  const reload = () => { pool.refetch(); quiz.refetch(); };
  const bank = subjects.data || [];

  return (
    <div className="wrap pb-24 pt-12 lg:pt-14">
      {header}
      <p className="mb-6 text-sm text-ink3">
        {quiz.data.question_count} questions · {quiz.data.total_marks} marks per attempt
      </p>
      <div className="grid gap-6">
        <Settings quiz={quiz.data} onSaved={reload} />
        <RandomRules quiz={quiz.data} subjects={bank} pool={pool.data} reload={reload} />
        <ManualPicks quiz={quiz.data} subjects={bank} reload={reload} />
        <NewQuestion subjects={bank} onCreated={() => { subjects.refetch(); reload(); }} />
      </div>
    </div>
  );
}
