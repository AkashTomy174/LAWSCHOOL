import { Link } from "react-router-dom";

import Icon from "../../components/Icon";
import { EmptyState, ErrorState, Skeleton } from "../../components/ui";
import { useAuth } from "../../context/AuthContext";
import useAsync from "../../hooks/useAsync";
import courseService from "../../services/courseService";
import { subscriptionService } from "../../services/paymentService";
import {
  formatDurationLabel,
  formatPrice,
  truncate,
} from "../../utils/format";

/**
 * Landing page.
 *
 * Everything that looks like data here (course counts, lesson totals, plans and
 * prices) comes from the API. The product tiles in the hero and the feature grid
 * are illustrative interface samples and are hidden from assistive tech.
 */
const CATALOGUE_PAGE = 50;

export default function Home() {
  const { isAuthenticated } = useAuth();
  const catalogue = useAsync(
    () => courseService.list({ page_size: CATALOGUE_PAGE }),
    [],
  );
  const plans = useAsync(() => subscriptionService.plans(), []);

  const courses = catalogue.data?.results || [];
  const totalCourses = catalogue.data?.count ?? courses.length;
  const [featured, ...others] = courses;

  return (
    <>
      <Hero isAuthenticated={isAuthenticated} />
      <Stats courses={courses} total={totalCourses} loading={catalogue.loading} />
      <Features />
      <FeaturedCourses
        loading={catalogue.loading}
        error={catalogue.error}
        retry={catalogue.refetch}
        featured={featured}
        others={others.slice(0, 3)}
      />
      <Plans plans={plans.data} />
      <ClosingBand isAuthenticated={isAuthenticated} />
    </>
  );
}

