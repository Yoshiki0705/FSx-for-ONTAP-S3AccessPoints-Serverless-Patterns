#!/usr/bin/env python3
"""Catch Japanese text left in English documentation.

The `.en.md` files are produced by translating their Japanese counterparts, and a
translation pass that misses a line leaves no trace: the file renders, the links
work, and only a reader who does not read Japanese notices. 96 such lines were
sitting across 37 files — 24 of them the identical `# 前提: AWS SAM CLI ...`
comment, copied verbatim into every pattern's demo guide.

Some Japanese in an English document is correct, and the distinction is what makes
this checkable rather than a blanket ban:

* the language switcher is bilingual by design;
* a Japanese statute is a proper noun, given with an English gloss —
  `景品表示法 (Act against Unjustifiable Premiums and Misleading Representations)`
  is more useful to a reader than the gloss alone;
* a link whose text says "Japanese version" is meant to leave English;
* `industry-coverage-map` carries the Japanese industry name as its own column;
* a Japanese filename used to demonstrate UTF-8 byte counting is the subject of
  the example, not a translation miss.

What remains after those is enumerated in ALLOWED_ANCHORS: links into Japanese
documents that have no English counterpart to point at. They are debt, not
exceptions, and listing them individually means a new one fails this check.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CJK = re.compile(r"[\u3000-\u30ff\u4e00-\u9fff]")

# Bilingual by design: the switcher has to name the other language in that language.
SWITCHER = re.compile(r"🌐|Language / |\*\*言語\*\*|\[日本語\]\(|\(日本語\)|\[English\]\(")

# A link that says it goes to the Japanese version is doing what it says.
DELIBERATE_JA_LINK = re.compile(r"\[Japanese version\]|\[README \(日本語\)\]")

# A Japanese statute paired with its English gloss, in either order:
#   景品表示法 (Act against Unjustifiable Premiums and Misleading Representations)
#   Electricity Business Act (電気事業法)
LAW_WITH_GLOSS = re.compile(
    r"[\u4e00-\u9fff]+(法|規則|条例|基準)[^(（]{0,12}[(（]\s*[A-Za-z]"
    r"|[A-Za-z][A-Za-z ]{3,}[(（][^)）]{0,20}[\u4e00-\u9fff]+(法|規則|条例|基準)[^)）]{0,10}[)）]"
)

# Lines that enumerate the eight UI locales; the point is the native script.
LOCALE_LIST = re.compile(r"한국어|简体中文|繁體中文")

# A dev.to series name quoted as the literal string to type into the `series:` field.
# The Japanese-language series is named in Japanese on dev.to, so translating the
# quotation would tell the author to set a value that does not exist. Requires the
# Japanese to sit inside backticks next to the product name, so untranslated prose in
# the same file still fails.
DEVTO_SERIES_NAME = re.compile(r"`[^`]*FSx for ONTAP [^`]*[\u3000-\u30ff\u4e00-\u9fff]")

# Files where the Japanese is the subject of the passage, not a translation miss.
# Scoped to the lines that carry it, so the rest of each file is still checked.
BY_DESIGN_FILES = {
    # Both docs instruct the author to tag articles with an exact series name.
    "docs/devto-file-portal-series.en.md": DEVTO_SERIES_NAME,
    "docs/devto-series-cleanup-guide.en.md": DEVTO_SERIES_NAME,
    # A deliberately bilingual table: "Industry (EN) | 業界名 (日本語) | UC/FC | ...".
    # An English reader mapping a customer's stated industry onto a pattern needs the
    # Japanese name to match what the customer actually said.
    "docs/industry-coverage-map.en.md": re.compile(r"^\| *[0-9]+ *\||業界名"),
    # Demonstrates UTF-8 byte counting; the Japanese filename is the input.
    "docs/design-considerations-en.md": re.compile(r"レポート_|UTF-8: "),
    # A changelog whose entries quote the Japanese UI strings that were changed.
    # Translating the quotation would describe a change that did not happen.
    "solutions/amplify-portal/docs/IMPLEMENTATION.en.md": re.compile(r"^\| 2026-"),
}

# Links into Japanese documents that have no English counterpart. Debt, not
# exceptions: each entry is a reader who leaves English by following a link whose own
# text is in English. Enumerated individually so a new one fails this check — closing
# an entry means writing the English target, not extending this list.
ALLOWED_ANCHORS: dict[str, tuple[str, ...]] = {
    # docs/guides/troubleshooting-guide.en.md does not exist yet.
    "solutions/industry/financial-idp/README.en.md": ("troubleshooting-guide.md#1-accessdenied-",),
    "solutions/industry/healthcare-dicom/README.en.md": ("troubleshooting-guide.md#1-accessdenied-",),
    "solutions/industry/legal-compliance/README.en.md": (
        "troubleshooting-guide.md#1-accessdenied-",
        "troubleshooting-guide.md#6-lambda-",
    ),
    "solutions/industry/manufacturing-analytics/README.en.md": ("troubleshooting-guide.md#1-accessdenied-",),
    "solutions/industry/media-vfx/README.en.md": ("troubleshooting-guide.md#1-accessdenied-",),
    # docs/investigations/dais2026-agent-bricks-industry-cases.en.md does not exist.
    "docs/pattern-selection-guide.en.md": ("dais2026-agent-bricks-industry-cases.md#",),
}


def english_docs() -> list[Path]:
    """Tracked English documents. Only git decides what a reader can open."""
    proc = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "*.en.md", "*-en.md"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return [ROOT / line for line in proc.stdout.split() if line]


def is_allowed(relative: str, line: str) -> bool:
    """Whether this line's Japanese is there on purpose."""
    if SWITCHER.search(line) or DELIBERATE_JA_LINK.search(line):
        return True
    if LAW_WITH_GLOSS.search(line) or LOCALE_LIST.search(line):
        return True
    by_design = BY_DESIGN_FILES.get(relative)
    if by_design and by_design.search(line):
        return True
    return any(needle in line for needle in ALLOWED_ANCHORS.get(relative, ()))


def main() -> int:
    """Report untranslated lines.

    Returns:
        1 when any English document carries Japanese that is not accounted for.
    """
    findings: list[str] = []
    scanned = 0
    for path in english_docs():
        if not path.is_file():
            continue
        scanned += 1
        relative = str(path.relative_to(ROOT))
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not CJK.search(line) or is_allowed(relative, line):
                continue
            findings.append(f"{relative}:{number}: {line.strip()[:110]}")

    if findings:
        print(f"英語ドキュメントに未翻訳の日本語があります ({len(findings)} 行):", file=sys.stderr)
        for finding in findings:
            print(f"  {finding}", file=sys.stderr)
        print(
            "\n  意図的な日本語（法令名の原文併記、言語スイッチャー、日本語版への明示的なリンク、"
            "UTF-8 の例に使うファイル名）は scripts/check_en_doc_language.py の許可リストに"
            "理由付きで登録してください。日本語ドキュメントへのアンカーは ALLOWED_ANCHORS に"
            "個別に列挙されており、新規に増やす前に英語版の対象を作ることを検討してください。",
            file=sys.stderr,
        )
        return 1

    print(f"EN docs OK: {scanned} ファイルに未翻訳の日本語なし")
    return 0


if __name__ == "__main__":
    sys.exit(main())
