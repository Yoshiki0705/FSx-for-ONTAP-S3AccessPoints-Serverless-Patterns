/**
 * Light / dark / system, as a three-way choice rather than a switch.
 *
 * A two-state switch has to start somewhere, and whichever it picks is wrong for
 * half of the people who never touch it. "System" is a real answer — follow the
 * desktop, including when it changes at dusk — so it is one of the options instead
 * of being implied by not having chosen.
 *
 * The attribute on `<html>` is the single source of truth for the stylesheet, and
 * it is written before the first paint by the snippet in index.html. This component
 * only changes it afterwards; it deliberately does not set it on mount, which would
 * mean the theme is applied twice and could flash.
 */
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "../i18n";

/** What the user asked for, which is not the same as what is displayed. */
export type ThemeChoice = "light" | "dark" | "system";

const STORAGE_KEY = "portal-theme";

/** The stored choice, or "system" when there is none or it is unreadable. */
function storedChoice(): ThemeChoice {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    if (value === "light" || value === "dark") return value;
  } catch {
    // storage unavailable (private mode, or a test environment)
  }
  return "system";
}

/** What "system" currently means. */
function systemTheme(): "light" | "dark" {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

const OPTIONS: { choice: ThemeChoice; icon: string; labelKey: "themeLight" | "themeDark" | "themeSystem" }[] = [
  { choice: "light", icon: "☀️", labelKey: "themeLight" },
  { choice: "dark", icon: "🌙", labelKey: "themeDark" },
  { choice: "system", icon: "🖥️", labelKey: "themeSystem" },
];

export function ThemeToggle() {
  const { t } = useTranslation();
  const [choice, setChoice] = useState<ThemeChoice>(storedChoice);

  const apply = useCallback((next: ThemeChoice) => {
    document.documentElement.setAttribute("data-theme", next === "system" ? systemTheme() : next);
    try {
      if (next === "system") localStorage.removeItem(STORAGE_KEY);
      else localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // The theme still applies for this session; only the memory of it is lost.
    }
    setChoice(next);
  }, []);

  // While following the system, keep following it. Without this, a desktop that
  // switches at sunset leaves the portal on the theme it happened to load with.
  useEffect(() => {
    if (choice !== "system") return;
    const query = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!query) return;
    const onChange = () => {
      document.documentElement.setAttribute("data-theme", systemTheme());
    };
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, [choice]);

  return (
    <div className="theme-toggle" role="group" aria-label={t("themeLabel")}>
      {OPTIONS.map((option) => (
        <button
          key={option.choice}
          className={`theme-option ${choice === option.choice ? "active" : ""}`}
          onClick={() => apply(option.choice)}
          // The pressed state is what a screen reader reads as the current choice;
          // the highlight alone says nothing.
          aria-pressed={choice === option.choice}
          title={t(option.labelKey)}
          aria-label={t(option.labelKey)}
        >
          <span aria-hidden="true">{option.icon}</span>
        </button>
      ))}
    </div>
  );
}
