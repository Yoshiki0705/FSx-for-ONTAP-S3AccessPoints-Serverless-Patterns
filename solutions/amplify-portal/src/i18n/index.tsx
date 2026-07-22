import { createContext, useContext, useState, useCallback, type ReactNode } from "react";
import { ja, en, ko, zhCN, zhTW, fr, de, es, type TranslationKeys } from "./locales";

export type Locale = "ja" | "en" | "ko" | "zh-CN" | "zh-TW" | "fr" | "de" | "es";

export const LOCALES: { code: Locale; label: string }[] = [
  { code: "ja", label: "日本語" },
  { code: "en", label: "English" },
  { code: "ko", label: "한국어" },
  { code: "zh-CN", label: "简体中文" },
  { code: "zh-TW", label: "繁體中文" },
  { code: "fr", label: "Français" },
  { code: "de", label: "Deutsch" },
  { code: "es", label: "Español" },
];

const translations: Record<Locale, Record<TranslationKeys, string>> = {
  ja,
  en,
  ko,
  "zh-CN": zhCN,
  "zh-TW": zhTW,
  fr,
  de,
  es,
};

function getInitialLocale(): Locale {
  try {
    const stored = localStorage.getItem("portal-locale");
    if (stored && stored in translations) return stored as Locale;
  } catch {
    // localStorage unavailable (SSR or test environment)
  }
  try {
    const browserLang = navigator.language.toLowerCase();
    if (browserLang.startsWith("ja")) return "ja";
    if (browserLang.startsWith("ko")) return "ko";
    if (browserLang.startsWith("zh-tw") || browserLang === "zh-hant") return "zh-TW";
    if (browserLang.startsWith("zh")) return "zh-CN";
    if (browserLang.startsWith("fr")) return "fr";
    if (browserLang.startsWith("de")) return "de";
    if (browserLang.startsWith("es")) return "es";
  } catch {
    // navigator unavailable
  }
  return "en";
}

interface I18nContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: TranslationKeys) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(getInitialLocale);

  const setLocale = useCallback((newLocale: Locale) => {
    setLocaleState(newLocale);
    try { localStorage.setItem("portal-locale", newLocale); } catch { /* test env */ }
    try { document.documentElement.lang = newLocale; } catch { /* test env */ }
  }, []);

  const t = useCallback(
    (key: TranslationKeys): string => {
      return translations[locale]?.[key] ?? translations.en[key] ?? key;
    },
    [locale]
  );

  return (
    <I18nContext.Provider value={{ locale, setLocale, t }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useTranslation() {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useTranslation must be used within I18nProvider");
  return ctx;
}

export type { TranslationKeys };
