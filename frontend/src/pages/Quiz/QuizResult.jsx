import { Link, useParams, useSearchParams } from "react-router-dom";

import { PageHeader } from "../../components/Layout";
import {
  Badge,
  Button,
  EmptyState,
  ErrorState,
  Panel,
  ProgressBar,
  Skeleton,
} from "../../components/ui";
import useAsync from "../../hooks/useAsync";
import { quizService } from "../../services/quizService";
import { formatDuration } from "../../utils/format";

/**
 * Quiz result + review.
 *
 * Everything shown here comes from the server's graded attempt. Correct answers and
 * explanations are only available *after* grading, which is why the review is
 * rendered from `GET /quiz-attempts/<id>/` rather than being derived locally.
 */
export default function QuizResult() {
  const { quizId } = useParams();
  const [searchParams] = useSearchParams();
  const attemptId = searchParams.get("attempt");

  const { data, loading, error, refetch } = useAsync(
    () => (attemptId ? quizService.attempt(attemptId) : Promise.resolve(null)),
    [attemptId],
    { immediate: Boolean(attemptId) },
  );

  if (!attemptId) {
    return (
      <div className="mx-auto w-full max-w-2xl px-4 py-16">
        <Panel>
          <EmptyState
            title="No attempt selected"
            description="Open a quiz result from your dashboard to see the review."
            action={
              <Link to="/dashboard" className="btn btn-primary">
                Back to dashboard
              </Link>
            }
          />
        </Panel>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="mx-auto w-full max-w-3xl px-4 py-10">
        <Skeleton className="h-36 w-full" />
        <Skeleton className="mt-5 h-64 w-full" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="mx-auto w-full max-w-2xl px-4 py-16">
        <ErrorState error={error} onRetry={refetch} />
      </div>
    );
  }

  if (!data?.attempt) return null;

  const { attempt, review = [] } = data;
  const correctCount = review.filter((row) => row.is_correct).length;

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-8 sm:py-10">
      <PageHeader
        title="Quiz result"
        description={attempt.quiz_title}
        breadcrumbs={[
          { label: "Dashboard", to: "/dashboard" },
          { label: "Quiz", to: `/quiz/${quizId}` },
          { label: "Result" },
        ]}
      />

      {/* -------------------------------------------------------- Score summary */}
      <Panel className="p-6">
        <div className="flex flex-wrap items-center justify-between gap-6">
          <div>
            <p className="text-xs uppercase tracking-wider text-white/45">
              Your score
            </p>
            <p className="mt-1 font-display text-4xl text-gold-300">
              {attempt.score}
              <span className="text-xl text-white/40">
                /{attempt.max_score}
              </span>
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <Badge tone={attempt.passed ? "success" : "danger"}>
                {attempt.passed ? "Passed" : "Not passed"}
              </Badge>
              <Badge tone="muted">Pass mark {attempt.pass_percentage}%</Badge>
              <Badge tone="muted">Attempt {attempt.attempt_number}</Badge>
            </div>
          </div>

          <div className="min-w-[180px] flex-1">
            <ProgressBar
              value={attempt.percentage}
              label={`${Math.round(Number(attempt.percentage))}% scored`}
            />
            <p className="mt-3 text-xs text-white/45">
              {correctCount} of {review.length} question
              {review.length === 1 ? "" : "s"} correct
              {attempt.duration_seconds > 0 &&
                ` · completed in ${formatDuration(attempt.duration_seconds)}`}
            </p>
          </div>
        </div>

        <div className="mt-6 flex flex-wrap gap-3">
          <Link to={`/quiz/${quizId}`} className="btn btn-primary">
            {attempt.passed ? "Try again" : "Retake quiz"}
          </Link>
          <Link to="/dashboard" className="btn btn-ghost">
            Back to dashboard
          </Link>
          <Link to="/leaderboard" className="btn btn-ghost">
            See leaderboard
          </Link>
        </div>
      </Panel>

      {/* --------------------------------------------------------------- Review */}
      {review.length > 0 && (
        <section className="mt-8" aria-labelledby="review-heading">
          <h2
            id="review-heading"
            className="font-display text-xl text-parchment"
          >
            Answer review
          </h2>
          <p className="mt-1 text-sm text-white/55">
            Correct answers are revealed now that your attempt has been graded.
          </p>
          <div className="gold-rule my-4" />

          <ol className="space-y-4">
            {review.map((row, index) => (
              <li key={row.question_id}>
                <Panel className="p-5">
                  <div className="flex items-start justify-between gap-4">
                    <p className="font-medium text-parchment">
                      <span className="mr-2 text-gold-500" aria-hidden="true">
                        {String(index + 1).padStart(2, "0")}.
                      </span>
                      {row.question_text}
                    </p>
                    <Badge tone={row.is_correct ? "success" : "danger"}>
                      {row.is_correct ? "Correct" : "Incorrect"}
                    </Badge>
                  </div>

                  <p className="mt-3 text-xs text-white/50">
                    {row.marks_awarded} of {row.marks_possible} mark
                    {row.marks_possible === 1 ? "" : "s"} awarded
                  </p>

                  {row.explanation && (
                    <div className="mt-4 rounded-lg border border-[var(--color-border-subtle)] bg-white/[0.03] px-4 py-3">
                      <p className="text-xs font-semibold uppercase tracking-wider text-gold-300">
                        Explanation
                      </p>
                      <p className="mt-1 text-sm text-white/70">
                        {row.explanation}
                      </p>
                    </div>
                  )}
                </Panel>
              </li>
            ))}
          </ol>
        </section>
      )}

      {review.length === 0 && (
        <div className="mt-8">
          <Panel className="p-6 text-center text-sm text-white/60">
            The detailed review is not available for this attempt.
          </Panel>
        </div>
      )}
    </div>
  );
}
