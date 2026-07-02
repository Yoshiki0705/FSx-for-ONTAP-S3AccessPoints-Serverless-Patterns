#!/usr/bin/env python3
"""Check that parameter names used in README `sam deploy --parameter-overrides`
blocks actually exist in the pattern's template.yaml Parameters.

A README that passes a non-existent parameter (e.g. a renamed `CrossRegionTarget`)
makes `sam deploy` fail with "must have values" / "invalid parameter", breaking
the "anyone can deploy" promise.

Reports, per pattern, any README param keys not declared in template.yaml.

Usage: python3 scripts/check_readme_param_names.py
"""
from __future__ import annotations

import glob
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def template_params(tpl: Path) -> set[str]:
    text = tpl.read_text()
    m = re.search(r"\nParameters:\n(.*?)\n(?:Globals|Conditions|Mappings|Resources):", text, re.S)
    if not m:
        return set()
    body = m.group(1)
    return set(re.findall(r"^  ([A-Za-z0-9]+):\s*$", body, re.M))


def readme_param_keys(md: Path) -> set[str]:
    text = md.read_text()
    keys: set[str] = set()
    # capture inside parameter-overrides blocks: lines like `    Key=value \`
    in_over = False
    for line in text.split("\n"):
        if "--parameter-overrides" in line:
            in_over = True
            continue
        if in_over:
            if re.match(r"^\s*--", line) or "```" in line or line.strip() == "":
                in_over = False
                continue
            m = re.match(r"^\s*([A-Za-z0-9]+)=", line)
            if m:
                keys.add(m.group(1))
    return keys


def main() -> int:
    issues = 0
    for tpl in sorted(glob.glob(str(ROOT / "solutions" / "**" / "template.yaml"), recursive=True)):
        if ".aws-sam" in tpl:
            continue
        tpl_p = Path(tpl)
        params = template_params(tpl_p)
        if not params:
            continue
        for md in sorted(list(tpl_p.parent.glob("README*.md")) + list(tpl_p.parent.glob("docs/demo-guide*.md"))):
            used = readme_param_keys(md)
            unknown = used - params
            if unknown:
                issues += 1
                print(f"{md.relative_to(ROOT)}: unknown params {sorted(unknown)}")
    print(f"\n{'OK - no unknown params' if issues == 0 else f'{issues} README(s) reference unknown params'}")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