/* -------------------------------------------------------------------------- */
function Hero({ isAuthenticated }) {
  return (
    <section className="wrap pb-20 pt-14 lg:pb-28 lg:pt-[72px]">
      <div className="grid gap-14 lg:grid-cols-[7fr_5fr] lg:items-center">
        <div className="flex flex-col gap-8">
          <h1 className="d1">
            Law, taught by people who <em>practise</em> it.
          </h1>
          <p className="lead">
            Recorded lectures, a question bank that marks your answers, and live
            classes for judiciary, bar and LLB students.
          </p>
          <div className="flex flex-wrap gap-3 pt-2">
            {isAuthenticated ? (
              <>
                <Link to="/dashboard" className="btn btn-gold btn-lg">
                  Go to my dashboard
                </Link>
                <Link to="/courses" className="btn btn-line btn-lg">
                  Browse courses
                </Link>
              </>
            ) : (
              <>
                <Link to="/register" className="btn btn-gold btn-lg">
                  Start free
                </Link>
                <Link to="/courses" className="btn btn-line btn-lg">
                  <Icon name="play" />
                  Explore courses
                </Link>
              </>
            )}
          </div>
        </div>

        {/* Decorative interface sample: a lecture over a practice question. */}
        <div
          className="relative hidden h-[590px] lg:block"
          aria-hidden="true"
        >
          <div className="navy-surface lift absolute left-0 top-0 flex h-[318px] w-[min(470px,94%)] flex-col justify-between rounded-[14px] p-[22px]">
            <span className="tag self-start !bg-white/10 !text-[#B4BED6]">
              Criminal Procedure
            </span>
            <div className="flex items-center justify-center">
              <span className="flex h-[60px] w-[60px] items-center justify-center rounded-full bg-[#C9A227] text-[#0B1220]">
                <Icon name="play" className="i-lg" />
              </span>
            </div>
            <div className="flex flex-col gap-3">
              <h3 className="h4">Bail and anticipatory bail</h3>
              <div className="flex items-center gap-3">
                <div className="h-1 flex-1 overflow-hidden rounded-sm bg-white/20">
                  <i className="block h-full w-[31%] bg-[#C9A227]" />
                </div>
                <span className="mono cap !text-[#B4BED6]">12:08 / 38:40</span>
              </div>
            </div>
          </div>

          <div className="card lift absolute right-0 top-[262px] flex w-[min(424px,90%)] flex-col gap-3.5 p-[22px]">
            <div className="flex items-center justify-between">
              <span className="cap">Question 7 of 20</span>
              <span className="tag tag-gold">Constitutional Law</span>
            </div>
            <h3 className="h4 !leading-tight">
              Which Article protects a person against self-incrimination?
            </h3>
            <div className="flex flex-col gap-2">
              {[
                ["A", "Article 14", false],
                ["B", "Article 20(3)", true],
                ["C", "Article 22(1)", false],
              ].map(([key, text, selected]) => (
                <div
                  key={key}
                  className={`opt !min-h-12 ${selected ? "sel" : ""}`}
                >
                  <span className="key !h-7 !w-7">{key}</span>
                  {text}
                </div>
              ))}
            </div>
            <div className="flex justify-end">
              <span className="btn btn-gold">Check answer</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------------- */
function Stats({ courses, total, loading }) {
  if (loading || courses.length === 0) return null;

  const lessons = courses.reduce(
    (sum, course) => sum + (Number(course.lesson_count) || 0),
    0,
  );
  const minutes = courses.reduce(
    (sum, course) => sum + (Number(course.duration_minutes) || 0),
    0,
  );
  // The catalogue is read in one page; say so when there is more than that.
  const partial = total > courses.length ? "+" : "";

  const stats = [
    [`${total}`, total === 1 ? "course" : "courses"],
    [`${lessons}${partial}`, "recorded lessons"],
    minutes > 0 ? [formatDurationLabel(minutes * 60), "of lectures"] : null,
  ].filter(Boolean);

  return (
    <section className="wrap pb-20 lg:pb-24" aria-label="The catalogue in numbers">
      <dl
        className="m-0 grid border-y border-line"
        style={{ gridTemplateColumns: `repeat(${stats.length}, minmax(0, 1fr))` }}
      >
        {stats.map(([value, label], index) => (
          <div
            key={label}
            className={`flex flex-col gap-1 py-8 ${index > 0 ? "border-l border-line pl-6 lg:pl-8" : ""}`}
          >
            <dd className="m-0 font-serif text-[34px] leading-none num sm:text-[44px] lg:text-[52px]">
              {value}
            </dd>
            <dt className="small">{label}</dt>
          </div>
        ))}
      </dl>
    </section>
  );
}

/* -------------------------------------------------------------------------- */
function Features() {
  return (
    <section className="wrap pb-24 lg:pb-28">
      <div className="flex max-w-[720px] flex-col gap-4 pb-10">
        <h2 className="h2">Watch, practise, ask.</h2>
        <p className="body">
          Lectures you can resume anywhere, a question bank that explains every
          answer, and live classes where you can put a question to faculty.
        </p>
      </div>

      <div className="grid gap-5 lg:grid-cols-12 lg:grid-rows-[260px_260px]">
        <div className="navy-surface flex flex-col justify-between gap-8 rounded-[14px] p-8 lg:col-span-7 lg:row-span-2 lg:p-9">
          <div className="flex max-w-[460px] flex-col gap-3">
            <h3 className="h3">Lectures that remember where you stopped.</h3>
            <p className="text-base leading-relaxed text-[#B4BED6]">
              Every lesson keeps your place, marks itself complete when you
              finish, and unlocks the next one.
            </p>
          </div>
          <ul
            aria-hidden="true"
            className="m-0 flex list-none flex-col rounded-[10px] border border-white/10 bg-white/5 p-0"
          >
            <li className="flex items-center gap-3 px-[18px] py-3.5">
              <span className="flex h-[22px] w-[22px] items-center justify-center rounded-full bg-[#5FCB9D] text-[#07211A]">
                <Icon name="check" className="i-sm" />
              </span>
              <span className="flex-1 text-[15px]">
                Bailable and non-bailable offences
              </span>
              <span className="mono cap !text-[#B4BED6]">19:30</span>
            </li>
            <li className="flex items-center gap-3 border-t border-white/10 bg-[rgba(212,175,55,0.12)] px-[18px] py-3.5">
              <span className="flex h-[22px] w-[22px] items-center justify-center rounded-full border-2 border-[#D4AF37]">
                <i className="block h-2 w-2 rounded-full bg-[#D4AF37]" />
              </span>
              <span className="flex-1 text-[15px] font-medium">
                Bail and anticipatory bail
              </span>
              <span className="mono cap !text-[#E6C766]">12:08 left</span>
            </li>
            <li className="flex items-center gap-3 border-t border-white/10 px-[18px] py-3.5">
              <span className="h-[22px] w-[22px] rounded-full border-[1.5px] border-[#8E9AB8]" />
              <span className="flex-1 text-[15px] text-[#B4BED6]">
                Default bail
              </span>
              <span className="mono cap !text-[#8E9AB8]">16:22</span>
            </li>
          </ul>
        </div>

        <div className="card flex flex-col justify-between gap-6 p-8 lg:col-span-5">
          <div className="flex flex-col gap-2">
            <h3 className="h4">Practice that explains itself.</h3>
            <p className="small !text-[15px]">
              Every answer shows the reasoning and the case behind it, once you
              have submitted.
            </p>
          </div>
          <div
            aria-hidden="true"
            className="rounded-[10px] border border-line bg-sunken p-4 text-sm"
          >
            <p className="font-medium text-ink">Article 20(3)</p>
            <p className="mt-1 text-ink2">
              No person accused of any offence shall be compelled to be a
              witness against himself.
            </p>
          </div>
        </div>

        <div className="flex flex-col justify-between gap-6 rounded-[14px] bg-gold-tint p-8 lg:col-span-5">
          <div className="flex flex-col gap-2">
            <h3 className="h4 !text-[#0B1220]">Live classes with the faculty.</h3>
            <p className="!text-[15px] text-[#4A3A00]">
              Join links appear for subscribers shortly before each class
              starts.
            </p>
          </div>
          <Link
            to="/subscription"
            className="inline-flex h-11 items-center self-start text-[15px] font-medium text-[#0B1220] underline underline-offset-4"
          >
            See which plans include live classes
          </Link>
        </div>
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------------- */
function courseMeta(course) {
  return [
    `${course.lesson_count} lessons`,
    course.duration_minutes > 0
      ? formatDurationLabel(course.duration_minutes * 60)
      : null,
  ]
    .filter(Boolean)
    .join(", ");
}

function AccessTag({ course }) {
  if (course.unlock_rule === "free")
    return <span className="tag tag-ok self-start">Free</span>;
  if (course.is_accessible)
    return <span className="tag tag-gold self-start">You have access</span>;
  return <span className="tag self-start">Subscription</span>;
}

function FeaturedCourses({ loading, error, retry, featured, others }) {
  return (
    <section className="wrap pb-24 lg:pb-28" aria-labelledby="start-heading">
      <div className="flex flex-wrap items-end justify-between gap-4 pb-9">
        <h2 id="start-heading" className="h2">
          Start with a course.
        </h2>
        <Link to="/courses" className="btn btn-line">
          Browse courses
        </Link>
      </div>

      {loading ? (
        <Skeleton className="h-[460px] w-full" />
      ) : error ? (
        <ErrorState error={error} onRetry={retry} />
      ) : !featured ? (
        <EmptyState
          title="No courses published yet"
          description="Courses will appear here as soon as an instructor publishes them."
        />
      ) : (
        <div className="grid gap-12 lg:grid-cols-[8fr_4fr]">
          <Link
            to={`/courses/${featured.slug}`}
            className="navy-surface relative flex min-h-[380px] flex-col justify-between overflow-hidden rounded-[14px] p-8 lg:min-h-[460px] lg:p-10"
          >
            <span
              aria-hidden="true"
              className="pointer-events-none absolute -bottom-8 right-9 select-none font-serif text-[200px] leading-none tracking-tight text-white/[0.06] lg:text-[280px]"
            >
              {featured.lesson_count}
            </span>
            <span className="tag tag-gold self-start">
              {featured.unlock_rule === "free" ? "Free" : "Featured"}
            </span>
            <div className="relative flex max-w-[520px] flex-col gap-4">
              <h3 className="d2 !text-[40px] sm:!text-[52px]">
                {featured.title}
              </h3>
              <p className="text-[17px] leading-relaxed text-[#B4BED6]">
                {truncate(featured.summary || featured.subtitle || "", 180)}
              </p>
              <p className="mono cap pt-2 !text-[#B4BED6]">
                {[courseMeta(featured), featured.instructor?.name]
                  .filter(Boolean)
                  .join(", ")}
              </p>
            </div>
          </Link>

          <div className="rows flex flex-col">
            {others.map((course, index) => (
              <Link
                key={course.id}
                to={`/courses/${course.slug}`}
                className={`flex flex-col gap-2 ${index === 0 ? "pb-7" : "py-7"} ${index === others.length - 1 ? "pb-2" : ""}`}
              >
                <AccessTag course={course} />
                <h3 className="h4">{course.title}</h3>
                <p className="small">
                  {truncate(course.summary || course.subtitle || "", 90)}
                </p>
                <span className="flex items-center justify-between gap-3">
                  <span className="mono cap">{courseMeta(course)}</span>
                  <span className="font-medium num">
                    {course.unlock_rule === "free"
                      ? "Free"
                      : formatPrice(course.price)}
                  </span>
                </span>
              </Link>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

/* -------------------------------------------------------------------------- */
function planPerks(plan) {
  const perks = [];
  perks.push(
    plan.is_all_access
      ? "Every course, including new ones"
      : `${plan.course_count} course${plan.course_count === 1 ? "" : "s"} included`,
  );
  if (plan.description) perks.push(plan.description);
  return perks;
}

function Plans({ plans }) {
  const list = Array.isArray(plans) ? plans.slice(0, 3) : [];
  if (list.length === 0) return null;

  return (
    <section className="bg-sunken py-24 lg:py-28" aria-labelledby="plans-heading">
      <div className="wrap">
        <div className="flex max-w-[640px] flex-col gap-4 pb-12">
          <h2 id="plans-heading" className="h2">
            Choose how long you need.
          </h2>
          <p className="body">
            One payment. Access runs to the end of your term and does not renew
            by itself.
          </p>
        </div>

        <div className="grid gap-5 md:grid-cols-3">
          {list.map((plan) => {
            const highlight = plan.is_featured;
            return (
              <div
                key={plan.id}
                className={`flex flex-col gap-6 rounded-[14px] p-8 lg:p-9 ${highlight ? "navy-surface" : "card"}`}
              >
                <div className="flex flex-col gap-2">
                  <div className="flex items-center justify-between gap-3">
                    <h3 className="h3">{plan.name}</h3>
                    {plan.is_all_access && (
                      <span className="tag tag-gold">All courses</span>
                    )}
                  </div>
                  <span
                    className={`text-sm ${highlight ? "text-[#B4BED6]" : "small"}`}
                  >
                    {plan.duration_days} days of access
                  </span>
                </div>
                <span className="font-serif text-[48px] leading-none tracking-tight num lg:text-[56px]">
                  {formatPrice(plan.price, plan.currency)}
                </span>
                <hr
                  className="m-0 h-px border-0"
                  style={{
                    background: highlight ? "rgba(255,255,255,.14)" : undefined,
                  }}
                />
                <ul
                  className={`m-0 flex flex-1 list-none flex-col gap-3 p-0 text-[15px] ${highlight ? "text-[#D5DBEA]" : "text-ink2"}`}
                >
                  {planPerks(plan).map((perk) => (
                    <li key={perk} className="flex gap-3">
                      <Icon
                        name="check"
                        className={`i-sm mt-1 ${highlight ? "text-[#5FCB9D]" : "text-ok"}`}
                      />
                      {perk}
                    </li>
                  ))}
                </ul>
                <Link
                  to="/subscription"
                  className={`btn btn-lg btn-block ${highlight ? "btn-gold" : "btn-line"}`}
                >
                  Choose {plan.name}
                </Link>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------------- */
function ClosingBand({ isAuthenticated }) {
  return (
    <section className="navy-surface">
      <div className="wrap flex flex-col gap-8 py-20 md:flex-row md:items-center md:justify-between lg:py-24">
        <h2 className="h2 max-w-[640px]">
          {isAuthenticated
            ? "Pick up where you left off."
            : "Watch the first lesson before you decide."}
        </h2>
        <Link
          to={isAuthenticated ? "/dashboard" : "/register"}
          className="btn btn-gold btn-lg self-start md:self-auto"
        >
          {isAuthenticated ? "Go to my dashboard" : "Start free"}
        </Link>
      </div>
    </section>
  );
}
