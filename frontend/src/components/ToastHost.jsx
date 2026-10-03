import { useUI } from "../context/UIContext";
import Icon from "./Icon";

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
    info: "border-line-strong",
    success: "border-ok",
    error: "border-bad",
    warning: "border-gold",
  };

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-0 z-50 flex flex-col items-center gap-2 px-4 pb-4">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          role={toast.tone === "error" ? "alert" : "status"}
          aria-live={toast.tone === "error" ? "assertive" : "polite"}
          className={`pointer-events-auto card lift w-full max-w-md px-4 py-3 text-sm text-ink ${
            tones[toast.tone] || tones.info
          }`}
        >
          <div className="flex items-start justify-between gap-3">
            <span>{toast.message}</span>
            <button
              type="button"
              onClick={() => dismissToast(toast.id)}
              className="-m-2 flex h-11 w-11 flex-none items-center justify-center rounded-lg text-ink3 hover:bg-sunken hover:text-ink"
              aria-label="Dismiss notification"
            >
              <Icon name="x" className="i-sm" />
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
