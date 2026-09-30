import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { PageHeader } from "../../components/Layout";
import { Badge, Button, Callout, ErrorState, Panel, Skeleton } from "../../components/ui";
import { quizService } from "../../services/quizService";
import { formatDuration } from "../../utils/format";

/**
 * Quiz attempt screen.
 *
 * Two rules this page respects, mirroring the backend contract:
 *
 * 1. **The answer key never reaches the browser before submission.** The UI cannot
 *    know which option is correct, so it cannot grade anything — it only records
 *    the student's selection.
 * 2. **The score is computed by the server.** After submitting we navigate to the
 *    result screen, which re-fetches the graded attempt from the API rather than
 *    trusting anything held in the browser.
 *
 * The countdown timer is advisory; the authoritative window lives in the database.
 *
 * Data flow: ``POST /quizzes/<id>/attempts/`` returns the attempt *and* the quiz
 * body, so this screen becomes interactive after exactly one request.
 */
export default function Quiz() {
  const { quizId } = useParams();
  const navigate = useNavigate();

  const [payload, setPayload] = useState(null); // { attempt, quiz, attempts_remaining }
  const [answers, setAnswers] = useState({});
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [remainingSeconds, setRemainingSeconds] = useState(null);

  const startedAtRef = useRef(null);
  const startedRef = useRef(false);

  /* ----------------------------- Start attempt ----------------------------- */
  const begin = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await quizService.start(quizId);
      setPayload(data);
      startedAtRef.current = Date.now();

      if (data.quiz?.time_limit_minutes) {
        // Account for time already spent when resuming an in-flight attempt.
        const elapsed = data.attempt?.started_at
          ? Math.floor((Date.now() - new Date(data.attempt.started_at).getTime()) / 1000)
          : 0;
        setRemainingSeconds(Math.max(0, data.quiz.time_limit_minutes * 60 - elapsed));
      }
      return data;
    } catch (caught) {
      setError(caught);
      return null;
    } finally {
      setLoading(false);
    }
  }, [quizId]);

  useEffect(() => {
    // Guard against StrictMode double-invoking effects in development: starting two
    // attempts would consume the student's allowance for no reason.
    if (startedRef.current) return;
    startedRef.current = true;
    begin();
  }, [begin]);

  /* ------------------------------ Submission ------------------------------ */
  const submit = useCallback(async () => {
    if (!payload?.attempt || submitting) return;

    setSubmitting(true);
    setError(null);
    try {
      const durationSeconds = startedAtRef.current
        ? Math.round((Date.now() - startedAtRef.current) / 1000)
        : 0;
      await quizService.submit(payload.attempt.id, { answers, durationSeconds });
      // No result passed through router state: the result page fetches the graded
      // attempt, so the source of truth is always the API.
      navigate(`/quiz/${quizId}/result?attempt=${payload.attempt.id}`, { replace: true });
    } catch (caught) {
      setError(caught);
      setSubmitting(false);
    }
  }, [payload, submitting, answers, quizId, navigate]);

  /* ------------------------------- Countdown ------------------------------- */
  useEffect(() => {
    if (remainingSeconds === null) return undefined;
    if (remainingSeconds <= 0) {
      // Auto-submit so an idle student does not lose answers silently.
      submit();
      return undefined;
    }
    const timer = window.setTimeout(() => setRemainingSeconds((value) => value - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [remainingSeconds, submit]);

  /* --------------------------- Guard against leaving ---------------------- */
  useEffect(() => {
    if (!payload || submitting) return undefined;
    const warn = (event) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [payload, submitting]);

  /* -------------------------------- Render -------------------------------- */
  if (loading) {
    return (
      <div className="mx-auto w-full max-w-3xl px-4 py-10" aria-busy="true">
        <Skeleton className="h-8 w-1/2" />
        <Skeleton className="mt-6 h-44 w-full" />
        <Skeleton className="mt-4 h-44 w-full" />
      </div>
    );
  }

  if (error && !payload) {
    const locked = ["subscription_required", "subscription_expired", "not_in_plan"].includes(
      error.code,
    );
    const exhausted = error.code === "attempt_limit_reached";

    return (
      <div className="mx-auto w-full max-w-2xl px-4 py-16">
        <Panel className="p-8 text-center">
          <h1 className="font-display text-2xl text-gold-300">
            {exhausted ? "No attempts left" : locked ? "Quiz locked" : "Quiz unavailable"}
          </h1>
          <p className="mt-3 text-sm text-white/70">{error.message}</p>
          <div className="mt-6 flex flex-wrap justify-center gap-3">
            {locked && (
              <Link to="/subscription" className="btn btn-primary">
                View plans
              </Link>
            )}
            <Link to="/dashboard" className="btn btn-ghost">
              Back to dashboard
            </Link>
          </div>
        </Panel>
      </div>
    );
  }

  const questions = payload.quiz.questions || [];
  const answeredCount = Object.values(answers).filter(Boolean).length;
  const attemptsLeft = payload.attempts_remaining;

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-8 sm:py-10">
      <PageHeader
        title={payload.quiz.title}
        description="Answers are graded on the server when you submit. Explanations appear afterwards."
        breadcrumbs={[{ label: "Dashboard", to: "/dashboard" }, { label: "Quiz" }]}
        actions={
          remainingSeconds !== null ? (
            <Badge tone={remainingSeconds < 60 ? "danger" : "gold"}>
              {formatDuration(remainingSeconds)} remaining
            </Badge>
          ) : (
            <Badge tone="muted">Untimed</Badge>
          )
        }
      />

      <Panel className="mb-5 flex flex-wrap items-center justify-between gap-3 p-4">
        <p className="text-xs text-white/55">
          {questions.length} question{questions.length === 1 ? "" : "s"} · pass mark{" "}
          {payload.quiz.pass_percentage}%
          {attemptsLeft === null || attemptsLeft === undefined
            ? " · unlimited attempts"
            : ` · ${attemptsLeft} attempt${attemptsLeft === 1 ? "" : "s"} remaining`}
        </p>
        <span className="text-sm text-white/65" aria-live="polite">
          {answeredCount} of {questions.length} answered
        </span>
      </Panel>

      {error && (
        <div className="mb-5">
          <ErrorState error={error} />
        </div>
      )}

      <ol className="space-y-4">
        {questions.map((question, index) => (
          <li key={question.id}>
            <Panel className="p-5">
              <fieldset>
                <legend className="mb-3 font-medium text-parchment">
                  <span className="mr-2 text-gold-500" aria-hidden="true">
                    {String(index + 1).padStart(2, "0")}.
                  </span>
                  {question.text}
                  <span className="ml-2 text-xs font-normal text-white/45">
                    ({question.marks} mark{question.marks === 1 ? "" : "s"})
                  </span>
                </legend>

                <div className="space-y-2">
                  {question.options.map((option) => {
                    const selected = answers[question.id] === option.id;
                    return (
                      <label
                        key={option.id}
                        className={`flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-3 text-sm transition-colors ${
                          selected
                            ? "border-gold-500 bg-gold-500/10 text-parchment"
                            : "border-white/10 hover:border-white/25"
                        }`}
                      >
                        <input
                          type="radio"
                          name={`question-${question.id}`}
                          value={option.id}
                          checked={selected}
                          onChange={() =>
                            setAnswers((current) => ({ ...current, [question.id]: option.id }))
                          }
                          className="h-4 w-4 accent-[var(--color-gold-500)]"
                        />
                        <span>{option.text}</span>
                      </label>
                    );
                  })}
                </div>
              </fieldset>
            </Panel>
          </li>
        ))}
      </ol>

      {questions.length === 0 && (
        <Panel className="p-6 text-center text-sm text-white/60">
          This quiz has no questions yet.
        </Panel>
      )}

      <Panel className="mt-5 flex flex-wrap items-center justify-between gap-3 p-4">
        <p className="text-xs text-white/50">
          Unanswered questions score zero. Your result is saved automatically.
        </p>
        <Button onClick={submit} loading={submitting} disabled={questions.length === 0}>
          {submitting ? "Grading…" : "Submit answers"}
        </Button>
      </Panel>

      {remainingSeconds !== null && remainingSeconds < 120 && (
        <div className="mt-4">
          <Callout tone="warning">
            Less than two minutes remaining. The quiz submits automatically when time runs out.
          </Callout>
        </div>
      )}
    </div>
  );
}