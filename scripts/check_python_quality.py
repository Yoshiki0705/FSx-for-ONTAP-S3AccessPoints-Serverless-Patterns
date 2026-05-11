#!/usr/bin/env python3
"""Broader Python quality check for Lambda handlers + shared modules.

Runs pyflakes across all Python files in UC functions/ dirs + shared/.
Reports all warnings categorized:
  - undefined name (potential NameError at runtime) — CRITICAL
  - unused import                                    — cosmetic
  - unused variable                                  — cosmetic
  - syntax error                                     — CRITICAL
  - other                                            — review

Exit code 1 only if CRITICAL issues found (undefined name / syntax error).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def run_pyflakes(path: Path) -> list[str]:
    result = subprocess.run(
        ["python3", "-m", "pyflakes", str(path)],
        capture_output=True, text=True,
    )
    return result.stdout.splitlines()


def categorize(line: str) -> str:
    lower = line.lower()
    if "undefined name" in lower:
        return "CRITICAL"
    if "syntax error" in lower or "invalid syntax" in lower:
        return "CRITICAL"
    if "imported but unused" in lower:
        return "unused-import"
    if "assigned to but never used" in lower:
        return "unused-variable"
    if "redefinition of unused" in lower:
        return "redefinition"
    return "other"


def main() -> int:
    repo = Path(__file__).resolve().parent.parent
    os.chdir(repo)

    roots = []
    for uc in sorted(repo.glob("*/functions")):
        if uc.is_dir():
            roots.append(uc)
    shared = repo / "shared"
    if shared.is_dir():
        roots.append(shared)

    all_files: list[Path] = []
    for root in roots:
        for py in root.rglob("*.py"):
            if "__pycache__" in py.parts:
                continue
            if "tests" in py.parts:
                continue
            all_files.append(py)

    by_category: dict[str, list[str]] = {
        "CRITICAL": [],
        "unused-import": [],
        "unused-variable": [],
        "redefinition": [],
        "other": [],
    }

    for f in all_files:
        lines = run_pyflakes(f)
        for line in lines:
            cat = categorize(line)
            by_category[cat].append(line)

    critical_count = len(by_category["CRITICAL"])
    print(f"Scanned {len(all_files)} Python files in UC functions/ and shared/")
    print()
    for cat in ("CRITICAL", "other", "redefinition", "unused-variable", "unused-import"):
        items = by_category[cat]
        if not items:
            continue
        print(f"=== {cat} ({len(items)}) ===")
        for line in items:
            print(f"  {line}")
        print()

    print(f"Critical issues: {critical_count}")
    return 1 if critical_count else 0


if __name__ == "__main__":
    sys.exit(main())
