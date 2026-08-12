import { describe, it, expect } from "vitest";
import { formatAbsoluteTime, formatRelativeTime } from "../../src/utils/formatTime";

/** A fixed instant, so the assertions do not depend on the clock. */
const NOW = Date.parse("2026-08-11T12:00:00Z");

/** `NOW` shifted by a number of milliseconds, as the listing would report it. */
const ago = (ms: number) => new Date(NOW - ms).toISOString();

const SECOND = 1_000;
const MINUTE = 60 * SECOND;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

describe("formatRelativeTime", () => {
  it("reports a missing or unparseable timestamp as absent", () => {
    expect(formatRelativeTime(null, "en", NOW)).toBe("-");
    expect(formatRelativeTime(undefined, "en", NOW)).toBe("-");
    expect(formatRelativeTime("", "en", NOW)).toBe("-");
    expect(formatRelativeTime("not a date", "en", NOW)).toBe("-");
  });

  it("chooses the largest unit that fits", () => {
    expect(formatRelativeTime(ago(3 * DAY), "en", NOW)).toBe("3 days ago");
    expect(formatRelativeTime(ago(5 * HOUR), "en", NOW)).toBe("5 hours ago");
    expect(formatRelativeTime(ago(20 * MINUTE), "en", NOW)).toBe("20 minutes ago");
    expect(formatRelativeTime(ago(30 * SECOND), "en", NOW)).toBe("30 seconds ago");
  });

  it("falls back to the smallest unit rather than to a date", () => {
    // Inside the window, an elapsed time under a second is "now" — not an
    // anonymous calendar day, which is what a date would give.
    expect(formatRelativeTime(ago(10), "en", NOW)).toBe("now");
  });

  it("gives a date once the relative phrase stops being informative", () => {
    const old = formatRelativeTime(ago(400 * DAY), "en", NOW);
    expect(old).not.toMatch(/ago/);
    expect(old).toContain("2025");
  });

  it("switches from phrase to date at the window edge", () => {
    expect(formatRelativeTime(ago(6 * DAY), "en", NOW)).toMatch(/ago/);
    expect(formatRelativeTime(ago(8 * DAY), "en", NOW)).not.toMatch(/ago/);
  });

  it("speaks the locale it is given", () => {
    expect(formatRelativeTime(ago(3 * DAY), "ja", NOW)).toBe("3 日前");
    expect(formatRelativeTime(ago(3 * DAY), "de", NOW)).toBe("vor 3 Tagen");
  });

  it("handles a timestamp ahead of now without breaking", () => {
    // Clock skew between the file system and the browser can produce one.
    expect(formatRelativeTime(new Date(NOW + 2 * HOUR).toISOString(), "en", NOW)).toBe(
      "in 2 hours"
    );
  });
});

describe("formatAbsoluteTime", () => {
  it("reports a missing or unparseable timestamp as absent", () => {
    expect(formatAbsoluteTime(null, "en")).toBe("-");
    expect(formatAbsoluteTime("nope", "en")).toBe("-");
  });

  it("keeps the time of day the short form drops", () => {
    const full = formatAbsoluteTime("2026-08-11T12:34:56Z", "en");
    expect(full).toMatch(/2026/);
    expect(full).toMatch(/\d{1,2}:\d{2}/);
  });
});
