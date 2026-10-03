import { Link } from "react-router-dom";

/** Navy footer shared by every page that shows site navigation. */
export default function Footer() {
  return (
    <footer className="navy-surface border-t border-white/10">
      <div className="wrap flex flex-col gap-6 py-9 md:flex-row md:items-center md:justify-between">
        <Link to="/" className="brand text-[22px] !text-[#EEF1F8]">
          <span className="brand-mark !bg-navy2">§</span>LawSchool
        </Link>

        <nav
          aria-label="Footer"
          className="flex flex-wrap gap-x-6 gap-y-2 text-sm text-[#B4BED6]"
        >
          <Link to="/courses" className="py-2 hover:text-white">
            Courses
          </Link>
          <Link to="/subscription" className="py-2 hover:text-white">
            Plans
          </Link>
          <Link to="/leaderboard" className="py-2 hover:text-white">
            Leaderboard
          </Link>
          <a
            href="mailto:support@lawschool.local"
            className="py-2 hover:text-white"
          >
            Support
          </a>
        </nav>

        <p className="cap !text-[#8E9AB8]">
          &copy; {new Date().getFullYear()} LawSchool. Course content is
          protected and streamed under licence.
        </p>
      </div>
    </footer>
  );
}
