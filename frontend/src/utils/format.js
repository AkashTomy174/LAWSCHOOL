/**
 * Shared formatting helpers.
 *
 * Kept as pure functions so they are unit-testable in isolation and reusable by
 * any component without pulling in context or state.
 */

/** Format a duration in seconds as `m:ss` or `h:mm:ss`. */
export function formatDuration(totalSeconds) {
  const seconds = Math.max(0, Math.floor(Number(totalSeconds) || 0));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;

  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  }
  return `${minutes}:${String(secs).padStart(2, "0")}`;
}

/** Human wording for a lesson/video length. */
export function formatDurationLabel(totalSeconds) {
  const seconds = Math.max(0, Number(totalSeconds) || 0);
  // Floor rather than round: `Math.round(30 / 60)` is 1, which would advertise a
  // 30-second clip as "1 min". Under-reporting is the safer direction for a
  // duration label. Exactly zero is treated as unknown rather than "< 1 min".
  const minutes = Math.floor(seconds / 60);

  if (minutes < 1) return "< 1 min";
  if (minutes < 60) return `${minutes} min`;

  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${hours} hr ${rest} min` : `${hours} hr`;
}

/** Format an amount as `INR 1,999.00` (en-IN grouping). */
export function formatMoney(amount, currency = "INR") {
  const value = Number(amount) || 0;
  return `${currency} ${value.toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

/**
 * Price for catalogue display: `₹1,999` (whole rupees drop the decimals).
 * Billing and receipts keep the explicit `formatMoney` form.
 */
export function formatPrice(amount, currency = "INR") {
  const value = Number(amount) || 0;
  const symbol = currency === "INR" ? "₹" : `${currency} `;
  return `${symbol}${value.toLocaleString("en-IN", {
    minimumFractionDigits: Number.isInteger(value) ? 0 : 2,
    maximumFractionDigits: 2,
  })}`;
}

/** Format paise (integer) the same way, for Razorpay payloads. */
export function formatPaise(paise, currency = "INR") {
  return formatMoney(Number(paise) / 100, currency);
}

export function formatDate(
  value,
  options = { day: "2-digit", month: "short", year: "numeric" },
) {
  if (!value) return "\u2014";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "\u2014";
  return date.toLocaleDateString("en-IN", options);
}

export function formatDateTime(value) {
  if (!value) return "\u2014";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "\u2014";
  return date.toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** "3 days ago" style output for activity feeds. */
export function formatRelative(value) {
  if (!value) return "\u2014";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "\u2014";

  const diffSeconds = Math.round((date.getTime() - Date.now()) / 1000);
  const units = [
    ["year", 60 * 60 * 24 * 365],
    ["month", 60 * 60 * 24 * 30],
    ["day", 60 * 60 * 24],
    ["hour", 60 * 60],
    ["minute", 60],
  ];
  const formatter = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

  for (const [unit, seconds] of units) {
    if (Math.abs(diffSeconds) >= seconds) {
      return formatter.format(Math.round(diffSeconds / seconds), unit);
    }
  }
  return "just now";
}

/** Percentage as a whole number for progress bars and score chips. */
export function formatPercent(value) {
  const number = Number(value);
  if (Number.isNaN(number)) return "0%";
  return `${Math.round(number)}%`;
}

export function truncate(text, max = 140) {
  if (!text) return "";
  return text.length <= max
    ? text
    : `${text.slice(0, max - 1).trimEnd()}\u2026`;
}

export function initials(name, fallback = "?") {
  if (!name) return fallback;
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toUpperCase())
    .join("");
}

/** Days remaining, phrased for the subscription card. */
export function formatDaysRemaining(days) {
  const value = Number(days);
  if (Number.isNaN(value)) return "—";
  if (value <= 0) return "Expired";
  if (value === 1) return "1 day left";
  return `${value} days left`;
}
