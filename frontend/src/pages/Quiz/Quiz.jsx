import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import Icon from "../../components/Icon";
import { Callout, ErrorState, Skeleton } from "../../components/ui";
import { quizService } from "../../services/quizService";
import { formatDuration } from "../../utils/format";

/**
 * Quiz attempt screen (focus mode).
 *
 * Two rules this page respects, mirroring the backend contract:
 *
 * 1. **The answer key never reaches the browser before submission.** The UI cannot
 *    know which option is correct, so it cannot grade anything; it only records
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
const LOCKED_CODES = [
  "subscription_required",
  "subscription_expired",
  "not_in_plan",
];

export default function Quiz() {
  const { quizId } = useParams();
  const navigate = useNavigate();

  const [payload, setPayload] = useState(null); // { attempt, quiz, attempts_remaining }
  const [answers, setAnswers] = useState({});
  const [flagged, setFlagged] = useState({});
  const [current, setCurrent] = useState(0);
  const [reviewing, setReviewing] = useState(false);
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
          ? Math.floor(
              (Date.now() - new Date(data.attempt.started_at).getTime()) / 1000,
            )
          : 0;
        setRemainingSeconds(
          Math.max(0, data.quiz.time_limit_minutes * 60 - elapsed),
        );
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
      await quizService.submit(payload.attempt.id, {
        answers,
        durationSeconds,
      });
      // No result passed through router state: the result page fetches the graded
      // attempt, so the source of truth is always the API.
      navigate(`/quiz/${quizId}/result?attempt=${payload.attempt.id}`, {
        replace: true,
      });
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
    const timer = window.setTimeout(
      () => setRemainingSeconds((value) => value - 1),
      1000,
    );
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
      <div className="wrap max-w-3xl py-10" aria-busy="true">
        <Skeleton className="h-8 w-1/2" />
        <Skeleton className="mt-6 h-44 w-full" />
        <Skeleton className="mt-4 h-44 w-full" />
      </div>
    );
  }

  if (error && !payload) {
    const locked = LOCKED_CODES.includes(error.code);
    const exhausted = error.code === "attempt_limit_reached";

    return (
      <div className="wrap max-w-2xl py-16">
        <div className="card flex flex-col items-center gap-4 p-8 text-center sm:p-10">
          <h1 className="h3">
            {exhausted
              ? "No attempts left"
              : locked
                ? "Quiz locked"
                : "Quiz unavailable"}
          </h1>
          <p className="body">{error.message}</p>
          <div className="flex flex-wrap justify-center gap-3 pt-2">
            {locked && (
              <Link to="/subscription" className="btn btn-gold">
                View plans
              </Link>
            )}
            <Link to="/dashboard" className="btn btn-line">
              Back to dashboard
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const questions = payload.quiz.questions || [];
  const total = questions.length;
  const question = questions[current];
  const attemptsLeft = payload.attempts_remaining;
  const isAnswered = (item) => Boolean(answers[item.id]);
  const answeredCount = questions.filter(isAnswered).length;
  const flaggedCount = questions.filter((item) => flagged[item.id]).length;
  const unanswered = questions
    .map((item, index) => ({ item, index }))
    .filter(({ item }) => !isAnswered(item));
  const lowTime = remainingSeconds !== null && remainingSeconds < 60;

  function goTo(index) {
    setReviewing(false);
    setCurrent(Math.max(0, Math.min(total - 1, index)));
  }

  function saveAndNext() {
    if (current >= total - 1) setReviewing(true);
    else setCurrent(current + 1);
  }

  return (
    <div>
      <header className="flex min-h-[68px] flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-8">
        <div className="flex min-w-0 items-center gap-4">
          <Link to="/dashboard" className="btn btn-line">
            <Icon name="x" />
            Exit quiz
          </Link>
          <span className="small hidden truncate sm:inline">
            {payload.quiz.title}
          </span>
        </div>
        {remainingSeconds !== null ? (
          <div
            role="timer"
            aria-label={`${formatDuration(remainingSeconds)} left`}
            className={`flex h-11 items-center gap-2 rounded-lg border bg-card px-4 ${lowTime ? "border-bad" : "border-line-strong"}`}
          >
            <Icon name="clock" className={lowTime ? "text-bad" : ""} />
            <span className={`mono font-medium ${lowTime ? "text-bad" : ""}`}>
              {formatDuration(remainingSeconds)}
            </span>
            <span className="small">left</span>
          </div>
        ) : (
          <span className="tag">Untimed</span>
        )}
      </header>

      {total > 0 && (
        <div
          className="flex gap-1 px-4 sm:px-8"
          role="progressbar"
          aria-valuemin={1}
          aria-valuemax={total}
          aria-valuenow={current + 1}
          aria-label={`Question ${current + 1} of ${total}`}
        >
          {questions.map((item, index) => (
            <i
              key={item.id}
              className={`h-1 flex-1 rounded-sm ${
                index === current
                  ? "bg-ink"
                  : isAnswered(item)
                    ? "bg-gold"
                    : "bg-line-strong"
              }`}
            />
          ))}
        </div>
      )}

      <div className="grid items-start gap-10 px-4 pb-16 pt-8 sm:px-8 lg:grid-cols-[minmax(0,1fr)_360px] lg:pt-10">
        <div className="flex min-w-0 flex-col gap-6">
          {error && <ErrorState error={error} />}

          {remainingSeconds !== null && remainingSeconds < 120 && (
            <Callout tone="warning">
              Less than two minutes remaining. The quiz submits automatically
              when time runs out.
            </Callout>
          )}

          {total === 0 ? (
            <div className="card p-8 text-center">
              <p className="body">This quiz has no questions yet.</p>
            </div>
          ) : reviewing ? (
            <section
              className="card flex flex-col gap-6 p-7 sm:p-11"
              aria-labelledby="review-heading"
            >
              <h1 id="review-heading" className="h2 !text-[34px]">
                Review and submit
              </h1>
              <dl className="m-0 grid grid-cols-3 border-y border-line">
                {[
                  [answeredCount, "answered"],
                  [flaggedCount, "flagged"],
                  [unanswered.length, "not answered"],
                ].map(([value, label], index) => (
                  <div
                    key={label}
                    className={`flex flex-col py-5 ${index > 0 ? "border-l border-line pl-5" : ""}`}
                  >
                    <dd className="m-0 font-serif text-[34px] leading-[1.1] num">
                      {value}
                    </dd>
                    <dt className="small">{label}</dt>
                  </div>
                ))}
              </dl>

              {unanswered.length > 0 && (
                <div className="flex flex-col gap-3">
                  <p className="body">
                    Unanswered questions score zero. Jump back to any of them:
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {unanswered.map(({ index }) => (
                      <button
                        key={index}
                        type="button"
                        onClick={() => goTo(index)}
                        className="btn btn-line mono !w-12 !px-0"
                        aria-label={`Go to question ${index + 1}`}
                      >
                        {index + 1}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              <div className="flex flex-wrap justify-between gap-3 pt-2">
                <button
                  type="button"
                  className="btn btn-line btn-lg"
                  onClick={() => setReviewing(false)}
                  disabled={submitting}
                >
                  <Icon name="caretLeft" />
                  Back to questions
                </button>
                <button
                  type="button"
                  className="btn btn-gold btn-lg"
                  onClick={submit}
                  disabled={submitting}
                  aria-busy={submitting || undefined}
                >
                  {submitting ? "Grading…" : "Submit answers"}
                </button>
              </div>
            </section>
          ) : (
            <>
              <section
                className="card flex flex-col gap-8 p-7 sm:p-11"
                aria-labelledby="question-heading"
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <span className="small num">
                    Question {current + 1} of {total}, {question.marks} mark
                    {question.marks === 1 ? "" : "s"}
                  </span>
                  <button
                    type="button"
                    className="btn btn-line"
                    aria-pressed={Boolean(flagged[question.id])}
                    onClick={() =>
                      setFlagged((value) => ({
                        ...value,
                        [question.id]: !value[question.id],
                      }))
                    }
                  >
                    <Icon name="flag" />
                    {flagged[question.id] ? "Flagged" : "Flag for review"}
                  </button>
                </div>

                <div className="flex flex-col gap-3">
                  <h1
                    id="question-heading"
                    className="h2 !text-[26px] !leading-[1.25] sm:!text-[36px]"
                  >
                    {question.text}
                  </h1>
                  <p className="small">Select one answer.</p>
                </div>

                <div
                  className="flex flex-col gap-3"
                  role="radiogroup"
                  aria-labelledby="question-heading"
                >
                  {question.options.map((option, index) => {
                    const selected = answers[question.id] === option.id;
                    return (
                      <label
                        key={option.id}
                        className={`opt ${selected ? "sel" : ""}`}
                      >
                        <input
                          type="radio"
                          name={`question-${question.id}`}
                          value={option.id}
                          checked={selected}
                          onChange={() =>
                            setAnswers((value) => ({
                              ...value,
                              [question.id]: option.id,
                            }))
                          }
                        />
                        <span className="key" aria-hidden="true">
                          {String.fromCharCode(65 + index)}
                        </span>
                        <span className={`flex-1 ${selected ? "font-medium" : ""}`}>
                          {option.text}
                        </span>
                        {selected && <Icon name="check" className="text-gold-ink" />}
                      </label>
                    );
                  })}
                </div>
              </section>

              <div className="flex items-center justify-between gap-3">
                <button
                  type="button"
                  className="btn btn-line btn-lg"
                  onClick={() => goTo(current - 1)}
                  disabled={current === 0}
                >
                  <Icon name="caretLeft" />
                  Previous
                </button>
                <button
                  type="button"
                  className="btn btn-gold btn-lg"
                  onClick={saveAndNext}
                >
                  {current >= total - 1 ? "Review and submit" : "Save and next"}
                  <Icon name="caretRight" />
                </button>
              </div>
            </>
          )}
        </div>

        <aside
          aria-label="Question navigator"
          className="card flex flex-col gap-5 p-7"
        >
          <h2 className="h4">Questions</h2>
          <div className="grid grid-cols-5 gap-2">
            {questions.map((item, index) => {
              const isCurrent = index === current && !reviewing;
              const answered = isAnswered(item);
              const isFlagged = Boolean(flagged[item.id]);
              const state = [
                answered ? "answered" : "unanswered",
                isFlagged ? "flagged" : null,
                isCurrent ? "current" : null,
              ]
                .filter(Boolean)
                .join(", ");
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => goTo(index)}
                  aria-label={`Question ${index + 1}, ${state}`}
                  aria-current={isCurrent ? "true" : undefined}
                  className={`mono flex h-12 items-center justify-center rounded-lg ${
                    isCurrent
                      ? "bg-ink font-medium text-page"
                      : answered
                        ? "bg-gold font-medium text-on-gold"
                        : "border border-control"
                  } ${isFlagged ? "shadow-[0_0_0_2px_var(--surface),0_0_0_4px_var(--ink)]" : ""}`}
                >
                  {index + 1}
                </button>
              );
            })}
          </div>

          <hr className="rule" />
          <ul className="m-0 flex list-none flex-col gap-3 p-0 text-sm text-ink2">
            <li className="flex items-center gap-3">
              <span className="inline-block h-5 w-5 rounded-[5px] bg-gold" />
              <span className="flex-1">Answered</span>
              <span className="mono">{answeredCount}</span>
            </li>
            <li className="flex items-center gap-3">
              <span className="inline-block h-5 w-5 rounded-[5px] bg-gold shadow-[0_0_0_2px_var(--surface),0_0_0_4px_var(--ink)]" />
              <span className="flex-1">Flagged for review</span>
              <span className="mono">{flaggedCount}</span>
            </li>
            <li className="flex items-center gap-3">
              <span className="inline-block h-5 w-5 rounded-[5px] border border-control" />
              <span className="flex-1">Not answered</span>
              <span className="mono">{unanswered.length}</span>
            </li>
          </ul>

          <button
            type="button"
            className="btn btn-line btn-block"
            onClick={() => setReviewing(true)}
            disabled={total === 0 || submitting}
          >
            Review and submit
          </button>

          <p className="cap">
            Pass mark {payload.quiz.pass_percentage}%
            {attemptsLeft === null || attemptsLeft === undefined
              ? ", unlimited attempts"
              : `, ${attemptsLeft} attempt${attemptsLeft === 1 ? "" : "s"} remaining`}
            . Answers are graded on the server when you submit.
          </p>
        </aside>
      </div>
    </div>
  );
}
