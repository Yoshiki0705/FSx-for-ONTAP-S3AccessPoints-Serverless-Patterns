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

  // Hours and minutes, which arrived with the FlexGroup rebalance runtimes. The
  // fallback below returns the period unchanged -- readable to somebody who knows
  // ISO-8601 and to nobody else -- so the select offered ONTAP's default as "PT6H"
  // and then, once 30 minutes led the list, as "PT30M".
  //
  // The `T` is required rather than optional: `P30M` is thirty months and `PT30M` is
  // thirty minutes, and the two differ by a factor of about forty thousand.
  const time = /^PT(?:(\d+)H)?(?:(\d+)M)?$/.exec(period);
  if (time && (time[1] || time[2])) {
    const hours = Number(time[1] ?? 0);
    const minutes = Number(time[2] ?? 0);
    if (hours && !minutes) return fill(t(hours === 1 ? "durationHour" : "durationHours"), { n: hours });
    if (minutes && !hours) return fill(t(minutes === 1 ? "durationMinute" : "durationMinutes"), { n: minutes });
    // A mixed value is a clock, for the same reason an elapsed time is one below:
    // composing two translated patterns reads worse than "1:30" in every language.
    return elapsedLabel(period);
  }

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

/**
 * An elapsed ISO-8601 duration as a clock: `PT1M32S` becomes "1:32".
 *
 * Separate from `durationLabel` because it answers a different question. That one
 * names a retention period in whole units, which is prose and belongs in the locale.
 * This one is a running total in mixed units, which nobody reads as prose and which
 * needs no translation as a clock. ONTAP reports a rebalance's runtime this way, and
 * the panel was showing the string `PT1M32S`.
 *
 * Anything unrecognised is returned unchanged, for the same reason as above: a new
 * shape should be visible rather than blank.
 */
export function elapsedLabel(runtime: string): string {
  const match = /^PT(?=\d)(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$/.exec(runtime);
  if (!match) return runtime;
  const [hours, minutes, seconds] = [match[1], match[2], match[3]].map((part) => Number(part ?? 0));
  const pad = (value: number) => String(value).padStart(2, "0");
  return hours > 0 ? `${hours}:${pad(minutes)}:${pad(seconds)}` : `${minutes}:${pad(seconds)}`;
}

/** "1 day to 30 years", for the hints under the selects. */
export function durationRange(fromPeriod: string, toPeriod: string, t: Translate): string {
  return fill(t("durationRange"), {
    from: durationLabel(fromPeriod, t),
    to: durationLabel(toPeriod, t),
  });
}
