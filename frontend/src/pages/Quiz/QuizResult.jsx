import { Link, useParams, useSearchParams } from "react-router-dom";

import Icon from "../../components/Icon";
import { EmptyState, ErrorState, Skeleton } from "../../components/ui";
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
      <div className="wrap max-w-2xl py-16">
        <EmptyState
          title="No attempt selected"
          description="Open a quiz result from your dashboard to see the review."
          action={
            <Link to="/dashboard" className="btn btn-gold">
              Back to dashboard
            </Link>
          }
        />
      </div>
    );
  }

  if (loading) {
    return (
      <div className="wrap max-w-3xl py-12">
        <Skeleton className="h-48 w-full" />
        <Skeleton className="mt-5 h-64 w-full" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="wrap max-w-2xl py-16">
        <ErrorState error={error} onRetry={refetch} />
      </div>
    );
  }

  if (!data?.attempt) return null;

  const { attempt, review = [] } = data;
  const correctCount = review.filter((row) => row.is_correct).length;
  const percent = Math.round(Number(attempt.percentage) || 0);

  return (
    <div className="wrap pb-24 pt-12 lg:pt-16">
      <div className="max-w-[860px]">
      <nav aria-label="Breadcrumb" className="small flex items-center gap-2 pb-8">
        <Link to="/dashboard" className="underline underline-offset-[3px] hover:text-ink">
          Dashboard
        </Link>
        <Icon name="caretRight" className="i-sm" />
        <span className="text-ink2" aria-current="page">
          Quiz result
        </span>
      </nav>

      {/* -------------------------------------------------------- Score summary */}
      <section
        aria-label="Your result"
        className="navy-surface flex flex-col gap-8 rounded-[14px] p-8 sm:p-10"
      >
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex flex-col gap-2">
            <span className="cap !text-[#B4BED6]">{attempt.quiz_title}</span>
            <h1 className="d2 !text-[64px] !leading-none sm:!text-[88px]">
              {attempt.score}
              <span className="text-[0.4em] text-[#8E9AB8]">
                {" "}
                / {attempt.max_score}
              </span>
            </h1>
          </div>
          <div className="flex flex-wrap gap-2">
            <span className={`tag ${attempt.passed ? "tag-ok" : "tag-bad"}`}>
              {attempt.passed ? "Passed" : "Not passed"}
            </span>
            <span className="tag !bg-white/10 !text-[#B4BED6]">
              Pass mark {attempt.pass_percentage}%
            </span>
            <span className="tag !bg-white/10 !text-[#B4BED6]">
              Attempt {attempt.attempt_number}
            </span>
          </div>
        </div>

        <div className="flex flex-col gap-2">
          <div
            className="h-1.5 overflow-hidden rounded-[3px] bg-white/[0.16]"
            role="progressbar"
            aria-label="Score"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={percent}
          >
            <i
              className="block h-full bg-[#C9A227]"
              style={{ width: `${percent}%` }}
            />
          </div>
          <span className="cap !text-[#B4BED6]">
            {percent}% scored, {correctCount} of {review.length} question
            {review.length === 1 ? "" : "s"} correct
            {attempt.duration_seconds > 0 &&
              `, completed in ${formatDuration(attempt.duration_seconds)}`}
          </span>
        </div>

        <div className="flex flex-wrap gap-3">
          <Link to={`/quiz/${quizId}`} className="btn btn-gold">
            {attempt.passed ? "Try again" : "Retake quiz"}
          </Link>
          <Link to="/dashboard" className="btn btn-on-navy">
            Back to dashboard
          </Link>
          <Link to="/leaderboard" className="btn btn-on-navy">
            See leaderboard
          </Link>
        </div>
      </section>

      {/* --------------------------------------------------------------- Review */}
      {review.length > 0 ? (
        <section className="pt-14" aria-labelledby="review-heading">
          <div className="flex flex-col gap-2 pb-6">
            <h2 id="review-heading" className="h3">
              Answer review
            </h2>
            <p className="small">
              Correct answers are revealed now that your attempt has been graded.
            </p>
          </div>

          <ol className="rows m-0 flex list-none flex-col border-t border-line-strong p-0">
            {review.map((row, index) => (
              <li key={row.question_id} className="flex flex-col gap-4 py-7">
                <div className="flex items-start justify-between gap-4">
                  <p className="flex gap-4 text-[17px] leading-snug">
                    <span className="mono cap pt-1">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <span>{row.question_text}</span>
                  </p>
                  <span
                    className={`tag flex-none ${row.is_correct ? "tag-ok" : "tag-bad"}`}
                  >
                    {row.is_correct ? "Correct" : "Incorrect"}
                  </span>
                </div>

                <p className="cap pl-[34px]">
                  {row.marks_awarded} of {row.marks_possible} mark
                  {row.marks_possible === 1 ? "" : "s"} awarded
                </p>

                {row.explanation && (
                  <div className="ml-[34px] rounded-[10px] border border-line bg-sunken px-5 py-4">
                    <p className="cap font-medium !text-gold-ink">Explanation</p>
                    <p className="body mt-1 !text-[15px]">{row.explanation}</p>
                  </div>
                )}
              </li>
            ))}
          </ol>
        </section>
      ) : (
        <p className="small border-y border-line py-6 mt-10 text-center">
          The detailed review is not available for this attempt.
        </p>
      )}
      </div>
    </div>
  );
}
