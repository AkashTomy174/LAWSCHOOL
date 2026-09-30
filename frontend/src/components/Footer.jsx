import { Link } from "react-router-dom";

export default function Footer() {
  return (
    <footer className="mt-20 border-t border-[var(--color-border-subtle)] bg-[rgba(6,11,26,0.6)]">
      <div className="mx-auto grid w-full max-w-7xl gap-8 px-4 py-10 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <p className="font-display text-lg text-gold-300">
            Law<span className="text-parchment">School</span>
          </p>
          <p className="mt-3 text-sm text-white/55">
            Structured legal education: expert-led video courses, graded
            assessments and measurable progress.
          </p>
        </div>

        <nav aria-label="Learn">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-white/70">
            Learn
          </h2>
          <ul className="space-y-2 text-sm text-white/55">
            <li>
              <Link to="/courses" className="hover:text-gold-300">
                All courses
              </Link>
            </li>
            <li>
              <Link to="/subscription" className="hover:text-gold-300">
                Plans &amp; pricing
              </Link>
            </li>
            <li>
              <Link to="/leaderboard" className="hover:text-gold-300">
                Leaderboard
              </Link>
            </li>
          </ul>
        </nav>

        <nav aria-label="Account">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-white/70">
            Account
          </h2>
          <ul className="space-y-2 text-sm text-white/55">
            <li>
              <Link to="/dashboard" className="hover:text-gold-300">
                Dashboard
              </Link>
            </li>
            <li>
              <Link to="/profile" className="hover:text-gold-300">
                Profile
              </Link>
            </li>
            <li>
              <Link to="/login" className="hover:text-gold-300">
                Sign in
              </Link>
            </li>
          </ul>
        </nav>

        <div>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-white/70">
            Support
          </h2>
          <p className="text-sm text-white/55">
            Payment or access issue? Email{" "}
            <a
              href="mailto:support@lawschool.local"
              className="text-gold-300 hover:underline"
            >
              support@lawschool.local
            </a>{" "}
            with your order id.
          </p>
        </div>
      </div>

      <div className="border-t border-[var(--color-border-subtle)] px-4 py-4">
        <p className="mx-auto w-full max-w-7xl text-xs text-white/40">
          &copy; {new Date().getFullYear()} LawSchool. All rights reserved.
          Course content is protected and streamed under licence.
        </p>
      </div>
    </footer>
  );
}
