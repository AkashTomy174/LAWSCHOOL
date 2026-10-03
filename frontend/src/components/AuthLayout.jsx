import Icon from "./Icon";

const POINTS = [
  "Recorded lectures that remember where you stopped",
  "Quizzes graded on the server, with an explanation for every answer",
  "Progress and rankings that follow you across devices",
];

/**
 * Shared frame for sign-in, registration and account recovery.
 *
 * A navy brand panel beside the form on wide screens; on phones only the form is
 * shown, so the first thing a student sees is the field they need to fill in.
 */
export default function AuthLayout({ children }) {
  return (
    <div className="grid min-h-[calc(100dvh-73px)] lg:grid-cols-[5fr_6fr]">
      <aside
        aria-hidden="true"
        className="navy-surface hidden flex-col justify-between p-14 lg:flex"
      >
        <h2 className="d2 max-w-[460px] !text-[52px]">
          Law, taught by people who <em>practise</em> it.
        </h2>
        <ul className="m-0 flex max-w-[460px] list-none flex-col gap-4 p-0">
          {POINTS.map((point) => (
            <li
              key={point}
              className="flex gap-3 border-t border-white/10 pt-4 text-[15px] text-[#B4BED6]"
            >
              <Icon name="check" className="i-sm mt-1 text-[#D4AF37]" />
              {point}
            </li>
          ))}
        </ul>
      </aside>

      <section className="flex items-center justify-center px-4 py-12 sm:px-8">
        <div className="w-full max-w-[420px]">{children}</div>
      </section>
    </div>
  );
}
