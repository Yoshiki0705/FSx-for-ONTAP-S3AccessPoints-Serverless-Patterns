#!/usr/bin/env python3
"""Fail when a 12-digit AWS account ID appears in an account-ID position and is
not one of the documented placeholders.

Why this exists as well as the secret-based exact-match check in
``.github/workflows/security-check.yml``:

The exact-match check greps tracked files for one specific account ID supplied
as a repository secret. It is precise, but it has two holes. It cannot run at
all when the secret is absent -- and an absent secret produces the same green
result as a clean tree, which is how it sat unnoticed. It also only ever knows
about the one ID that was configured, so a different real account ID pasted from
another environment passes.

This check needs no secret, so it cannot enter that vacuous state, and it is
shape-based rather than value-based, so it catches any real ID rather than one.
It is deliberately narrow: it only looks at 12-digit runs that sit in a position
where an account ID is what is meant (``AccountId=``, ``account_id:``, an ARN
account field, ``Account (...)``). A bare 12-digit number elsewhere is usually a
byte count or the last segment of a UUID -- measured on this repository, those
account for every non-placeholder 12-digit run outside these positions -- and
flagging them would produce noise that gets the check disabled.

Matched digits are never printed. Echoing the finding would leak the value into
CI logs, which are world-readable on a public repository.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# Placeholders are recognised by SHAPE, not by an enumerated list of values.
# A list would have to be edited every time a document needs one more account,
# and the omission looks identical to a real leak, so the check would train its
# readers to add values without thinking. Three shapes cover both this
# repository's convention and the one AWS uses in its own documentation.
#
#   repeated single digit   111111111111, 555555555555, 000000000000
#   repeated digit groups   111122223333, 444455556666   (AWS documentation style)
#   sequential run mod 10   123456789012, 234567890123, 987654321098
#
# A real account ID that happens to be a perfect run or a perfect group pattern
# would be indistinguishable from a placeholder by any means, so nothing is lost.
REPEATED_SINGLE_DIGIT = re.compile(r"^(\d)\1{11}$")
REPEATED_DIGIT_GROUPS = re.compile(r"^(\d)\1{3}(\d)\2{3}(\d)\3{3}$")

# Kept only for values that are conventional but match no shape rule.
DOCUMENTED_PLACEHOLDERS: frozenset[str] = frozenset()


def _is_sequential_run(value: str) -> bool:
    """Return True when the digits ascend or descend by one, wrapping at 9/0.

    Args:
        value: A string of digits.

    Returns:
        True for runs such as ``123456789012`` or ``987654321098``.
    """
    digits = [int(character) for character in value]
    for step in (1, -1):
        if all(
            (previous + step) % 10 == following for previous, following in zip(digits[:-1], digits[1:], strict=True)
        ):
            return True
    return False


# Positions where a 12-digit run means an account ID. Kept adjacent on purpose:
# a nearby *word* "account" also matches prose that merely discusses account
# IDs, which is how the two comments in ci.yml would have been reported.
ACCOUNT_ID_POSITIONS = (
    # AccountId=123456789012 / account_id: "123456789012" / account-id = '...'
    re.compile(r"account[_-]?id\s*[=:]\s*[\"']?(\d{12})\b", re.IGNORECASE),
    # Account (123456789012) -- the form used in the ASCII diagrams
    re.compile(r"account\s*\(\s*(\d{12})\s*\)", re.IGNORECASE),
    # arn:aws:service:region:123456789012:resource
    re.compile(r"arn:aws[a-z-]*:[^:\s]*:[^:\s]*:(\d{12})[:\s\"']"),
)

# An inline escape hatch, matching the repository's existing `allow:naming`
# precedent, for the case where a real ID genuinely has to appear (for example
# an AWS-owned public account ID in a policy example).
EXEMPTION_MARKER = "allow:account-id"

SKIP_SUFFIXES = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".svg",
        ".pdf",
        ".ico",
        ".woff",
        ".woff2",
        ".zip",
        ".gz",
        ".drawio",
    }
)


def is_placeholder(value: str) -> bool:
    """Return True when ``value`` has the shape of a placeholder account ID.

    Args:
        value: A 12-digit account ID found in an account-ID position.

    Returns:
        True when the value matches one of the accepted placeholder shapes.
    """
    if value in DOCUMENTED_PLACEHOLDERS:
        return True
    if REPEATED_SINGLE_DIGIT.match(value) or REPEATED_DIGIT_GROUPS.match(value):
        return True
    return _is_sequential_run(value)


def mask(value: str) -> str:
    """Mask an account ID for display: keep the length, drop the value."""
    return f"{value[:2]}{'#' * (len(value) - 2)}"


def tracked_files(root: Path) -> list[Path]:
    """Return git-tracked files worth scanning, as paths relative to ``root``."""
    out = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", "ls-files", "-z"],  # noqa: S607 - git resolved from PATH by design
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    result = []
    for name in out.split("\0"):
        if not name:
            continue
        path = Path(name)
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        result.append(path)
    return result


def scan_text(text: str) -> list[tuple[int, str]]:
    """Return ``(line_number, account_id)`` for each non-placeholder finding."""
    findings: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if EXEMPTION_MARKER in line:
            continue
        for pattern in ACCOUNT_ID_POSITIONS:
            for match in pattern.finditer(line):
                value = match.group(1)
                if not is_placeholder(value):
                    findings.append((lineno, value))
    return findings


def scan_repository(root: Path) -> list[tuple[Path, int, str]]:
    """Scan every tracked file and return all findings."""
    findings: list[tuple[Path, int, str]] = []
    for rel in tracked_files(root):
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
        findings.extend((rel, lineno, value) for lineno, value in scan_text(text))
    return findings


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="repository root to scan (default: the repository containing this script)",
    )
    args = parser.parse_args(argv)

    findings = scan_repository(args.root)
    if findings:
        print(
            f"::error::{len(findings)} account ID(s) in an account-ID position are not "
            "documented placeholders. Values are masked; see the file and line."
        )
        for rel, lineno, value in findings:
            print(f"  {rel}:{lineno}: {mask(value)}")
        print()
        print("Replace with a placeholder from AGENTS.md, or if the value must appear,")
        print(f"annotate the line with `{EXEMPTION_MARKER}` and say why.")
        return 1

    print("✅ Every account ID in an account-ID position is a documented placeholder")
    return 0


if __name__ == "__main__":
    sys.exit(main())
