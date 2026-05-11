#!/usr/bin/env python3
"""
lint_all_templates.py — Parallel cfn-lint runner for FSxN S3AP Serverless Patterns.

Runs cfn-lint across all 17 UC templates in parallel (4 workers) and aggregates
results. Designed to catch template-level errors that would otherwise block
stack deployment (missing parameters, typo in state machine schema, undefined
conditions, etc).

Why this exists:
  - cfn-lint 1.x takes ~60-120s per template (remote schema fetches).
  - Serial lint of all 17 UCs would take 15-30 minutes.
  - Parallel (4 workers) brings it down to ~5-7 minutes.

Benign error codes filtered (do not indicate real bugs):
  E2530 — Lambda ZipFile size warning (not relevant for deployed UCs).
  E3030 — AllowedValues regional subset mismatch (cfn-lint's regional data).
  E3006 — Resource type missing in some regions (e.g., Glue::Table not in
          ap-southeast-6). Our UCs target ap-northeast-1 / us-east-1.

Exit code: 0 if all clean, 1 if any template has real errors.

Usage:
  python3 scripts/lint_all_templates.py                # all 17 UCs
  python3 scripts/lint_all_templates.py uc-slug1 ...   # subset by UC dir name
"""
from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from cfnlint import api

# All 17 UC directories (each contains template-deploy.yaml).
ALL_UC_SLUGS = [
    "legal-compliance",          # UC1
    "financial-idp",             # UC2
    "manufacturing-analytics",   # UC3
    "media-vfx",                 # UC4
    "healthcare-dicom",          # UC5
    "construction-bim",          # UC6
    "genomics-pipeline",         # UC7
    "energy-seismic",            # UC8
    "autonomous-driving",        # UC9
    "logistics-ocr",             # UC10
    "insurance-claims",          # UC11
    "retail-catalog",            # UC12
    "semiconductor-eda",         # UC13
    "education-research",        # UC14
    "defense-satellite",         # UC15
    "government-archives",       # UC16
    "smart-city-geospatial",     # UC17
]

BENIGN_CODES = ("E2530", "E3030", "E3006")


def lint_one(path: str):
    """Lint a single template. Returns (path, errors_list, elapsed_sec)."""
    start = time.time()
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    results = api.lint_all(content)
    errors = []
    for r in results:
        s = str(r)
        if not s.startswith("[E"):
            continue
        if any(code in s for code in BENIGN_CODES):
            continue
        errors.append(s)
    return path, errors, time.time() - start


def main(argv: list[str]) -> int:
    repo_root = Path(__file__).resolve().parent.parent
    os.chdir(repo_root)

    if argv:
        slugs = argv
    else:
        slugs = ALL_UC_SLUGS

    templates = []
    for slug in slugs:
        tpl = Path(slug) / "template-deploy.yaml"
        if not tpl.is_file():
            print(f"WARN: {tpl} not found, skipping")
            continue
        templates.append(str(tpl))

    if not templates:
        print("No templates to lint.")
        return 1

    print(f"Linting {len(templates)} template(s) with 4 parallel workers...\n")

    failures = 0
    with ProcessPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(lint_one, t): t for t in templates}
        for fut in as_completed(futures):
            path, errors, elapsed = fut.result()
            status = "OK" if not errors else f"FAIL ({len(errors)})"
            print(f"[{elapsed:5.1f}s] {status:10s} {path}")
            for err in errors:
                print(f"  {err}")
            if errors:
                failures += 1

    print()
    passed = len(templates) - failures
    print(f"=== Summary: {passed}/{len(templates)} templates clean ===")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
