#!/usr/bin/env python3
"""Quick static analysis for potential NameError in Lambda handlers.

Uses pyflakes (undefined name detection). For each handler.py in every UC's
functions/ dir, report any undefined names. This catches the class of bugs
we saw in UC9 Discovery (inference_type not returned) and UC4 Discovery
(NameError on undefined `objects`).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def run_pyflakes(path: Path) -> list[str]:
    result = subprocess.run(
        ["python3", "-m", "pyflakes", str(path)],
        capture_output=True, text=True
    )
    # pyflakes emits on stdout, nothing on stderr normally
    lines = result.stdout.splitlines()
    # Filter to undefined-name complaints only (ignore unused imports etc)
    return [l for l in lines if "undefined name" in l]


def main() -> int:
    repo = Path(__file__).resolve().parent.parent
    handlers = sorted(repo.glob("*/functions/*/handler.py"))

    issues = 0
    for h in handlers:
        errs = run_pyflakes(h)
        if errs:
            rel = h.relative_to(repo)
            print(f"=== {rel} ===")
            for e in errs:
                print(f"  {e}")
            issues += len(errs)

    print()
    print(f"Scanned {len(handlers)} handlers, found {issues} undefined-name issue(s)")
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
