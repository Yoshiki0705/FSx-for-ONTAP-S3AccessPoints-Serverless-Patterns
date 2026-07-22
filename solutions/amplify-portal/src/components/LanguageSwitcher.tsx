import { useState, useRef, useEffect } from "react";
import { useTranslation, LOCALES, type Locale } from "../i18n";

/**
 * Language switcher — pill-shaped custom dropdown.
 *
 * UX design principles (per Smashing Magazine best practices):
 * - Show current language in native script (日本語, not "Japanese")
 * - No flags (flags = countries, not languages)
 * - Globe icon (🌐) as universal visual cue
 * - Pill shape (rounded) — compact, modern appearance
 * - Click to open, click outside to close
 * - Keyboard accessible (Enter/Escape)
 *
 * Persists to localStorage, auto-detects browser language on first visit.
 */
export function LanguageSwitcher() {
  const { locale, setLocale } = useTranslation();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const currentLabel = LOCALES.find((l) => l.code === locale)?.label || "English";

  // Close on click outside
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open]);

  const handleSelect = (code: Locale) => {
    setLocale(code);
    setOpen(false);
  };

  return (
    <div className="lang-switcher" ref={containerRef}>
      <button
        className="lang-trigger"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-label="Language"
      >
        <span className="lang-globe">🌐</span>
        <span className="lang-current">{currentLabel}</span>
        <span className="lang-chevron">{open ? "▴" : "▾"}</span>
      </button>

      {open && (
        <ul className="lang-dropdown" role="listbox" aria-label="Select language">
          {LOCALES.map((loc) => (
            <li
              key={loc.code}
              role="option"
              aria-selected={loc.code === locale}
              className={`lang-option ${loc.code === locale ? "selected" : ""}`}
              onClick={() => handleSelect(loc.code)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") handleSelect(loc.code);
              }}
              tabIndex={0}
            >
              {loc.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
