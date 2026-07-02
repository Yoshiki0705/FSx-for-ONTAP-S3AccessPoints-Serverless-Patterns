#!/usr/bin/env python3
"""Quick translation-quality check for a pattern's README language variants:
Japanese-specific kana remnants (excluding the language switcher line) + fence balance."""
from __future__ import annotations
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
pattern = sys.argv[1] if len(sys.argv) > 1 else "solutions/industry/logistics-ocr"
langs = sys.argv[2].split(",") if len(sys.argv) > 2 else ["ko", "zh-CN", "zh-TW", "fr", "de", "es"]
FENCE = "`" * 3

problems = 0
for lang in langs:
    p = ROOT / pattern / f"README.{lang}.md"
    if not p.exists():
        print(f"{lang}: MISSING FILE")
        problems += 1
        continue
    lines = p.read_text().split("\n")
    kana = []
    for i, l in enumerate(lines):
        if "Language / " in l and "README.md" in l:
            continue
        if re.search(r"[\u3040-\u309F\u30A0-\u30FF]", l):
            kana.append((i + 1, l[:60]))
    fences = sum(1 for l in lines if l.startswith(FENCE))
    ok = (not kana) and fences % 2 == 0
    print(f"README.{lang}.md: kana_lines={len(kana)} fences={fences} {'OK' if ok else 'CHECK'}")
    for ln, t in kana[:3]:
        print(f"    L{ln}: {t}")
    if not ok:
        problems += 1
print(f"\n{'ALL OK' if problems == 0 else str(problems) + ' file(s) need attention'}")
sys.exit(1 if problems else 0)
