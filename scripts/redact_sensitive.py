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
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# (pattern_in_file, replacement_in_scripts, replacement_in_docs)
REDACTIONS = [
    (r"178625946981",
     r"<ACCOUNT_ID>",
     r"<ACCOUNT_ID>"),
    (r"fsvol-0f7ab3a0723676e7c",
     r"<FSX_VOLUME_ID>",
     r"<FSX_VOLUME_ID>"),
    (r"fsvol-0ac1d08a1709b97ba", r"<FSX_VOLUME_ID>", r"<FSX_VOLUME_ID>"),
    (r"fsvol-0647183905872652c", r"<FSX_VOLUME_ID>", r"<FSX_VOLUME_ID>"),
    (r"fsvol-0c583905429e614d7", r"<FSX_VOLUME_ID>", r"<FSX_VOLUME_ID>"),
    (r"fs-09ffe72a3b2b7dbbd", r"<FSX_FILE_SYSTEM_ID>", r"<FSX_FILE_SYSTEM_ID>"),
    (r"svm-0d5f81cd0146af242", r"<SVM_ID>", r"<SVM_ID>"),
    (r"9ae87e42-068a-11f1-b1ff-ada95e61ee66", r"<SVM_UUID>", r"<SVM_UUID>"),
    (r"4bc997e8-4b06-11f1-acbd-21ab1e8e6bf5", r"<VOLUME_UUID>", r"<VOLUME_UUID>"),
    (r"vpc-0ae01826f906191af", r"<VPC_ID>", r"<VPC_ID>"),
    (r"sg-07be65398316491d8", r"<SG_ID>", r"<SG_ID>"),
    (r"sg-026b3207d8324b5e4", r"<SG_ID>", r"<SG_ID>"),
    (r"sg-0e199c3aab717888c", r"<SG_ID>", r"<SG_ID>"),
    (r"sg-0567bc078bfd6ef70", r"<SG_ID>", r"<SG_ID>"),
    (r"subnet-0307ebbd55b35c842", r"<SUBNET_ID>", r"<SUBNET_ID>"),
    (r"subnet-0af86ebd3c65481b8", r"<SUBNET_ID>", r"<SUBNET_ID>"),
    (r"rtb-0c7c5f7aa89d19592", r"<ROUTE_TABLE_ID>", r"<ROUTE_TABLE_ID>"),
    (r"rtb-0b04b4ff2589e19fe", r"<ROUTE_TABLE_ID>", r"<ROUTE_TABLE_ID>"),
    (r"10\.0\.3\.72", r"<ONTAP_MGMT_IP>", r"<ONTAP_MGMT_IP>"),
    (r"3\.112\.208\.171", r"<EC2_PUBLIC_IP>", r"<EC2_PUBLIC_IP>"),
    (r"i-009b81a634ffa9099", r"<EC2_INSTANCE_ID>", r"<EC2_INSTANCE_ID>"),
    (r"yoshiki\.fujiwara@netapp\.com", r"<NOTIFICATION_EMAIL>", r"<NOTIFICATION_EMAIL>"),
    # S3 AP alias contains the account info bucket name
    (r"eda-demo-s3ap-fnwqydfpmd4gabncr8xqepjrrt131apn1a-ext-s3alias",
     r"<S3_AP_ALIAS>", r"<S3_AP_ALIAS>"),
    (r"fsvol-0f7ab3a",   r"<FSX_VOLUME_ID>", r"<FSX_VOLUME_ID>"),  # catch partial
]

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
