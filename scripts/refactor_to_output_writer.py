#!/usr/bin/env python3
"""Refactor Lambda handlers to use OutputWriter instead of direct s3.put_object.

Targets handlers that:
1. Import `boto3`
2. Read `OUTPUT_BUCKET` from environment
3. Call `boto3.client("s3").put_object(Bucket=output_bucket, Key=..., Body=..., ContentType=...)`

Transforms them to:
1. Import `from shared.output_writer import OutputWriter`
2. Use `OutputWriter.from_env()`
3. Call `output_writer.put_json(key=..., data=...)` or `put_text` / `put_bytes`

Usage:
    python3 scripts/refactor_to_output_writer.py <handler.py> [--dry-run]

This tool is idempotent and safe to re-run.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def refactor_handler(path: Path, dry_run: bool = False) -> bool:
    """Refactor a single handler. Returns True if modified."""
    text = path.read_text()
    original = text

    # Skip if already using OutputWriter
    if "from shared.output_writer import OutputWriter" in text:
        print(f"  SKIP (already refactored): {path}")
        return False

    # 1. Add OutputWriter import after s3ap_helper import (if present)
    if "from shared.s3ap_helper import S3ApHelper" in text:
        text = text.replace(
            "from shared.s3ap_helper import S3ApHelper",
            "from shared.output_writer import OutputWriter\nfrom shared.s3ap_helper import S3ApHelper",
            1,
        )
    elif "from shared.exceptions import" in text:
        text = text.replace(
            "from shared.exceptions import lambda_error_handler",
            "from shared.exceptions import lambda_error_handler\nfrom shared.output_writer import OutputWriter",
            1,
        )

    # 2. Update docstring environment variable section
    # Replace "OUTPUT_BUCKET: S3 出力バケット名" with the full set
    new_env_docstring = """OUTPUT_DESTINATION: `STANDARD_S3` or `FSXN_S3AP` (デフォルト: `STANDARD_S3`)
    OUTPUT_BUCKET: STANDARD_S3 モードの出力バケット名
    OUTPUT_S3AP_ALIAS: FSXN_S3AP モードの S3AP Alias or ARN
    OUTPUT_S3AP_PREFIX: FSXN_S3AP モードの出力プレフィックス (デフォルト: `ai-outputs/`)"""

    # Try matching common patterns
    for pat in [
        r"    OUTPUT_BUCKET: S3 出力バケット名",
        r"    OUTPUT_BUCKET: 出力 S3 バケット名",
        r"    OUTPUT_BUCKET: 出力バケット名",
    ]:
        if re.search(pat, text):
            text = re.sub(pat, f"    {new_env_docstring}", text, count=1)
            break

    # 3. Replace output_bucket variable assignment with output_writer
    # Pattern:   output_bucket = os.environ["OUTPUT_BUCKET"]
    # Replace:   output_writer = OutputWriter.from_env()
    text = re.sub(
        r'    output_bucket\s*=\s*os\.environ\["OUTPUT_BUCKET"\]',
        "    output_writer = OutputWriter.from_env()",
        text,
    )

    # 4. Replace s3_client.put_object block with output_writer.put_json/put_text/put_bytes
    # This is the tricky part. We replace specific patterns.

    # Pattern A: JSON output
    #     s3_client = boto3.client("s3")
    #     s3_client.put_object(
    #         Bucket=output_bucket,
    #         Key=output_key,
    #         Body=json.dumps(XXX, default=str, ensure_ascii=False).encode("utf-8"),
    #         ContentType="application/json; charset=utf-8",
    #     )
    # OR Body=json.dumps(XXX, default=str).encode("utf-8"),
    # OR ContentType="application/json",

    pattern_json = re.compile(
        r'(\s+)s3_client\s*=\s*boto3\.client\(["\']s3["\']\)\s*\n'
        r'\s+s3_client\.put_object\(\s*\n'
        r'\s+Bucket=output_bucket,\s*\n'
        r'\s+Key=(\w+),\s*\n'
        r'\s+Body=json\.dumps\(([^)]+?)\)\.encode\(["\']utf-8["\']\),\s*\n'
        r'\s+ContentType=["\']application/json(?:; charset=utf-8)?["\'],\s*\n'
        r'\s+\)',
        re.MULTILINE,
    )

    def replace_json_put(m: re.Match) -> str:
        indent = m.group(1)
        key_var = m.group(2)
        dumps_args = m.group(3).strip()
        # Extract the data variable (first arg of json.dumps)
        data_var = dumps_args.split(",")[0].strip()
        return f"{indent}output_writer.put_json(key={key_var}, data={data_var})"

    text = pattern_json.sub(replace_json_put, text)

    # Pattern B: Text output
    #     s3_client.put_object(
    #         Bucket=output_bucket,
    #         Key=output_key,
    #         Body=something.encode("utf-8"),
    #         ContentType="text/plain; charset=utf-8",
    #     )
    pattern_text = re.compile(
        r'(\s+)s3_client\.put_object\(\s*\n'
        r'\s+Bucket=output_bucket,\s*\n'
        r'\s+Key=(\w+),\s*\n'
        r'\s+Body=(\w+)\.encode\(["\']utf-8["\']\),\s*\n'
        r'\s+ContentType=["\']text/plain(?:; charset=utf-8)?["\'],\s*\n'
        r'\s+\)',
        re.MULTILINE,
    )

    def replace_text_put(m: re.Match) -> str:
        indent = m.group(1)
        key_var = m.group(2)
        text_var = m.group(3)
        return f"{indent}output_writer.put_text(key={key_var}, text={text_var})"

    text = pattern_text.sub(replace_text_put, text)

    # 5. Replace plain s3://{output_bucket}/{key} string refs with output_writer.build_s3_uri(key)
    # Optional; keep as best-effort

    if text == original:
        print(f"  NO CHANGES (could not auto-refactor): {path}")
        return False

    if dry_run:
        print(f"  DRY RUN (would modify): {path}")
        return True

    path.write_text(text)
    print(f"  REFACTORED: {path}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="Handler files to refactor")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change")
    args = parser.parse_args()

    modified = 0
    for p in args.paths:
        if not p.exists():
            print(f"  MISSING: {p}", file=sys.stderr)
            continue
        if refactor_handler(p, dry_run=args.dry_run):
            modified += 1

    print(f"\n{'DRY RUN: would modify' if args.dry_run else 'Modified'} {modified} file(s)")
    return 0 if modified else 1


if __name__ == "__main__":
    sys.exit(main())
