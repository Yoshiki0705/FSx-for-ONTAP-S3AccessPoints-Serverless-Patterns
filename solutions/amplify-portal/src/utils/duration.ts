/**
 * Human-readable labels for the ISO-8601 retention periods the SnapLock forms use.
 *
 * These were 28 hardcoded Japanese strings across three selects, which meant the
 * retention a user picked was unreadable in seven of the portal's eight locales.
 * Giving each option its own translation key would have been 28 keys for what is
 * really a number and a unit, so the labels are composed from a handful of
 * patterns instead.
 *
 * The patterns live in the locale files rather than here because spacing and
 * plurals are language decisions: Japanese writes "30日" with no space, English
 * needs "30 days" with one, and the singular differs in one and not the other.
 */

import type { TranslationKeys } from "../i18n";

/**
 * The translation function, typed against the real key union rather than
 * `string`. A wider signature compiles here but not at the call site, and it
 * would also let a typo'd key through — the point of the union is that a key
 * which does not exist is a build error rather than a blank label.
 */
type Translate = (key: TranslationKeys) => string;

const fill = (template: string, values: Record<string, string | number>): string =>
  Object.keys(values).reduce(
    (text, key) => text.split(`{${key}}`).join(String(values[key])),
    template
  );

/**
 * Turn an ISO-8601 day period into a label.
 *
 * `P0D` means no limit rather than zero days, and "custom" is the sentinel the
 * form uses for the free-entry row, so both are handled before the arithmetic.
 * Anything unrecognised is returned unchanged: showing the raw period is more
 * useful than an empty option, and it makes a new value visible instead of
 * silently blank.
 */
export function durationLabel(period: string, t: Translate): string {
  if (period === "custom") return t("durationCustom");

  const match = /^P(\d+)D$/.exec(period);
  if (!match) return period;

  const days = Number(match[1]);
  if (!Number.isFinite(days)) return period;
  if (days === 0) return t("durationUnlimited");

  // Whole years read better than three-digit day counts, and every year-scale
  // option in these forms is an exact multiple.
  if (days % 365 === 0) {
    const years = days / 365;
    return fill(t(years === 1 ? "durationYear" : "durationYears"), { n: years });
  }

  // A month equivalent is worth showing for the mid-range options, because 90
  // days is easier to reason about as a quarter. Strictly above 30, since the
  // annotation tells you nothing for exactly one month and the plural pattern
  // would read "1 months".
  if (days > 30 && days % 30 === 0) {
    return fill(t("durationDaysWithMonths"), { n: days, m: days / 30 });
  }

  return fill(t(days === 1 ? "durationDay" : "durationDays"), { n: days });
}

/** "1 day to 30 years", for the hints under the selects. */
export function durationRange(fromPeriod: string, toPeriod: string, t: Translate): string {
  return fill(t("durationRange"), {
    from: durationLabel(fromPeriod, t),
    to: durationLabel(toPeriod, t),
  });
}
