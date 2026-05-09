#!/usr/bin/env python3
"""Create Phase 7 UC locale README stubs (ko, zh-CN, zh-TW, fr, de, es).

For each UC directory (defense-satellite, government-archives, smart-city-geospatial),
copy the English README as a stub for each locale with a header note that
encourages contributions for proper translations.

This is intentionally a stub: full manual translations are preferred but expensive.
"""
from __future__ import annotations

from pathlib import Path

UCS = ["defense-satellite", "government-archives", "smart-city-geospatial"]
LOCALES = {
    "ko": ("한국어", "Korean"),
    "zh-CN": ("简体中文", "Simplified Chinese"),
    "zh-TW": ("繁體中文", "Traditional Chinese"),
    "fr": ("Français", "French"),
    "de": ("Deutsch", "German"),
    "es": ("Español", "Spanish"),
}

LOCALE_HEADER_NOTES = {
    "ko": "> **Note**: 이 번역은 자동 생성된 초안입니다. 원문을 기반으로 리뷰 및 개선 환영합니다.",
    "zh-CN": "> **注意**: 本翻译为自动生成草稿。欢迎基于原文进行审阅和完善。",
    "zh-TW": "> **注意**: 本翻譯為自動產生草稿。歡迎基於原文進行審閱和完善。",
    "fr": "> **Note**: Cette traduction est un brouillon généré automatiquement. Les révisions sont les bienvenues.",
    "de": "> **Hinweis**: Diese Übersetzung ist ein automatisch generierter Entwurf. Überarbeitungen sind willkommen.",
    "es": "> **Nota**: Esta traducción es un borrador generado automáticamente. Se agradecen las revisiones.",
}


def create_stub(uc: str, locale: str, locale_name: str) -> None:
    project_root = Path(__file__).resolve().parent.parent
    en_readme = project_root / uc / "README.en.md"
    out = project_root / uc / f"README.{locale}.md"

    if not en_readme.exists():
        print(f"MISSING: {en_readme}")
        return

    content = en_readme.read_text()
    header_note = LOCALE_HEADER_NOTES.get(locale, "")
    if header_note:
        # Insert note right after the first ### or after the top title+nav section
        lines = content.splitlines()
        insert_idx = 0
        for i, line in enumerate(lines):
            if line.startswith("## Overview"):
                insert_idx = i
                break
        if insert_idx:
            lines.insert(insert_idx, header_note + "\n")
        content = "\n".join(lines)

    out.write_text(content)
    print(f"Wrote: {out}")


def main() -> None:
    for uc in UCS:
        for locale, (name, _) in LOCALES.items():
            create_stub(uc, locale, name)


if __name__ == "__main__":
    main()
