#!/usr/bin/env python3
"""Fail when a publicly routable IPv4 address appears in a tracked file.

Why shape-based rather than a list of known addresses:

The check this replaces grepped for two specific EC2 public addresses, which meant
the public repository carried the very values it was guarding. It also only ever
knew those two, so a third address pasted from a new test instance passed.

This check needs no list. It flags any dotted IPv4 that ``ipaddress`` reports as
globally routable, plus the same address embedded in an EC2 public DNS name
(``ec2-a-b-c-d.<region>.compute.amazonaws.com``). Everything a document is meant
to use passes without configuration: RFC 1918 private ranges, loopback,
link-local (including the instance metadata address), shared address space, and
the three RFC 5737 documentation ranges (192.0.2.0/24, 198.51.100.0/24,
203.0.113.0/24).

Exact values, when a specific address must also be caught in a form this check
cannot recognise, belong in the gitignored ``scripts/_sensitive_strings.py``.
``scripts/_check_sensitive_leaks.py`` already scans tracked text against that
list, and CI materialises it from the ``SENSITIVE_STRINGS_PY`` secret.

Two things are not leaks and are recognised by context rather than listed per
file: well-known public DNS resolvers, which documentation names on purpose, and
dotted version numbers (``-MinimumVersion 2.8.5.201``). Anything else that must
appear can carry the inline marker ``allow:ipv4`` with a reason.

Matched addresses are never printed in full. CI logs on a public repository are
world-readable, so echoing a finding would leak it a second time.
"""

from __future__ import annotations

import argparse
import ipaddress
import re
import subprocess
import sys
from pathlib import Path

# A dotted quad not glued to further digits or dots, so a five-part OID or long
# version string is not mis-split into an address.
DOTTED_IPV4 = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})(?![\d.])")

# EC2 public DNS names spell the address with hyphens.
EC2_PUBLIC_DNS = re.compile(r"\bec2-(\d{1,3}(?:-\d{1,3}){3})\.", re.IGNORECASE)

# Public resolvers that documentation names deliberately, e.g. "ask 1.1.1.1 first".
# They identify no one's environment.
WELL_KNOWN_PUBLIC: frozenset[str] = frozenset(
    {
        "1.1.1.1",
        "1.0.0.1",
        "8.8.8.8",
        "8.8.4.4",
        "9.9.9.9",
        "149.112.112.112",
        "208.67.222.222",
        "208.67.220.220",
    }
)

# A dotted run directly after the word "version" is a version number.
VERSION_CONTEXT = re.compile(r"version[\s=:\"']*$", re.IGNORECASE)

EXEMPTION_MARKER = "allow:ipv4"

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


def is_public(value: str) -> bool:
    """Return True when ``value`` is a globally routable IPv4 address.

    Args:
        value: A dotted-quad candidate.

    Returns:
        False for invalid octets, private / reserved / documentation ranges, and
        the well-known public resolvers.
    """
    try:
        address = ipaddress.IPv4Address(value)
    except ValueError:
        return False
    if value in WELL_KNOWN_PUBLIC:
        return False
    return address.is_global


def mask(value: str) -> str:
    """Keep the first octet so a reader can find the line, drop the rest."""
    return value.split(".", 1)[0] + ".x.x.x"


def scan_text(text: str) -> list[tuple[int, str]]:
    """Return ``(line_number, address)`` for each public IPv4 finding."""
    findings: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if EXEMPTION_MARKER in line:
            continue
        for match in DOTTED_IPV4.finditer(line):
            if VERSION_CONTEXT.search(line[: match.start()]):
                continue
            if is_public(match.group(1)):
                findings.append((lineno, match.group(1)))
        for match in EC2_PUBLIC_DNS.finditer(line):
            value = match.group(1).replace("-", ".")
            if is_public(value):
                findings.append((lineno, value))
    return findings


def tracked_files(root: Path) -> list[Path]:
    """Return git-tracked files worth scanning, relative to ``root``."""
    out = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", "ls-files", "-z"],  # noqa: S607 - git resolved from PATH by design
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [Path(name) for name in out.split("\0") if name and Path(name).suffix.lower() not in SKIP_SUFFIXES]


def scan_repository(root: Path) -> list[tuple[Path, int, str]]:
    """Scan every tracked text file and return all findings."""
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
        print(f"::error::{len(findings)} publicly routable IPv4 address(es) in tracked files. Values are masked.")
        for rel, lineno, value in findings:
            print(f"  {rel}:{lineno}: {mask(value)}")
        print()
        print("Replace with a documentation address (192.0.2.x, 198.51.100.x, 203.0.113.x)")
        print(f"or a placeholder such as <EC2_PUBLIC_IP>. If it must appear, mark the line `{EXEMPTION_MARKER}`.")
        return 1
    print("✅ No publicly routable IPv4 address in tracked files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
