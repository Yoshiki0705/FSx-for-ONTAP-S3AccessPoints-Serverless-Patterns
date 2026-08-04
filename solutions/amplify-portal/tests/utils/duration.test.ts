/**
 * The duration formatter replaced 28 hardcoded Japanese labels, so the risk it
 * introduces is a label that is plausible but wrong — "365 days (12 months)"
 * instead of "1 year", or a silent blank for a period nobody anticipated.
 */

import { describe, it, expect } from "vitest";
import { durationLabel, durationRange } from "../../src/utils/duration";
import { ja } from "../../src/i18n/locales/ja";
import { en } from "../../src/i18n/locales/en";

// Stand in for the real hook, reading straight from a locale file so the test
// exercises the actual patterns rather than fixtures that could drift from them.
const translator = (locale: Record<string, string>) =>
  ((key: string) => locale[key] ?? key) as Parameters<typeof durationLabel>[1];

const t = translator(ja as unknown as Record<string, string>);
const tEn = translator(en as unknown as Record<string, string>);

describe("durationLabel", () => {
  it("renders every period the SnapLock forms offer", () => {
    // The full set from VolumeManager, so a period losing its label shows up
    // here rather than as a blank option in the UI.
    expect(
      [
        "P0D",
        "P1D",
        "P7D",
        "P30D",
        "P90D",
        "P180D",
        "P365D",
        "P730D",
        "P1825D",
        "P3650D",
        "P10950D",
        "custom",
      ].map((p) => durationLabel(p, tEn))
    ).toEqual([
      "No limit",
      "1 day",
      "7 days",
      // Deliberately not "30 days (1 month)", which the original Japanese label
      // had: the annotation adds nothing for exactly one month, and the plural
      // pattern would render it "1 months" in English.
      "30 days",
      "90 days (3 months)",
      "180 days (6 months)",
      "1 year",
      "2 years",
      "5 years",
      "10 years",
      "30 years",
      "Custom...",
    ]);
  });

  it("prefers whole years over large day counts", () => {
    // "365 days (12 months)" is accurate and useless.
    expect(durationLabel("P365D", tEn)).toBe("1 year");
    expect(durationLabel("P3650D", tEn)).toBe("10 years");
  });

  it("treats P0D as no limit rather than zero days", () => {
    expect(durationLabel("P0D", tEn)).toBe("No limit");
    expect(durationLabel("P0D", t)).toBe("制限なし");
  });

  it("uses the singular where the language has one", () => {
    expect(durationLabel("P1D", tEn)).toBe("1 day");
    expect(durationLabel("P365D", tEn)).toBe("1 year");
    // Japanese does not inflect, so the same pattern serves both.
    expect(durationLabel("P1D", t)).toBe("1日");
  });

  it("closes up the units in Japanese and spaces them in English", () => {
    // The spacing is a language decision, which is why it lives in the locale.
    expect(durationLabel("P7D", t)).toBe("7日");
    expect(durationLabel("P7D", tEn)).toBe("7 days");
  });

  it("returns an unrecognised period unchanged rather than blank", () => {
    // A new period showing as "P42Y" is visible; showing as "" is not.
    expect(durationLabel("P42Y", tEn)).toBe("P42Y");
    expect(durationLabel("", tEn)).toBe("");
  });
});

describe("durationRange", () => {
  it("composes both ends through the same formatter", () => {
    expect(durationRange("P1D", "P10950D", tEn)).toBe("1 day to 30 years");
    expect(durationRange("P0D", "P10950D", tEn)).toBe("No limit to 30 years");
  });

  it("uses the locale's own range separator", () => {
    expect(durationRange("P1D", "P10950D", t)).toBe("1日〜30年");
  });
});
