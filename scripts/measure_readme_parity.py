#!/usr/bin/env python3
"""Measure translation parity of README language variants against README.md (ja).

For each pattern dir with a README.md, compares each language variant's line
count and H2 section count to the Japanese canonical, and classifies:
  - FULL   : >= 80% of ja lines (likely a full translation)
  - PARTIAL: 40-80%
  - STUB    : < 40% (summary only)

Prints a per-language summary and totals so we can scope the work.
"""
from __future__ import annotations

import glob
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LANGS = ["en.md", "ko.md", "zh-CN.md", "zh-TW.md", "fr.md", "de.md", "es.md"]


def metrics(text: str) -> tuple[int, int]:
    lines = [ln for ln in text.split("\n")]
    h2 = sum(1 for ln in lines if ln.startswith("## "))
    return len(lines), h2


def classify(ratio: float) -> str:
    if ratio >= 0.80:
        return "FULL"
    if ratio >= 0.40:
        return "PARTIAL"
    return "STUB"


def main() -> int:
    buckets: dict[str, list] = defaultdict(list)
    per_lang_stub: dict[str, int] = defaultdict(int)
    total_patterns = 0
    for ja in sorted(glob.glob(str(ROOT / "solutions" / "**" / "README.md"), recursive=True)):
        d = Path(ja).parent
        # skip sub-component readmes (glue-etl, cloudfront) — only pattern roots have template.yaml
        if not (d / "template.yaml").exists():
            continue
        ja_lines, ja_h2 = metrics(Path(ja).read_text())
        if ja_lines < 20:
            continue
        total_patterns += 1
        rel = d.relative_to(ROOT / "solutions")
        row = [str(rel), ja_lines, ja_h2]
        for lang in LANGS:
            p = d / f"README.{lang}"
            if not p.exists():
                row.append(f"{lang}:—")
                continue
            ln, _ = metrics(p.read_text())
            ratio = ln / ja_lines if ja_lines else 1.0
            cls = classify(ratio)
            if cls != "FULL":
                per_lang_stub[lang] += 1
            row.append(f"{lang.split('.')[0]}:{ln}({int(ratio*100)}%,{cls[0]})")
        buckets["rows"].append(row)

    for row in buckets["rows"]:
        print(f"{row[0]:<42} ja={row[1]:>4}l/{row[2]}h2  " + "  ".join(str(c) for c in row[3:]))
    print(f"\nPatterns with template.yaml + README.md: {total_patterns}")
    print("Non-FULL (PARTIAL/STUB) counts per language:")
    for lang in LANGS:
        print(f"  {lang:<9}: {per_lang_stub[lang]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
