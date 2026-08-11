#!/usr/bin/env python3
"""Check GitHub Actions pinning, and that no workflow sits where it never runs.

Two checks, both learned from real gaps in this repository.

1. Every action must be pinned to a full 40-character commit SHA, with the
   version in a trailing comment (`uses: owner/action@<sha> # vX.Y.Z`).

   This used to exempt `actions/*` and `github/*` as "first-party and signed".
   That exemption did not describe the repository: all nine actions in use are
   SHA-pinned, Renovate is configured with `helpers:pinGitHubActionDigests` and
   `pinDigests: true` to keep them that way, and the supply-chain policy makes
   no first-party exception. A checker that permits what the policy forbids
   cannot detect a regression, so the exemption is gone. First-party actions
   are compromised the same way third-party ones are — by a moved tag.

2. Workflow files must live in `.github/workflows` at the repository root.

   GitHub only reads workflows from that one directory. A file at
   `infrastructure/handson-lab/.github/workflows/validate.yml` looked like a
   cfn-lint gate for seven templates, was never executed once, and those
   templates were also outside the `templates:` globs in `.cfnlintrc` — so
   they had no gate at all. Nothing reported this, because a workflow that
   never runs never fails.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Pattern matching `uses: owner/action@ref`.
#
# The `- ` is not optional decoration. This pattern used to be `^\s*uses:`,
# which does not match the one-line step form `- uses: actions/checkout@v4`
# because `-` is not whitespace. Both forms are in use here, so the checker was
# reading roughly half the `uses:` lines and reporting the rest as clean.
USES_PATTERN = re.compile(r"^\s*(?:-\s+)?uses:\s+([^@\s]+)@([^\s#]+)")

# SHA pattern (40 hex chars)
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")

# The trailing `# vX.Y.Z` that says which version a SHA corresponds to. Without
# it a bump is unreviewable: nobody can tell v4 from v7 by looking at a hash.
VERSION_COMMENT_PATTERN = re.compile(r"#\s*v[0-9]+(\.[0-9]+)*\b")

WORKFLOW_SUFFIXES = (".yml", ".yaml")


def check_workflow(filepath: Path, display: Path | None = None) -> list[str]:
    """Check a single workflow file for unpinned actions.

    Args:
        filepath: Workflow file to read.
        display: Path to show in findings, when it differs from ``filepath``
            (a repository-relative path reads better than an absolute one).

    Returns:
        One formatted finding per problem line. Empty when the file is clean.
    """
    findings = []
    shown = display or filepath
    with open(filepath, encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            match = USES_PATTERN.search(line)
            if not match:
                continue

            action_ref = match.group(1)
            version_ref = match.group(2)

            if not SHA_PATTERN.match(version_ref):
                findings.append(f"  {shown}:{line_no} — {action_ref}@{version_ref}\n    not pinned to a commit SHA")
            elif not VERSION_COMMENT_PATTERN.search(line):
                findings.append(
                    f"  {shown}:{line_no} — {action_ref}@{version_ref[:12]}...\n"
                    f"    pinned, but no trailing `# vX.Y.Z` saying which version this is"
                )

    return findings


def find_misplaced_workflows(root: Path) -> list[Path]:
    """Find workflow files GitHub will never execute.

    Args:
        root: Repository root. Only ``root/.github/workflows`` is honoured by
            GitHub; a ``.github/workflows`` anywhere else is inert.

    Returns:
        Paths to workflow files outside the root workflows directory, excluding
        anything vendored under ``node_modules``.
    """
    canonical = (root / ".github" / "workflows").resolve()
    misplaced = []
    for path in sorted(root.rglob(".github/workflows/*")):
        if path.suffix not in WORKFLOW_SUFFIXES or not path.is_file():
            continue
        if "node_modules" in path.parts:
            continue
        if path.parent.resolve() == canonical:
            continue
        misplaced.append(path)
    return misplaced


def main(argv: list[str] | None = None) -> int:
    """Run both checks against a repository root.

    Args:
        argv: Command-line arguments. ``None`` reads ``sys.argv``.

    Returns:
        ``0`` when every action is SHA-pinned with a version comment and every
        workflow sits in the directory GitHub reads; ``1`` otherwise.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Repository root to check (default: current directory)",
    )
    args = parser.parse_args(argv)
    root: Path = args.root

    print("Checking GitHub Actions pinning...")

    workflow_dir = root / ".github" / "workflows"
    if not workflow_dir.exists():
        print(f"   No {workflow_dir} directory found — skipping")
        return 0

    workflow_files = sorted(p for p in workflow_dir.iterdir() if p.suffix in WORKFLOW_SUFFIXES and p.is_file())

    all_findings: list[str] = []
    for workflow_file in workflow_files:
        all_findings.extend(check_workflow(workflow_file, display=workflow_file.relative_to(root)))

    misplaced = find_misplaced_workflows(root)

    print(f"   Checked {len(workflow_files)} workflow files\n")

    if misplaced:
        print(f"{len(misplaced)} workflow file(s) in a directory GitHub never reads:")
        for path in misplaced:
            print(f"  {path.relative_to(root)}")
        print(
            "\n   GitHub only runs workflows from `.github/workflows` at the repository\n"
            "   root. Move the job there, or fold what it checked into a gate that runs\n"
            "   (for example the `templates:` globs in .cfnlintrc) and delete the file."
        )

    if all_findings:
        print(f"{len(all_findings)} action pinning problem(s):")
        for f in all_findings:
            print(f)
        print("\n   Pin actions as: `uses: owner/action@<full-sha> # vX.Y.Z`")
        print("   Find the SHA: gh api repos/OWNER/REPO/git/ref/tags/TAG --jq '.object.sha'")

    if all_findings or misplaced:
        return 1

    print("All actions are SHA-pinned with a version comment, and every workflow is")
    print("in a directory GitHub reads.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
