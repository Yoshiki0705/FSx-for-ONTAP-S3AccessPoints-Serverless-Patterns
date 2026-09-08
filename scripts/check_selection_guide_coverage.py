#!/usr/bin/env python3
"""Fail when a deployable pattern is missing from the pattern selection guide.

## Why this exists

The guide is the first page a Partner or SI reads to decide what to deploy, and it is
hand-maintained. Measured 2026-09-07 against `main`: it named **16 of 28** industry use cases
and did not mention `flexcache` (10 patterns), `operations` (6), `amplify-portal`,
`event-driven`, `sap` or `ha` at all.

So a reader who started there could not learn that FlexCache fan-out, the file portal, or the
six operations patterns exist. The library was not the problem -- the entrance was. Nothing
reported it, because every other check in this repository looks at whether a document is
internally consistent, not at whether it covers the tree it claims to index.

## What counts as a pattern

A directory holding a `template.yaml` (deployable) or, for the portal, an `amplify/`
directory. That excludes `operations/docs` and `operations/tests`, which are shared and not
something anyone deploys -- a rule based on what the directory contains rather than on a list
of names to keep in step.

## Usage

    python3 scripts/check_selection_guide_coverage.py           # exit 1 on a gap
    python3 scripts/check_selection_guide_coverage.py --list    # what it considers a pattern
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

GUIDES = (
    ROOT / "docs" / "pattern-selection-guide.md",
    ROOT / "docs" / "pattern-selection-guide.en.md",
)

# Where deployable patterns live. `solutions/*/*` covers industry, flexcache, genai, edge,
# event-driven, sap and ha; `solutions/*` catches the portal, which sits one level up.
PATTERN_GLOBS = ("solutions/*/*", "solutions/*", "operations/*")


def is_pattern(path: Path) -> bool:
    """Whether a directory is something a reader can deploy.

    Decided by contents rather than by name, so a seventh operations pattern or a new family
    is picked up without editing this file, and shared directories are excluded without being
    listed.
    """
    if not path.is_dir():
        return False
    return (path / "template.yaml").is_file() or (path / "amplify").is_dir()


def patterns(root: Path = ROOT) -> list[str]:
    """Every deployable pattern directory, as a repository-relative posix path."""
    found: set[str] = set()
    for glob in PATTERN_GLOBS:
        for path in root.glob(glob):
            if is_pattern(path):
                found.add(path.relative_to(root).as_posix())
    return sorted(found)


def missing(root: Path = ROOT) -> dict[str, list[str]]:
    """Map each guide to the patterns it does not mention.

    Args:
        root: Repository root, overridable for tests.

    Returns:
        Guide filename to the sorted list of unmentioned pattern paths. Empty when complete.
    """
    gaps: dict[str, list[str]] = {}
    every = patterns(root)
    for guide in GUIDES:
        target = root / guide.relative_to(ROOT)
        if not target.is_file():
            gaps[guide.name] = ["the guide itself is missing"]
            continue
        text = target.read_text(encoding="utf-8")
        absent = [p for p in every if f"{p}/" not in text]
        if absent:
            gaps[guide.name] = absent
    return gaps


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="print what counts as a pattern")
    args = parser.parse_args()

    if args.list:
        for path in patterns():
            print(path)
        return 0

    gaps = missing()
    if gaps:
        for guide, absent in sorted(gaps.items()):
            print(f"{guide}: {len(absent)} pattern(s) a reader cannot find here:", file=sys.stderr)
            for path in absent:
                print(f"  {path}", file=sys.stderr)
        print(
            "\nThe selection guide is the first page someone reads to choose what to deploy. "
            "A pattern absent from it does not exist for that reader.",
            file=sys.stderr,
        )
        return 1

    print(f"selection-guide: {len(patterns())} pattern(s) reachable from both guides")
    return 0


if __name__ == "__main__":
    sys.exit(main())
