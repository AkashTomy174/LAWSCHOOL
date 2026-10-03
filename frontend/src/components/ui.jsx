/**
 * Shared presentational components.
 *
 * Grouped in one module to keep the import graph simple; each export is small,
 * stateless and purely visual. Anything with data-fetching behaviour lives in its
 * own file instead.
 */

export function Spinner({ size = 20, className = "" }) {
  return (
    <span
      className={`inline-block animate-spin rounded-full border-2 border-current border-t-transparent ${className}`}
      style={{ width: size, height: size }}
      role="status"
      aria-label="Loading"
    />
  );
}

export function Button({
  children,
  variant = "primary",
  loading = false,
  className = "",
  type = "button",
  disabled = false,
  ...rest
}) {
  const classes = [
    "btn",
    variant === "primary" ? "btn-primary" : "btn-ghost",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <button
      type={type}
      className={classes}
      disabled={disabled || loading}
      // Announce the busy state to assistive tech, not just visually.
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading && <Spinner size={16} />}
      {children}
    </button>
  );
}

export function Panel({ children, className = "", interactive = false }) {
  return (
    <div
      className={`panel ${interactive ? "panel-interactive" : ""} ${className}`}
    >
      {children}
    </div>
  );
}

export function Badge({ children, tone = "gold", className = "" }) {
  const tones = {
    gold: "tag-gold",
    success: "tag-ok",
    danger: "tag-bad",
    warning: "tag-gold",
    muted: "",
  };
  return <span className={`tag ${tones[tone] ?? ""} ${className}`}>{children}</span>;
}

/** Progress bar with ARIA values so screen readers announce the number. */
export function ProgressBar({ value = 0, label, className = "" }) {
  const percent = Math.max(0, Math.min(100, Number(value) || 0));
  return (
    <div className={className}>
      {label && (
        <div className="mb-1.5 flex items-center justify-between text-xs text-ink3">
          <span>{label}</span>
          <span className="mono">{Math.round(percent)}%</span>
        </div>
      )}
      <div
        className="bar"
        role="progressbar"
        aria-valuenow={Math.round(percent)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label || "Progress"}
      >
        <i style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}

/**
 * Loading skeleton.
 *
 * A skeleton rather than a spinner: it preserves layout so the page does not jump
 * when data arrives, which is very noticeable on mobile.
 */
export function Skeleton({ className = "", count = 1 }) {
  return (
    <>
      {Array.from({ length: count }).map((_, index) => (
        <div
          key={index}
          className={`animate-pulse rounded-lg bg-sunken ${className}`}
          aria-hidden="true"
        />
      ))}
    </>
  );
}

export function EmptyState({ title, description, action }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 px-6 py-14 text-center">
      <h3 className="h4">{title}</h3>
      {description && <p className="body max-w-md">{description}</p>}
      {action}
    </div>
  );
}

/**
 * Inline error with an optional retry.
 *
 * `role="alert"` makes it announced immediately — important when a submission
 * would otherwise fail silently for a screen-reader user.
 */
export function ErrorState({ error, onRetry, className = "" }) {
  if (!error) return null;
  const message = error.message || "Something went wrong.";
  return (
    <div
      role="alert"
      className={`flex rounded-[10px] border border-bad bg-bad-bg px-4 py-3 text-sm text-ink ${className}`}
    >
      <div className="flex w-full flex-wrap items-center justify-between gap-3">
        <span>{message}</span>
        {onRetry && (
          <Button
            variant="ghost"
            onClick={onRetry}
            className="!min-h-0 !px-3 !py-1 text-xs"
          >
            Try again
          </Button>
        )}
      </div>
    </div>
  );
}

/** Field-level validation message, linked to its input via `aria-describedby`. */
export function FieldError({ id, children }) {
  if (!children) return null;
  return (
    <p id={id} role="alert" className="mt-1 text-[13px] text-bad">
      {children}
    </p>
  );
}

export function TextField({
  label,
  id,
  error,
  hint,
  className = "",
  as = "input",
  ...rest
}) {
  const Element = as;
  const describedBy = [error ? `${id}-error` : null, hint ? `${id}-hint` : null]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={className}>
      {label && (
        <label htmlFor={id} className="label">
          {label}
        </label>
      )}
      <Element
        id={id}
        className="input"
        aria-invalid={error ? "true" : undefined}
        aria-describedby={describedBy || undefined}
        {...rest}
      />
      {hint && (
        <p id={`${id}-hint`} className="cap mt-1">
          {hint}
        </p>
      )}
      <FieldError id={`${id}-error`}>{error}</FieldError>
    </div>
  );
}

export function Avatar({ user, size = 36, className = "" }) {
  const name = user?.name || user?.email || "?";
  const initial = name.trim().charAt(0).toUpperCase() || "?";

  if (user?.avatar) {
    return (
      <img
        src={user.avatar}
        alt={`${name}'s avatar`}
        width={size}
        height={size}
        className={`rounded-full object-cover ${className}`}
        style={{ width: size, height: size }}
      />
    );
  }

  return (
    <span
      className={`avatar ${className}`}
      style={{ width: size, height: size, fontSize: size * 0.38 }}
      aria-hidden="true"
    >
      {initial}
    </span>
  );
}

export function Callout({ tone = "info", title, children }) {
  const tones = {
    info: "border-line bg-card",
    warning: "border-gold bg-gold-tint",
    danger: "border-bad bg-bad-bg",
    success: "border-ok bg-ok-bg",
  };
  return (
    <div className={`rounded-[10px] border px-4 py-3 ${tones[tone] || tones.info}`}>
      {title && <p className="mb-1 font-medium text-ink">{title}</p>}
      <div className="text-sm text-ink2">{children}</div>
    </div>
  );
}
