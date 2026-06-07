#!/usr/bin/env python3
"""Check that third-party GitHub Actions are pinned to SHA hashes.

Supply-chain security requirement: all non-GitHub-owned actions must use
full SHA pinning (e.g., `uses: owner/action@<sha> # vX.Y.Z`).

GitHub-owned actions (actions/*, github/*) are allowed to use tag references
since they are first-party and signed.
"""

import re
import sys
from pathlib import Path

# First-party orgs that are exempt from SHA pinning requirement
EXEMPT_ORGS = {"actions", "github"}

# Pattern matching `uses: owner/action@ref`
USES_PATTERN = re.compile(r"^\s*uses:\s+([^@\s]+)@([^\s#]+)")

# SHA pattern (40 hex chars)
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def check_workflow(filepath: Path) -> list[str]:
    """Check a single workflow file for unpinned actions."""
    findings = []
    with open(filepath, encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            match = USES_PATTERN.search(line)
            if not match:
                continue

            action_ref = match.group(1)  # e.g., "ossf/scorecard-action"
            version_ref = match.group(2)  # e.g., "v2.4.3" or "abc123..."

            # Extract org from action reference
            org = action_ref.split("/")[0] if "/" in action_ref else ""

            # Skip first-party actions
            if org in EXEMPT_ORGS:
                continue

            # Check if pinned to SHA
            if not SHA_PATTERN.match(version_ref):
                findings.append(
                    f"  {filepath}:{line_no} — {action_ref}@{version_ref}\n"
                    f"    ⚠️  Third-party action not pinned to SHA hash"
                )

    return findings


def main() -> int:
    print("🔍 Checking GitHub Actions SHA pinning...")

    workflow_dir = Path(".github/workflows")
    if not workflow_dir.exists():
        print("   No .github/workflows/ directory found — skipping")
        return 0

    all_findings: list[str] = []
    files_checked = 0

    for workflow_file in sorted(workflow_dir.glob("*.yml")) + sorted(workflow_dir.glob("*.yaml")):
        files_checked += 1
        findings = check_workflow(workflow_file)
        all_findings.extend(findings)

    print(f"   Checked {files_checked} workflow files\n")

    if all_findings:
        print(f"❌ {len(all_findings)} unpinned third-party action(s) found:")
        for f in all_findings:
            print(f)
        print("\n💡 Pin actions to SHA: `uses: owner/action@<full-sha> # vX.Y.Z`")
        print("   Find SHA: gh api repos/OWNER/REPO/git/refs/tags/TAG --jq '.object.sha'")
        return 1

    print("✅ All third-party actions are SHA-pinned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
