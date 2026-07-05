#!/usr/bin/env python3
"""Cross-language parity scan for pattern README deploy docs.

For each pattern directory that has a template.yaml, group its README*.md files
and report when a deploy-related marker is present in some language variants but
missing in others. Surfaces asymmetric updates (e.g. ja/en got a note the other
languages did not).
"""

from __future__ import annotations

import glob
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MARKERS = {
    # Meaningful deploy-doc parity signals. `sam build` alone is intentionally
    # excluded: it appears in local-testing (`sam local invoke`) blocks too and
    # would false-flag patterns that document local testing but deploy via a
    # pattern-specific flow (e.g. Bedrock KB pre-creation).
    "sam deploy": "sam deploy",
    "template-deploy note": "template-deploy.yaml",
}

LANG_SUFFIXES = ["md", "en.md", "ko.md", "zh-CN.md", "zh-TW.md", "fr.md", "de.md", "es.md"]


def has_marker(text: str, marker) -> bool:
    if isinstance(marker, re.Pattern):
        return bool(marker.search(text))
    return marker in text


def main() -> int:
    gaps = 0
    for tpl in sorted(glob.glob(str(ROOT / "solutions" / "**" / "template.yaml"), recursive=True)):
        if ".aws-sam" in tpl:
            continue
        d = Path(tpl).parent
        readmes = {}
        for suf in LANG_SUFFIXES:
            p = d / f"README.{suf}" if suf != "md" else d / "README.md"
            if p.exists():
                readmes[suf] = p.read_text()
        if len(readmes) < 2:
            continue
        for name, marker in MARKERS.items():
            present = {suf for suf, text in readmes.items() if has_marker(text, marker)}
            if present and present != set(readmes.keys()):
                missing = sorted(set(readmes.keys()) - present)
                # only report deploy-relevant markers when at least the primary has it
                gaps += 1
                rel = d.relative_to(ROOT)
                print(f"{rel}: marker '{name}' present in {len(present)}/{len(readmes)}; missing in {missing}")
    print(f"\n{'OK - deploy docs in parity across languages' if gaps == 0 else f'{gaps} parity gap(s) found'}")
    return 1 if gaps else 0


if __name__ == "__main__":
    raise SystemExit(main())
