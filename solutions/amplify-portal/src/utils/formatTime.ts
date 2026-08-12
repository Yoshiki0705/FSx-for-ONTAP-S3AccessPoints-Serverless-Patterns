/**
 * Timestamps for listings, in the portal's language.
 *
 * A listing answers "has this changed lately?" more often than "what date was
 * that?", and a bare date answers the first question poorly: 2026-08-04 and
 * 2026-07-04 look alike at a glance while "3 days ago" and "last month" do not.
 * Far enough back the reverse holds, so the relative phrase is used only inside a
 * window and the date takes over beyond it.
 *
 * Both forms are produced here because a row shows the short one and keeps the
 * exact instant in its tooltip; the two must not disagree about which value they
 * describe.
 */

/** Units the relative phrase may use, largest first. */
const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["day", 86_400_000],
  ["hour", 3_600_000],
  ["minute", 60_000],
  ["second", 1_000],
];

/** How far from now a relative phrase stays more informative than a date. */
const RELATIVE_WINDOW_MS = 7 * 86_400_000;

/**
 * The instant as a short phrase: "3 days ago" when recent, a date when not.
 *
 * `now` is a parameter so a test can state the instant it is comparing against
 * rather than depend on the clock.
 */
export function formatRelativeTime(
  iso: string | null | undefined,
  locale: string,
  now: number = Date.now()
): string {
  if (!iso) return "-";
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return "-";

  const elapsed = then - now; // negative in the past, which is the usual case
  if (Math.abs(elapsed) > RELATIVE_WINDOW_MS) {
    return new Date(then).toLocaleDateString(locale);
  }
  // Falling back to the smallest unit rather than to a date: inside the window,
  // an elapsed time under a second is "now", not an anonymous calendar day.
  const [unit, span] = UNITS.find(([, ms]) => Math.abs(elapsed) >= ms) ?? UNITS[UNITS.length - 1];
  return new Intl.RelativeTimeFormat(locale, { numeric: "auto" }).format(
    Math.round(elapsed / span),
    unit
  );
}

/** The instant in full, for the tooltip beside the short phrase. */
export function formatAbsoluteTime(iso: string | null | undefined, locale: string): string {
  if (!iso) return "-";
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return "-";
  return new Date(then).toLocaleString(locale);
}
