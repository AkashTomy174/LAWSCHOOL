import { useUI } from "../context/UIContext";

/**
 * Toast host.
 *
 * Rendered once near the app root. `role="status"` + `aria-live="polite"` means
 * routine messages are announced without interrupting the student, while an error
 * escalates to `assertive` because it usually needs attention.
 */
export default function ToastHost() {
  const { toasts, dismissToast } = useUI();

  if (!toasts.length) return null;

  const tones = {
    info: "border-[var(--color-border-subtle)] text-parchment",
    success: "border-emerald-500/40 text-emerald-100",
    error: "border-red-500/40 text-red-100",
    warning: "border-amber-500/40 text-amber-100",
  };

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-0 z-50 flex flex-col items-center gap-2 px-4 pb-4">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          role={toast.tone === "error" ? "alert" : "status"}
          aria-live={toast.tone === "error" ? "assertive" : "polite"}
          className={`pointer-events-auto panel w-full max-w-md px-4 py-3 text-sm shadow-lg ${
            tones[toast.tone] || tones.info
          }`}
        >
          <div className="flex items-start justify-between gap-3">
            <span>{toast.message}</span>
            <button
              type="button"
              onClick={() => dismissToast(toast.id)}
              className="text-white/50 hover:text-white"
              aria-label="Dismiss notification"
            >
              {"\u2715"}
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
