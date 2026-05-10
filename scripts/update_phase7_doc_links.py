#!/usr/bin/env python3
"""Normalize Phase 7 doc links from `uc15-architecture.md` → `architecture.md` and
`uc15-demo-script.md` → `demo-guide.md` across all README / docs.

Also updates README references in each locale to point to the locale-specific doc
file (e.g., README.ko.md links to docs/architecture.ko.md instead of docs/architecture.md).
"""
from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

UC_DIRS = ["defense-satellite", "government-archives", "smart-city-geospatial"]
LOCALES_SUFFIX = ["ko", "zh-CN", "zh-TW", "fr", "de", "es", "en"]


def _replace_patterns(text: str) -> str:
    # Simple renames uc15-*.md -> architecture.md / demo-guide.md
    replacements = [
        (r"uc15-architecture\.md", "architecture.md"),
        (r"uc16-architecture\.md", "architecture.md"),
        (r"uc17-architecture\.md", "architecture.md"),
        (r"uc15-demo-script\.md", "demo-guide.md"),
        (r"uc16-demo-script\.md", "demo-guide.md"),
        (r"uc17-demo-script\.md", "demo-guide.md"),
    ]
    for pattern, repl in replacements:
        text = re.sub(pattern, repl, text)
    return text


def _localize_doc_link(text: str, locale: str) -> str:
    """If this is a locale-specific README, update docs/architecture.md → docs/architecture.<locale>.md."""
    if locale not in LOCALES_SUFFIX:
        return text
    # Careful to match only the exact pattern without already-locale-extended
    text = re.sub(
        r"docs/architecture\.md(?!\w)",
        f"docs/architecture.{locale}.md",
        text,
    )
    text = re.sub(
        r"docs/demo-guide\.md(?!\w)",
        f"docs/demo-guide.{locale}.md",
        text,
    )
    return text


def main() -> None:
    for uc in UC_DIRS:
        uc_dir = PROJECT_ROOT / uc

        # Update all README.*.md in UC dir
        for readme in uc_dir.glob("README*.md"):
            original = readme.read_text()
            updated = _replace_patterns(original)

            # Determine locale from filename
            name = readme.name  # e.g. README.ko.md, README.md
            if name == "README.md":
                locale = "ja"
            else:
                match = re.match(r"README\.([a-zA-Z-]+)\.md", name)
                locale = match.group(1) if match else "ja"

            if locale != "ja":
                updated = _localize_doc_link(updated, locale)

            if updated != original:
                readme.write_text(updated)
                print(f"Updated links: {readme.relative_to(PROJECT_ROOT)}")

    # Update root README*.md references to old uc15-architecture.md etc
    for readme in PROJECT_ROOT.glob("README*.md"):
        original = readme.read_text()
        updated = _replace_patterns(original)
        if updated != original:
            readme.write_text(updated)
            print(f"Updated links: {readme.name}")


if __name__ == "__main__":
    main()
