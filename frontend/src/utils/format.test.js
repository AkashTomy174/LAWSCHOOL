import { describe, expect, it } from "vitest";

import {
  formatDaysRemaining,
  formatDuration,
  formatDurationLabel,
  formatMoney,
  formatPrice,
  formatPaise,
  formatPercent,
  initials,
  truncate,
} from "./format";

/**
 * Unit tests for the formatting helpers.
 *
 * These are pure functions used across every page, so a regression here shows up
 * everywhere — worth pinning down precisely.
 */
describe("formatDuration", () => {
  it("formats sub-hour durations as m:ss", () => {
    expect(formatDuration(0)).toBe("0:00");
    expect(formatDuration(9)).toBe("0:09");
    expect(formatDuration(65)).toBe("1:05");
    expect(formatDuration(600)).toBe("10:00");
  });

  it("formats hour-plus durations as h:mm:ss", () => {
    expect(formatDuration(3600)).toBe("1:00:00");
    expect(formatDuration(3661)).toBe("1:01:01");
  });

  it("treats invalid input as zero rather than rendering NaN", () => {
    expect(formatDuration(undefined)).toBe("0:00");
    expect(formatDuration(null)).toBe("0:00");
    expect(formatDuration("abc")).toBe("0:00");
  });

  it("clamps negative values", () => {
    expect(formatDuration(-30)).toBe("0:00");
  });
});

describe("formatDurationLabel", () => {
  it("describes minutes and hours in words", () => {
    expect(formatDurationLabel(30)).toBe("< 1 min");
    expect(formatDurationLabel(600)).toBe("10 min");
    expect(formatDurationLabel(3600)).toBe("1 hr");
    expect(formatDurationLabel(5400)).toBe("1 hr 30 min");
  });
});

describe("formatMoney", () => {
  it("uses Indian digit grouping and two decimals", () => {
    expect(formatMoney(1999)).toBe("INR 1,999.00");
    expect(formatMoney(123456.5)).toBe("INR 1,23,456.50");
  });

  it("handles zero and invalid input", () => {
    expect(formatMoney(0)).toBe("INR 0.00");
    expect(formatMoney(undefined)).toBe("INR 0.00");
  });

  it("honours a non-default currency", () => {
    expect(formatMoney(10, "USD")).toBe("USD 10.00");
  });
});

describe("formatPaise", () => {
  it("converts the smallest currency unit correctly", () => {
    // Razorpay charges in paise; a wrong conversion here is a real money bug.
    expect(formatPaise(199900)).toBe("INR 1,999.00");
    expect(formatPaise(100)).toBe("INR 1.00");
  });
});

describe("formatPercent", () => {
  it("rounds to a whole number", () => {
    expect(formatPercent(66.67)).toBe("67%");
    expect(formatPercent("50.4")).toBe("50%");
  });

  it("defaults to 0% for unusable values", () => {
    expect(formatPercent(null)).toBe("0%");
    expect(formatPercent("nope")).toBe("0%");
  });
});

describe("truncate", () => {
  it("leaves short text untouched", () => {
    expect(truncate("short", 20)).toBe("short");
  });

  it("adds an ellipsis when cutting", () => {
    const result = truncate("a".repeat(50), 10);
    expect(result.length).toBeLessThanOrEqual(10);
    expect(result.endsWith("\u2026")).toBe(true);
  });
});

describe("initials", () => {
  it("uses the first letters of the first two words", () => {
    expect(initials("Rahul Sharma")).toBe("RS");
    expect(initials("Meera")).toBe("M");
  });

  it("falls back when there is no name", () => {
    expect(initials("")).toBe("?");
    expect(initials(null, "X")).toBe("X");
  });
});

describe("formatDaysRemaining", () => {
  it("describes expiry in plain language", () => {
    expect(formatDaysRemaining(0)).toBe("Expired");
    expect(formatDaysRemaining(-5)).toBe("Expired");
    expect(formatDaysRemaining(1)).toBe("1 day left");
    expect(formatDaysRemaining(30)).toBe("30 days left");
  });
});

describe("formatPrice", () => {
  it("shows whole rupees without decimals and keeps paise when present", () => {
    expect(formatPrice("1999.00")).toBe("₹1,999");
    expect(formatPrice(123456)).toBe("₹1,23,456");
    expect(formatPrice("499.50")).toBe("₹499.50");
  });

  it("falls back to the currency code for non-rupee prices", () => {
    expect(formatPrice(10, "USD")).toBe("USD 10");
  });
});
