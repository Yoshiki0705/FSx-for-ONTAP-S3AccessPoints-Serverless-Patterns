/**
 * `withNodes` splices markup into a translated sentence. The failure that
 * matters is a silent one: a placeholder the locale renamed, or a sentence that
 * still reads correctly after a value vanished from it.
 */

import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { withNodes } from "../../src/utils/richText";
import { ja, en, ko, zhCN, zhTW, fr, de, es } from "../../src/i18n/locales";

describe("withNodes", () => {
  it("substitutes a node for its placeholder", () => {
    const { container } = render(
      <p>{withNodes("leave it as {db} and check", { db: <code>default</code> })}</p>
    );
    expect(container.querySelector("code")?.textContent).toBe("default");
    expect(container.textContent).toBe("leave it as default and check");
  });

  it("keeps an unknown placeholder visible rather than dropping it", () => {
    // Dropping it yields "check with ." — a sentence that reads fine and has
    // lost its subject. Leaving the marker in points at what is missing.
    const { container } = render(<p>{withNodes("check with {cmd}", {})}</p>);
    expect(container.textContent).toBe("check with {cmd}");
  });

  it("substitutes every occurrence and preserves order", () => {
    const { container } = render(
      <p>{withNodes("{a} then {b} then {a}", { a: <code>one</code>, b: <em>two</em> })}</p>
    );
    expect(container.textContent).toBe("one then two then one");
    expect(container.querySelectorAll("code")).toHaveLength(2);
  });

  it("passes through a template with no placeholders", () => {
    const { container } = render(<p>{withNodes("nothing to fill", { db: <code>x</code> })}</p>);
    expect(container.textContent).toBe("nothing to fill");
  });
});

// The placeholders are part of the contract between the component and every
// locale file. A translator dropping `{cmd}` produces a sentence that reads
// perfectly and silently omits the command the user has to type, which no type
// check catches — the value is still a string.
describe("locale placeholder contract", () => {
  const locales = { ja, en, ko, zhCN, zhTW, fr, de, es } as Record<
    string,
    Record<string, string>
  >;

  const required: Record<string, string[]> = {
    aqDatabaseExplain: ["{db}", "{cmd}"],
    aqExamplesNote: ["{cmd}"],
    aqSetupStep2: ["{path}"],
    aqSetupEnvHint: ["{file}", "{env}"],
    aqRowsReturned: ["{count}"],
    durationRange: ["{from}", "{to}"],
    durationDaysWithMonths: ["{n}", "{m}"],
    // These two matter more than the rest: the prompt asks the operator to type a
    // word and the component compares against it. A locale that lost {keyword}
    // would ask for nothing in particular and reject whatever was typed.
    rmSnapLockConfirm: ["{keyword}"],
    rmSnapLockCancelled: ["{keyword}"],
  };

  for (const [name, locale] of Object.entries(locales)) {
    it(`${name} keeps every placeholder its sentence needs`, () => {
      for (const [key, tokens] of Object.entries(required)) {
        for (const token of tokens) {
          expect(locale[key], `${name}.${key} is missing ${token}`).toContain(token);
        }
      }
    });
  }

  it("keeps the multi-line SQL placeholder multi-line in every locale", () => {
    // The textarea hint is three lines; collapsing it to one during translation
    // makes it unreadable without any visible error.
    for (const [name, locale] of Object.entries(locales)) {
      expect(locale.aqSqlPlaceholder.split("\n"), `${name} aqSqlPlaceholder`).toHaveLength(3);
    }
  });
});
