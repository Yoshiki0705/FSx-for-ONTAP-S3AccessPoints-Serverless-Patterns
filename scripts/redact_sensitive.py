#!/usr/bin/env python3
"""Redact sensitive environment-specific literals from tracked files.

Replaces account IDs, VPC IDs, subnet IDs, SG IDs, IPs, UUIDs with
placeholders so the scripts/docs can be published safely.

Strategy:
- Scripts (*.sh, *.py, *.yaml): replace with "<PLACEHOLDER>" default empty
  so users must supply via env vars
- Docs (*.md): replace with placeholder like "<ACCOUNT_ID>" (and similar)

Usage:
    python3 scripts/redact_sensitive.py [--dry-run]

Note:
    Sensitive strings are loaded from scripts/_sensitive_strings.py
    (which is gitignored). See scripts/_sensitive_strings.py.example
    for the expected format.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load sensitive strings from gitignored file
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _sensitive_strings import SENSITIVE_STRINGS  # noqa: E402
except ImportError:
    print("ERROR: scripts/_sensitive_strings.py not found.")
    print("Copy scripts/_sensitive_strings.py.example and fill in your values.")
    sys.exit(1)

# Build REDACTIONS from SENSITIVE_STRINGS
# Format: (pattern, replacement_in_scripts, replacement_in_docs)
# The _sensitive_strings.py should export REDACTION_RULES as a list of tuples
# or we build generic rules from SENSITIVE_STRINGS
try:
    from _sensitive_strings import REDACTION_RULES  # noqa: E402
    REDACTIONS = REDACTION_RULES
except ImportError:
    # Fallback: build generic redaction rules from SENSITIVE_STRINGS tuple
    REDACTIONS = [(s, "<REDACTED>", "<REDACTED>") for s in SENSITIVE_STRINGS]

# Files matched by this pattern are considered docs (different replacement style)
DOC_PATTERNS = ("*.md", "*.txt")


def is_doc_file(path: Path) -> bool:
    return any(path.match(pat) for pat in DOC_PATTERNS)


def redact_file(path: Path, dry_run: bool = False) -> int:
    """Redact sensitive literals in file. Returns number of replacements made."""
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, IsADirectoryError):
        return 0

    original = text
    total_subs = 0
    is_doc = is_doc_file(path)
    for pattern, script_repl, doc_repl in REDACTIONS:
        replacement = doc_repl if is_doc else script_repl
        new_text, n = re.subn(pattern, replacement, text)
        if n > 0:
            total_subs += n
            text = new_text

    if total_subs > 0 and text != original:
        if dry_run:
            print(f"  WOULD REDACT ({total_subs} subs): {path}")
        else:
            path.write_text(text, encoding="utf-8")
            print(f"  REDACTED ({total_subs} subs): {path}")
    return total_subs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="preview without writing")
    args = parser.parse_args()

    # Enumerate all tracked files (via git ls-files equivalent)
    import subprocess
    result = subprocess.run(
        ["git", "-C", str(PROJECT_ROOT), "ls-files"],
        capture_output=True, text=True, check=True,
    )
    files = [PROJECT_ROOT / f for f in result.stdout.splitlines() if f]

    # Exclude binary/PNG/ZIP files
    skip_suffixes = {".png", ".jpg", ".jpeg", ".zip", ".gz", ".pdf", ".segy",
                     ".dcm", ".fastq", ".gds", ".gds2", ".tif"}
    # Also exclude the redact script itself and known infrastructure scripts
    skip_files = {
        "scripts/redact_sensitive.py",  # this script itself
        "scripts/mask_uc_demos.py",  # contains SENSITIVE_STRINGS for safety verification
        "scripts/mask_phase7.py",  # same
    }

    grand_total = 0
    redacted_files = 0
    for p in files:
        if p.suffix.lower() in skip_suffixes:
            continue
        rel = p.relative_to(PROJECT_ROOT)
        if str(rel) in skip_files:
            continue
        if not p.exists():  # git ls-files may list deleted files
            continue
        n = redact_file(p, dry_run=args.dry_run)
        if n > 0:
            grand_total += n
            redacted_files += 1

    action = "WOULD REDACT" if args.dry_run else "REDACTED"
    print(f"\n{action}: {grand_total} literal occurrences across {redacted_files} files")


if __name__ == "__main__":
    main()
