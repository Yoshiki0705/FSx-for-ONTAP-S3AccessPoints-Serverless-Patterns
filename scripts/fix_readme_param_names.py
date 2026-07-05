#!/usr/bin/env python3
"""Fix stale parameter names in README `sam deploy --parameter-overrides` blocks so
they match each pattern's template.yaml Parameters.

Rules:
  1. Rename `CrossRegionTarget=` -> `CrossRegion=` (the real parameter name).
  2. Drop any `--parameter-overrides` line whose key is NOT declared in the
     template (e.g. `DeployBucket` — SAM packages/uploads automatically — and any
     other removed params like a stale `S3AccessPointName`).

Template-aware: only drops keys genuinely absent from that pattern's template.

Usage: python3 scripts/fix_readme_param_names.py <pattern-dir> [--write]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def template_params(tpl: Path) -> set[str]:
    text = tpl.read_text()
    m = re.search(r"\nParameters:\n(.*?)\n(?:Globals|Conditions|Mappings|Resources):", text, re.S)
    return set(re.findall(r"^  ([A-Za-z0-9]+):\s*$", m.group(1), re.M)) if m else set()


def fix_readme(md: Path, params: set[str]) -> int:
    lines = md.read_text().split("\n")
    out: list[str] = []
    in_over = False
    changes = 0
    for line in lines:
        if "--parameter-overrides" in line:
            in_over = True
            out.append(line)
            continue
        if in_over:
            # rename first
            renamed = line.replace("CrossRegionTarget=", "CrossRegion=")
            if renamed != line:
                changes += 1
                line = renamed
            if re.match(r"^\s*--", line) or "```" in line or line.strip() == "":
                in_over = False
                out.append(line)
                continue
            m = re.match(r"^\s*([A-Za-z0-9]+)=", line)
            if m and m.group(1) not in params:
                changes += 1  # drop this line
                continue
        out.append(line)
    if changes:
        md.write_text("\n".join(out))
    return changes


def main() -> int:
    pattern_dir = Path(sys.argv[1])
    write = "--write" in sys.argv
    tpl = pattern_dir / "template.yaml"
    params = template_params(tpl)
    total = 0
    md_files = list(pattern_dir.glob("README*.md")) + list(pattern_dir.glob("docs/demo-guide*.md"))
    for md in sorted(md_files):
        if write:
            c = fix_readme(md, params)
            if c:
                print(f"  fixed {md.name} ({c})")
            total += c
    print(f"{pattern_dir.name}: {total} change(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
