import { Link } from "react-router-dom";

import CourseCard from "../../components/CourseCard";
import {
  Badge,
  EmptyState,
  ErrorState,
  Panel,
  Skeleton,
} from "../../components/ui";
import { useAuth } from "../../context/AuthContext";
import useAsync from "../../hooks/useAsync";
import courseService from "../../services/courseService";

/**
 * Landing page.
 *
 * The catalogue is fetched once and sliced locally for the "featured" strip rather
 * than issuing a second request — one round trip instead of two on the slowest
 * page of the funnel.
 */
export default function Home() {
  const { isAuthenticated, user } = useAuth();
  const { data, loading, error, refetch } = useAsync(
    () => courseService.list({ page_size: 6 }),
    [],
  );

  const courses = data?.results || [];

  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-10 sm:py-14">
      {/* ---------------------------------------------------------------- Hero */}
      <section className="grid gap-10 lg:grid-cols-[1.15fr_0.85fr] lg:items-center">
        <div>
          <Badge tone="gold">Indian law, taught properly</Badge>
          <h1 className="mt-4 font-display text-3xl leading-tight text-parchment sm:text-5xl">
            Learn law the way it is{" "}
            <span className="text-gold-300">actually practised</span>
          </h1>
          <p className="mt-5 max-w-2xl text-base text-white/70">
            Structured video courses, graded assessments and a leaderboard that
            rewards consistency. Every lesson is streamed securely and tracks
            your progress automatically.
          </p>

          <div className="mt-8 flex flex-wrap gap-3">
            {isAuthenticated ? (
              <>
                <Link to="/dashboard" className="btn btn-primary">
                  Go to my dashboard
                </Link>
                <Link to="/courses" className="btn btn-ghost">
                  Browse all courses
                </Link>
              </>
            ) : (
              <>
                <Link to="/register" className="btn btn-primary">
                  Create free account
                </Link>
                <Link to="/courses" className="btn btn-ghost">
                  Explore courses
                </Link>
              </>
            )}
          </div>

          {isAuthenticated && (
            <p className="mt-4 text-sm text-white/55">
              Signed in as <span className="text-gold-300">{user?.email}</span>
            </p>
          )}
        </div>

        <Panel className="p-6">
          <h2 className="font-display text-lg text-parchment">What you get</h2>
          <ul className="mt-4 space-y-4 text-sm">
            {[
              [
                "\u{1F3AC}",
                "Protected lectures",
                "Short-lived signed playback — access follows your subscription.",
              ],
              [
                "\u2705",
                "Graded quizzes",
                "Scored on the server, with review explanations after submission.",
              ],
              [
                "\u{1F4C8}",
                "Real progress",
                "Resume exactly where you stopped, on any device.",
              ],
              [
                "\u{1F3C6}",
                "Leaderboard",
                "Measurable scores, ranked fairly and updated as you learn.",
              ],
            ].map(([icon, title, description]) => (
              <li key={title} className="flex gap-3">
                <span aria-hidden="true" className="text-lg">
                  {icon}
                </span>
                <span>
                  <span className="block font-semibold text-parchment">
                    {title}
                  </span>
                  <span className="text-white/60">{description}</span>
                </span>
              </li>
            ))}
          </ul>
        </Panel>
      </section>

      {/* ----------------------------------------------------------- Catalogue */}
      <section className="mt-16" aria-labelledby="featured-heading">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2
              id="featured-heading"
              className="font-display text-2xl text-parchment"
            >
              Featured courses
            </h2>
            <p className="mt-1 text-sm text-white/55">
              Published courses from our faculty. Locked titles are marked
              clearly.
            </p>
          </div>
          <Link to="/courses" className="text-sm text-gold-300 hover:underline">
            View all courses
          </Link>
        </div>

        {loading ? (
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 3 }).map((_, index) => (
              <Skeleton key={index} className="h-80 w-full" />
            ))}
          </div>
        ) : error ? (
          <ErrorState error={error} onRetry={refetch} />
        ) : courses.length === 0 ? (
          <Panel>
            <EmptyState
              title="No courses published yet"
              description="Courses will appear here as soon as an instructor publishes them."
            />
          </Panel>
        ) : (
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {courses.map((course) => (
              <CourseCard key={course.id} course={course} />
            ))}
          </div>
        )}
      </section>

      {/* ---------------------------------------------------------------- CTA */}
      {!isAuthenticated && (
        <section className="mt-16">
          <Panel className="flex flex-col items-center gap-4 p-8 text-center">
            <h2 className="font-display text-2xl text-parchment">
              Ready to start your first module?
            </h2>
            <p className="max-w-xl text-sm text-white/60">
              Create an account to preview lessons for free. Unlock full courses
              whenever you are ready with a subscription.
            </p>
            <div className="flex flex-wrap justify-center gap-3">
              <Link to="/register" className="btn btn-primary">
                Create free account
              </Link>
              <Link to="/subscription" className="btn btn-ghost">
                Compare plans
              </Link>
            </div>
          </Panel>
        </section>
      )}
    </div>
  );
}
