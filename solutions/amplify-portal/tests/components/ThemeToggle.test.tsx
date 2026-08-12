/**
 * The theme control: light / dark / system.
 *
 * Two things here are easy to get wrong in a way no one notices. The first is
 * "system": if the choice is not stored as a distinct state, a desktop that switches
 * at dusk leaves the portal on whatever theme it loaded with, and the user's only
 * recourse is a reload. The second is the pressed state -- the highlight is a
 * background colour and says nothing to a screen reader, so aria-pressed is the only
 * thing that reports which of the three is active.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, act, fireEvent } from "@testing-library/react";

import { ThemeToggle } from "../../src/components/ThemeToggle";
import { I18nProvider } from "../../src/i18n";

const STORAGE_KEY = "portal-theme";

/**
 * An in-memory Storage.
 *
 * This environment has no localStorage at all -- not as a global, not on window --
 * which is why every access to it in the portal sits inside a try/catch. Without a
 * stub these tests would exercise only the catch branches and would pass while
 * asserting nothing about what is stored.
 */
function stubStorage(onWrite?: () => void) {
  const entries = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => entries.get(key) ?? null,
    setItem: (key: string, value: string) => {
      onWrite?.();
      entries.set(key, value);
    },
    removeItem: (key: string) => entries.delete(key),
    clear: () => entries.clear(),
  });
  return entries;
}

/** A matchMedia whose value can be changed and whose listeners can be fired. */
function stubMatchMedia(prefersDark: boolean) {
  const listeners = new Set<() => void>();
  const query = {
    matches: prefersDark,
    addEventListener: (_: string, handler: () => void) => listeners.add(handler),
    removeEventListener: (_: string, handler: () => void) => listeners.delete(handler),
  };
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => query),
  );
  return {
    /** Change what the system prefers and notify, as a desktop does at sunset. */
    change(next: boolean) {
      query.matches = next;
      listeners.forEach((handler) => handler());
    },
    get listenerCount() {
      return listeners.size;
    },
  };
}

const renderToggle = () =>
  render(
    <I18nProvider>
      <ThemeToggle />
    </I18nProvider>,
  );

const themeAttribute = () => document.documentElement.getAttribute("data-theme");
const option = (name: RegExp) => screen.getByRole("button", { name });

let storage: Map<string, string>;

beforeEach(() => {
  storage = stubStorage();
  document.documentElement.removeAttribute("data-theme");
  stubMatchMedia(false);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ThemeToggle", () => {
  it("offers three choices, not a switch", () => {
    renderToggle();
    expect(screen.getByRole("group")).toBeTruthy();
    expect(screen.getAllByRole("button")).toHaveLength(3);
  });

  it("starts on system when nothing is stored", () => {
    renderToggle();
    expect(option(/システム|system/i).getAttribute("aria-pressed")).toBe("true");
  });

  it("starts on the stored choice", () => {
    storage.set(STORAGE_KEY, "dark");
    renderToggle();
    expect(option(/ダーク|dark/i).getAttribute("aria-pressed")).toBe("true");
  });

  it("does not touch the attribute on mount", () => {
    // index.html sets it before the first paint. Setting it again here would apply
    // the theme twice and can flash.
    storage.set(STORAGE_KEY, "dark");
    renderToggle();
    expect(themeAttribute()).toBeNull();
  });

  it("applies dark and remembers it", () => {
    renderToggle();
    fireEvent.click(option(/ダーク|dark/i));

    expect(themeAttribute()).toBe("dark");
    expect(storage.get(STORAGE_KEY)).toBe("dark");
    expect(option(/ダーク|dark/i).getAttribute("aria-pressed")).toBe("true");
    expect(option(/ライト|light/i).getAttribute("aria-pressed")).toBe("false");
  });

  it("forgets the choice when returning to system", async () => {
    storage.set(STORAGE_KEY, "dark");
    renderToggle();
    fireEvent.click(option(/システム|system/i));

    // Removed rather than stored as "system": an absent key and "follow the system"
    // are the same state, and keeping both invites them to disagree.
    expect(storage.has(STORAGE_KEY)).toBe(false);
  });

  it("resolves system to what the desktop currently prefers", async () => {
    stubMatchMedia(true);
    renderToggle();
    fireEvent.click(option(/システム|system/i));
    expect(themeAttribute()).toBe("dark");
  });

  it("keeps following the system after it changes", async () => {
    const media = stubMatchMedia(false);
    renderToggle();
    fireEvent.click(option(/システム|system/i));
    expect(themeAttribute()).toBe("light");

    act(() => media.change(true));

    // The regression this guards: without the listener the portal stays on the theme
    // it loaded with until someone reloads the page.
    expect(themeAttribute()).toBe("dark");
  });

  it("stops following once an explicit choice is made", async () => {
    const media = stubMatchMedia(false);
    renderToggle();
    fireEvent.click(option(/システム|system/i));
    fireEvent.click(option(/ライト|light/i));

    act(() => media.change(true));

    expect(themeAttribute()).toBe("light");
  });

  it("drops the listener when it is no longer following", async () => {
    const media = stubMatchMedia(false);
    renderToggle();
    fireEvent.click(option(/システム|system/i));
    expect(media.listenerCount).toBe(1);

    fireEvent.click(option(/ダーク|dark/i));
    expect(media.listenerCount).toBe(0);
  });

  it("labels each option for a screen reader", () => {
    renderToggle();
    for (const button of screen.getAllByRole("button")) {
      expect(button.getAttribute("aria-label")).toBeTruthy();
      // The icon is decorative; the label carries the meaning.
      expect(button.querySelector("[aria-hidden='true']")).toBeTruthy();
    }
  });

  it("still applies the theme when storage is unavailable", async () => {
    // Private browsing throws on setItem. Losing the memory of the choice is
    // acceptable; losing the choice itself is not.
    stubStorage(() => {
      throw new Error("QuotaExceededError");
    });
    stubMatchMedia(false);
    renderToggle();
    fireEvent.click(option(/ダーク|dark/i));

    expect(themeAttribute()).toBe("dark");
  });

  it("treats an unreadable stored value as system", () => {
    storage.set(STORAGE_KEY, "sepia");
    renderToggle();
    expect(option(/システム|system/i).getAttribute("aria-pressed")).toBe("true");
  });
});
