#!/usr/bin/env python3
"""Drift guard: ensure template.yaml (SAM) and template-deploy.yaml (raw CFn) stay
consistent in their user-facing surface, so the two deploy paths behave the same.

For each pattern that has BOTH files, compares:
  - Parameter names (template-deploy.yaml legitimately adds `DeployBucket`; ignored)
  - Function logical IDs (…Function resources)

Reports drift. Exit 0 = consistent; 1 = drift found.

Usage: python3 scripts/check_template_consistency.py
"""

from __future__ import annotations

import glob
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IGNORE_PARAMS = {"DeployBucket"}


def params_of(text: str) -> set[str]:
    m = re.search(r"\nParameters:\n(.*?)\n(?:Globals|Conditions|Mappings|Resources):", text, re.S)
    return set(re.findall(r"^  ([A-Za-z0-9]+):\s*$", m.group(1), re.M)) if m else set()


def function_ids(text: str) -> set[str]:
    ids: set[str] = set()
    for m in re.finditer(
        r"^  ([A-Za-z0-9]+):\n(?:    .*\n|\n)*?    Type:\s*AWS::(?:Serverless|Lambda)::Function", text, re.M
    ):
        ids.add(m.group(1))
    return ids


def main() -> int:
    drift = 0
    for tpl in sorted(glob.glob(str(ROOT / "solutions" / "**" / "template.yaml"), recursive=True)):
        if ".aws-sam" in tpl:
            continue
        dep = Path(tpl).with_name("template-deploy.yaml")
        if not dep.exists():
            continue
        t1, t2 = Path(tpl).read_text(), dep.read_text()
        p1, p2 = params_of(t1), params_of(t2) - IGNORE_PARAMS
        f1, f2 = function_ids(t1), function_ids(t2)
        rel = Path(tpl).parent.relative_to(ROOT)
        if p1 != p2:
            drift += 1
            print(f"PARAM DRIFT {rel}: only-in-template={sorted(p1 - p2)} only-in-deploy={sorted(p2 - p1)}")
        if f1 != f2:
            drift += 1
            print(f"FUNC DRIFT  {rel}: only-in-template={sorted(f1 - f2)} only-in-deploy={sorted(f2 - f1)}")
    print(
        f"\n{'OK - template.yaml and template-deploy.yaml consistent' if drift == 0 else f'{drift} drift finding(s)'}"
    )
    return 1 if drift else 0


if __name__ == "__main__":
    raise SystemExit(main())
