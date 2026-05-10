#!/usr/bin/env python3
"""Generate 7 locale versions of architecture.md and demo-guide.md for UC15/16/17.

- Inject language switcher at the top of the Japanese source file.
- Copy JA content as a stub for each locale with a notice to review the translation.
- Mirror the pattern used by UC6/UC9 etc.
"""
from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

UCS = ["defense-satellite", "government-archives", "smart-city-geospatial"]
DOC_TYPES = ["architecture", "demo-guide"]

LOCALES = [
    ("ja", "日本語"),
    ("en", "English"),
    ("ko", "한국어"),
    ("zh-CN", "简体中文"),
    ("zh-TW", "繁體中文"),
    ("fr", "Français"),
    ("de", "Deutsch"),
    ("es", "Español"),
]


def build_language_switcher(current_locale: str, base_name: str) -> str:
    """Return the Markdown language switcher line."""
    parts = []
    for code, label in LOCALES:
        if code == "ja":
            filename = f"{base_name}.md"
        else:
            filename = f"{base_name}.{code}.md"
        if code == current_locale:
            parts.append(label)
        else:
            parts.append(f"[{label}]({filename})")
    return "🌐 **Language / 言語**: " + " | ".join(parts)


NOTICE = {
    "en": "> Note: This translation is an auto-generated draft based on the Japanese original. Contributions to improve translation quality are welcome.",
    "ko": "> 참고: 이 번역은 일본어 원문을 바탕으로 자동 생성된 초안입니다. 번역 품질 향상에 대한 기여를 환영합니다.",
    "zh-CN": "> 注意：本翻译为基于日文原文自动生成的草稿，欢迎提交改进翻译的贡献。",
    "zh-TW": "> 注意：本翻譯為基於日文原文自動生成的草稿，歡迎提交改進翻譯的貢獻。",
    "fr": "> Remarque: Cette traduction est un brouillon généré automatiquement à partir de l'original japonais. Les contributions pour améliorer la qualité de la traduction sont les bienvenues.",
    "de": "> Hinweis: Diese Übersetzung ist ein automatisch generierter Entwurf basierend auf dem japanischen Original. Beiträge zur Verbesserung der Übersetzungsqualität sind willkommen.",
    "es": "> Nota: Esta traducción es un borrador generado automáticamente a partir del original japonés. Se agradecen las contribuciones para mejorar la calidad de la traducción.",
}


def inject_switcher_in_ja(doc_path: Path, base_name: str) -> str:
    """Ensure the JA file has a language switcher at the top and return its content."""
    content = doc_path.read_text()
    switcher = build_language_switcher("ja", base_name)

    # If already has switcher, just return content
    if "🌐 **Language / 言語**" in content:
        return content

    # Insert after the first H1 title
    lines = content.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("# "):
            # insert blank + switcher + blank after title
            lines.insert(i + 1, "")
            lines.insert(i + 2, switcher)
            break
    new_content = "\n".join(lines)
    doc_path.write_text(new_content)
    return new_content


def build_locale_content(ja_content: str, locale_code: str, base_name: str) -> str:
    """Create a locale-specific version with switcher updated and translation notice added."""
    switcher_ja = build_language_switcher("ja", base_name)
    switcher_locale = build_language_switcher(locale_code, base_name)

    content = ja_content.replace(switcher_ja, switcher_locale)

    # Insert notice after switcher (before next header)
    lines = content.splitlines()
    for i, line in enumerate(lines):
        if "🌐 **Language / 言語**" in line:
            lines.insert(i + 1, "")
            lines.insert(i + 2, NOTICE.get(locale_code, ""))
            break
    return "\n".join(lines)


def main() -> None:
    for uc in UCS:
        for doc_type in DOC_TYPES:
            ja_path = PROJECT_ROOT / uc / "docs" / f"{doc_type}.md"
            if not ja_path.exists():
                print(f"MISSING: {ja_path}")
                continue

            # 1) Inject switcher in JA
            ja_content = inject_switcher_in_ja(ja_path, doc_type)
            print(f"JA OK: {ja_path.relative_to(PROJECT_ROOT)}")

            # 2) Generate each locale file
            for code, _ in LOCALES:
                if code == "ja":
                    continue
                locale_path = PROJECT_ROOT / uc / "docs" / f"{doc_type}.{code}.md"
                if locale_path.exists():
                    print(f"  SKIP (exists): {locale_path.name}")
                    continue
                locale_content = build_locale_content(ja_content, code, doc_type)
                locale_path.write_text(locale_content)
                print(f"  CREATED: {locale_path.name}")


if __name__ == "__main__":
    main()
