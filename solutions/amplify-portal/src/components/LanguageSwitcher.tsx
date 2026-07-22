import { useTranslation, LOCALES, type Locale } from "../i18n";

/**
 * Language switcher dropdown — 8 languages.
 * Persists selection to localStorage. Auto-detects browser language on first visit.
 * Shows language name in native script (日本語, English, 한국어, etc.)
 */
export function LanguageSwitcher() {
  const { locale, setLocale, t } = useTranslation();

  return (
    <div className="language-switcher" title={t("languageLabel")}>
      <select
        value={locale}
        onChange={(e) => setLocale(e.target.value as Locale)}
        aria-label={t("languageLabel")}
        className="language-select"
      >
        {LOCALES.map((loc) => (
          <option key={loc.code} value={loc.code}>
            {loc.label}
          </option>
        ))}
      </select>
    </div>
  );
}
