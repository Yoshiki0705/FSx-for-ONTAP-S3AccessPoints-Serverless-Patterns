# ポータル UI の国際化（8 言語）

> このファイルはリポジトリに含まれる（GitHub から読める）。ローカルの Kiro では
> `.kiro/steering/portal-i18n.md` が読み込み条件だけを持ち、
> 該当する作業をしているときにこの内容へ誘導する。`.kiro/` は公開しないため、
> 知識の本体は常にこちら側に置く。

## UI Internationalization (i18n) — 8 Languages

The Amplify portal supports 8 languages with instant runtime switching. All new UI components must follow these patterns.

### Supported Languages

| Code | Label | Auto-detect pattern |
|------|-------|:---:|
| `ja` | 日本語 | `ja-*` |
| `en` | English | `en-*` |
| `ko` | 한국어 | `ko-*` |
| `zh-CN` | 简体中文 | `zh-CN`, `zh` |
| `zh-TW` | 繁體中文 | `zh-TW`, `zh-Hant` |
| `fr` | Français | `fr-*` |
| `de` | Deutsch | `de-*` |
| `es` | Español | `es-*` |

### Architecture

```
src/i18n/
├── index.tsx          # I18nProvider context + useTranslation hook
└── locales/
    ├── index.ts       # Re-exports all locales
    ├── ja.ts          # Source of truth (defines TranslationKeys type)
    ├── en.ts          # English translations
    ├── ko.ts          # Korean
    ├── zh-CN.ts       # Simplified Chinese
    ├── zh-TW.ts       # Traditional Chinese
    ├── fr.ts          # French
    ├── de.ts          # German
    └── es.ts          # Spanish
```

### Design Rules for AI Agents

1. **ja.ts is the type source**: `TranslationKeys` is exported from `ja.ts`. All other locale files must implement `Record<TranslationKeys, string>`
2. **No hardcoded user-facing strings**: Every visible label, heading, button text, description, error message, and placeholder must use `t("keyName")`
3. **Technical terms stay in English**: ONTAP, SnapLock, FlexClone, S3 AP, ARP/AI, REST API, Lambda, Cognito, WORM, VPC, IAM, ARN — these are product/technology names and are NOT translated
4. **Key naming convention**: camelCase, prefixed by component area (`arp*`, `lock*`, `snapshots*`, `nav*`, `group*`)
5. **New keys**: Add to `ja.ts` first (with type), then to all 7 other locale files
6. **Language Switcher UI**: Pill-shaped custom dropdown (`LanguageSwitcher.tsx`), not native `<select>`. Shows 🌐 + current language in native script + chevron
7. **No flags**: Flags represent countries, not languages (per Smashing Magazine UX research). Use language names in native script only
8. **Persistence**: `localStorage.getItem("portal-locale")` → auto-detect from `navigator.language` if not set
9. **Graceful fallback**: `t(key)` falls back to English if key is missing in current locale, then to key name itself
10. **Test environment**: `getInitialLocale()` handles missing `localStorage`/`navigator` gracefully (SSR/jsdom)

### How to Add a New Translatable String

```typescript
// 1. Add key to ja.ts (source of truth)
export const ja = {
  // ... existing keys ...
  myNewLabel: "新しいラベル",
} as const;

// 2. Add to all other locale files (en.ts, ko.ts, zh-CN.ts, zh-TW.ts, fr.ts, de.ts, es.ts)
// TypeScript will show errors until all files have the new key

// 3. Use in component
import { useTranslation } from "../i18n";
const { t } = useTranslation();
return <h2>{t("myNewLabel")}</h2>;
```

### Language Switcher CSS

The pill-shaped dropdown uses CSS custom properties for theming:
- `--border-color`, `--surface-color`, `--text-color`, `--hover-bg`, `--accent-color`, `--selected-bg`
- Animation: `lang-fade-in` (opacity + translateY, 0.12s ease)
- Z-index: 1000 (above all content)
