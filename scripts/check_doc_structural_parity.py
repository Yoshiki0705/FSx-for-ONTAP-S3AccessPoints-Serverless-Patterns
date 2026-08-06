#!/usr/bin/env python3
"""Compare JA/EN documentation pairs for structural parity, not just headings.

## Why this exists

`agent-output-audit.yml` already compares JA/EN section counts. That check
passes whenever both files have the same number of headings, which is not the
same thing as both files saying the same thing. A pair can match 1:1 on headings
while one side is missing an entire fenced code block inside a matching section.

That happened in `docs/ja|en/ad-joined-svm-s3ap-prerequisites.md`. The JA
monitoring section defined a `AWS::Scheduler::Schedule` whose target referenced
`!GetAtt AdHealthCheckFunction.Arn`, but the function definition present in the
EN block was absent — so the snippet could not be copied and used. The heading
count was identical, so the existing check reported the pair as aligned.

## What it compares

Per matching section, for each pair:

* fenced code blocks (count and language tags)
* table rows, excluding the `|---|` separator
* top-level list items

Deliberately NOT line counts. Japanese prose is denser than English, and the EN
files here are soft-wrapped near 80 columns while the JA files use one line per
paragraph. On this repository's largest doc pair that difference alone accounts
for an 83-line gap with identical content — measuring lines produces false
alarms and hides the real ones.

Prose wording is out of scope: this cannot tell a translation from a summary.
It answers a narrower question that is still worth automating — does one side
have a code block, table row or list item that the other does not?

## Usage

    python3 scripts/check_doc_structural_parity.py            # report only
    python3 scripts/check_doc_structural_parity.py --strict   # exit 1 on mismatch
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

HEADING = re.compile(r"^#{2,4} ")
TABLE_SEPARATOR = re.compile(r"^\s*\|[\s|:-]+\|\s*$")
LIST_ITEM = re.compile(r"^\s*[-*] ")


def split_sections(path: Path) -> list[tuple[str, list[str]]]:
    """Split a Markdown file into (heading, body-lines) pairs."""
    sections: list[tuple[str, list[str]]] = []
    heading: str | None = None
    body: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if HEADING.match(line):
            if heading is not None:
                sections.append((heading, body))
            heading, body = line.strip(), []
        else:
            body.append(line)
    if heading is not None:
        sections.append((heading, body))
    return sections


def structure(body: list[str]) -> dict[str, object]:
    """Countable structure of a section body."""
    fences = [line.strip() for line in body if line.strip().startswith("```")]
    # Opening fences are the even-indexed ones; their suffix is the language tag.
    langs = [fence.lstrip("`").strip() for fence in fences[0::2]]
    rows = [line for line in body if line.strip().startswith("|") and not TABLE_SEPARATOR.match(line)]
    items = [line for line in body if LIST_ITEM.match(line)]
    return {
        "blocks": len(fences) // 2,
        "langs": [lang for lang in langs if lang],
        "rows": len(rows),
        "items": len(items),
    }


def find_pairs() -> list[tuple[Path, Path]]:
    """JA/EN document pairs that exist on both sides."""
    pairs: list[tuple[Path, Path]] = []
    ja_dir = REPO_ROOT / "docs" / "ja"
    en_dir = REPO_ROOT / "docs" / "en"
    if not ja_dir.is_dir() or not en_dir.is_dir():
        return pairs
    for ja in sorted(ja_dir.glob("*.md")):
        en = en_dir / ja.name
        if en.exists():
            pairs.append((ja, en))
    return pairs


def compare(ja: Path, en: Path) -> list[str]:
    """Structural differences between one pair. Empty list means aligned."""
    ja_sections = split_sections(ja)
    en_sections = split_sections(en)

    problems: list[str] = []

    if len(ja_sections) != len(en_sections):
        problems.append(
            f"section count differs: JA has {len(ja_sections)}, EN has {len(en_sections)} "
            "— structural comparison below is positional and may be misaligned"
        )

    for ja_pair, en_pair in zip(ja_sections, en_sections):
        ja_heading, ja_body = ja_pair
        en_heading, en_body = en_pair
        ja_struct = structure(ja_body)
        en_struct = structure(en_body)

        for key, label in (
            ("blocks", "fenced code blocks"),
            ("rows", "table rows"),
            ("items", "list items"),
        ):
            if ja_struct[key] != en_struct[key]:
                problems.append(
                    f"{ja_heading}\n"
                    f"      {label}: JA has {ja_struct[key]}, EN has {en_struct[key]}\n"
                    f"      (EN heading: {en_heading})"
                )

        if ja_struct["langs"] != en_struct["langs"]:
            problems.append(
                f"{ja_heading}\n      code block languages: JA {ja_struct['langs']}, EN {en_struct['langs']}"
            )

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 when any pair has a structural mismatch",
    )
    parser.add_argument(
        "--max-mismatches",
        type=int,
        default=None,
        metavar="N",
        help=(
            "exit 1 when the total exceeds N. Use this as a ratchet against the "
            "recorded baseline so the count can only go down, rather than failing "
            "on pre-existing gaps."
        ),
    )
    args = parser.parse_args()

    pairs = find_pairs()
    if not pairs:
        print("no docs/ja + docs/en pairs found")
        return 0

    total_problems = 0
    for ja, en in pairs:
        problems = compare(ja, en)
        rel = ja.relative_to(REPO_ROOT)
        if problems:
            total_problems += len(problems)
            print(f"\n{rel}  ({len(problems)} mismatch(es))")
            for problem in problems:
                print(f"  - {problem}")
        else:
            print(f"OK  {rel}")

    print(f"\n{len(pairs)} pair(s) checked, {total_problems} structural mismatch(es)")

    guidance = (
        "\nA mismatch means one language has a code block, table row or list item the "
        "other does not. Port the missing content rather than deleting the other side "
        "— the gap usually means one language is missing something a reader needs, not "
        "that the other has something spare."
    )

    if args.strict and total_problems:
        print(guidance)
        return 1

    if args.max_mismatches is not None and total_problems > args.max_mismatches:
        print(guidance)
        print(
            f"\n{total_problems} mismatches exceeds the recorded baseline of "
            f"{args.max_mismatches}. Fix the new gap, or lower the baseline in the "
            "workflow if you have closed some."
        )
        return 1

    if args.max_mismatches is not None and total_problems < args.max_mismatches:
        print(
            f"\nBelow the recorded baseline of {args.max_mismatches}. Lower it to "
            f"{total_problems} so the progress is locked in."
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
