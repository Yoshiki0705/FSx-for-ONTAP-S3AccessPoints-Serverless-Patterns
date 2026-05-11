#!/usr/bin/env python3
"""Validate S3 Access Point IAM policy patterns across all UC templates.

This script catches the bug pattern discovered in Phase 8 Batch 3 verification:
  - Discovery Lambda roles that grant s3:PutObject on S3 Access Point
    only via alias format (arn:aws:s3:::<alias>/*), missing the full
    ARN format (arn:aws:s3:<region>:<account>:accesspoint/<name>/object/*).

When boto3 S3 clients make requests with --endpoint-url-style or when
certain SDKs reference the S3AP via the access point name (not alias),
AWS IAM evaluates the request against the full ARN format. Policies
that only list the alias format will fail with AccessDenied.

Correct pattern:
    Resource: !If
      - HasS3AccessPointName
      - - !Sub "arn:aws:s3:::${S3AccessPointAlias}/*"
        - !Sub "arn:aws:s3:${AWS::Region}:${AWS::AccountId}:accesspoint/${S3AccessPointName}/object/*"
      - - !Sub "arn:aws:s3:::${S3AccessPointAlias}/*"

This script exits with non-zero if any template has the bug pattern.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# UC directories to scan
UC_DIRS = [
    "legal-compliance",
    "financial-idp",
    "manufacturing-analytics",
    "media-vfx",
    "healthcare-dicom",
    "semiconductor-eda",
    "genomics-pipeline",
    "energy-seismic",
    "autonomous-driving",
    "construction-bim",
    "retail-catalog",
    "logistics-ocr",
    "education-research",
    "insurance-claims",
    "defense-satellite",
    "government-archives",
    "smart-city-geospatial",
]


def check_template(template_path: Path) -> list[str]:
    """Check a template for S3AP IAM policy bugs.

    Returns list of issues found, empty list if clean.
    """
    if not template_path.exists():
        return [f"Template not found: {template_path}"]

    content = template_path.read_text()
    issues: list[str] = []
    lines = content.split("\n")

    def get_line_number(pos: int) -> int:
        """Get 1-indexed line number for character position."""
        return content[:pos].count("\n") + 1

    def is_in_if_block(block_line: int) -> bool:
        """Check if block at `block_line` is inside `!If HasS3AccessPointName`."""
        if block_line < 2:
            return False
        block_text = lines[block_line - 1]
        block_indent = len(block_text) - len(block_text.lstrip())

        for i in range(block_line - 2, max(0, block_line - 20), -1):
            line = lines[i]
            stripped = line.strip()
            if "HasS3AccessPointName" in stripped and stripped.startswith("-"):
                line_indent = len(line) - len(line.lstrip())
                if line_indent <= block_indent:
                    return True
            if stripped and (stripped.startswith("- Sid:") or stripped.startswith("- Effect:")):
                line_indent = len(line) - len(line.lstrip())
                if line_indent < block_indent:
                    break
        return False

    # Pattern 1: Statement blocks with "Sid: S3...Write/Output" containing PutObject
    pattern_sid = re.compile(
        r'(Sid:\s*(S3(?:AccessPoint|AP\w*)?\w*(?:Write|Output\w*))\s*\n'
        r'(?:[^-]*\n)*?'
        r'\s*Action:\s*\n'
        r'(?:\s*-\s*s3:(?:PutObject|DeleteObject|AbortMultipartUpload|CompleteMultipartUpload)\w*\s*\n)+'
        r'\s*Resource:\s*(?:(?!Sid:).)*?)'
        r'(?=\s*-\s*Sid:|\nResources:|$)',
        re.DOTALL,
    )

    # Pattern 2: Statement blocks WITHOUT Sid but with "Action: [s3:PutObject]" (inline style)
    pattern_inline = re.compile(
        r'(Effect:\s*Allow\s*\n'
        r'\s*Action:\s*\[(?:[^\]]*s3:PutObject[^\]]*)\]\s*\n'
        r'\s*Resource:\s*(?:(?!Effect:|Sid:).)*?)'
        r'(?=\s*-\s*Effect:|\s*-\s*Sid:|\s+PolicyName:|$)',
        re.DOTALL,
    )

    all_matches = []

    # Collect Sid-style matches
    for match in pattern_sid.finditer(content):
        block = match.group(1)
        sid = match.group(2)
        block_line = get_line_number(match.start())
        all_matches.append((block, sid, block_line, "Sid"))

    # Collect inline-style matches (no Sid)
    for match in pattern_inline.finditer(content):
        block = match.group(1)
        block_line = get_line_number(match.start())
        # Skip if this block is part of a Sid block already counted
        is_in_sid = any(
            sm_line <= block_line <= sm_line + sm_block.count("\n")
            for sm_block, _, sm_line, _ in all_matches
        )
        if not is_in_sid:
            all_matches.append((block, "(no Sid)", block_line, "inline"))

    for block, sid, block_line, style in all_matches:
        # Check if this block uses HasS3AccessPointName conditional directly
        has_direct_conditional = "HasS3AccessPointName" in block
        has_arn_format = "accesspoint/" in block
        has_alias_format = (
            "S3AccessPointAlias" in block or "OutputS3APAlias" in block
        )

        # Skip blocks that reference only OutputBucket (standard S3)
        only_output_bucket = (
            "OutputBucket" in block and not has_alias_format
        )
        if only_output_bucket:
            continue

        # Skip if this block is inside an !If HasS3AccessPointName wrapper
        if is_in_if_block(block_line):
            continue

        # Issue: alias-only without any conditional
        if has_alias_format and not has_arn_format and not has_direct_conditional:
            issues.append(
                f"  {sid} (line {block_line}, style={style}): "
                f"Missing ARN format — uses only alias. "
                f"Add !If HasS3AccessPointName block with "
                f"arn:aws:s3:${{AWS::Region}}:${{AWS::AccountId}}:accesspoint/"
                f"${{S3AccessPointName}}/object/* resource."
            )

    return issues


def main() -> int:
    """Main entry point."""
    project_root = Path(__file__).parent.parent
    total_issues = 0
    templates_checked = 0

    for uc_dir in UC_DIRS:
        template = project_root / uc_dir / "template-deploy.yaml"
        if not template.exists():
            continue
        templates_checked += 1
        issues = check_template(template)
        if issues:
            print(f"{uc_dir}/template-deploy.yaml:")
            for issue in issues:
                print(issue)
                total_issues += 1

    print()
    print(f"Scanned {templates_checked} templates.")
    if total_issues == 0:
        print("✅ All S3AP write policies have correct dual-format (alias + ARN).")
        return 0
    else:
        print(f"❌ Found {total_issues} S3AP IAM policy issues.")
        print(
            "\nFix: Update the Resource block to use !If HasS3AccessPointName "
            "conditional with both alias and full ARN formats. See "
            "scripts/check_s3ap_iam_patterns.py docstring for example."
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
