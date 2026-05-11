#!/usr/bin/env python3
"""Add S3AccessPointName parameter to template.yaml (SAM source) for all UCs.

This ensures that when create_deploy_template.py regenerates template-deploy.yaml,
the S3AccessPointName parameter and HasS3AccessPointName condition are preserved.

Idempotent: skips UCs that already have S3AccessPointName in template.yaml.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PARAM_BLOCK = """
  S3AccessPointName:
    Type: String
    Default: ""
    Description: |
      入力用 S3 Access Point の名前（alias ではなく）。指定すると AP ARN 形式でも
      IAM アクセスを許可する（FSxN S3AP の permission 判定で両形式をサポート）。
      空文字列の場合は alias 形式のみ許可。
"""

CONDITION_LINE = """  HasS3AccessPointName:
    !Not [!Equals [!Ref S3AccessPointName, ""]]
"""

ALL_UCS = [
    "legal-compliance",
    "financial-idp",
    "manufacturing-analytics",
    "media-vfx",
    "healthcare-dicom",
    "construction-bim",
    "genomics-pipeline",
    "energy-seismic",
    "autonomous-driving",
    "logistics-ocr",
    "insurance-claims",
    "retail-catalog",
    "semiconductor-eda",
    "education-research",
    "defense-satellite",
    "government-archives",
    "smart-city-geospatial",
]


def add_param_to_template(path: Path) -> bool:
    """Add S3AccessPointName param after S3AccessPointAlias. Returns True if modified."""
    content = path.read_text(encoding="utf-8")

    if "S3AccessPointName:" in content:
        return False  # Already present

    # Insert after S3AccessPointAlias block (find the end of its AllowedPattern line)
    # Pattern: S3AccessPointAlias: ... AllowedPattern: "..." \n\n
    pattern = r'(  S3AccessPointAlias:\n(?:.*\n)*?    AllowedPattern:.*\n)'
    match = re.search(pattern, content)
    if match:
        insert_pos = match.end()
        content = content[:insert_pos] + PARAM_BLOCK + content[insert_pos:]
    else:
        # Fallback: insert after first occurrence of S3AccessPointAlias block
        # Find the blank line after S3AccessPointAlias section
        alias_idx = content.find("  S3AccessPointAlias:")
        if alias_idx == -1:
            print(f"  WARN: No S3AccessPointAlias found in {path}")
            return False
        # Find next parameter (next line starting with "  " + capital letter after a blank line)
        next_param = re.search(r'\n\n  [A-Z]', content[alias_idx + 20:])
        if next_param:
            insert_pos = alias_idx + 20 + next_param.start() + 1  # after the \n\n
            content = content[:insert_pos] + PARAM_BLOCK + content[insert_pos:]
        else:
            print(f"  WARN: Could not find insertion point in {path}")
            return False

    # Add condition if not present
    if "HasS3AccessPointName:" not in content:
        # Find Conditions section
        cond_match = re.search(r'^Conditions:\s*\n', content, re.MULTILINE)
        if cond_match:
            insert_pos = cond_match.end()
            content = content[:insert_pos] + CONDITION_LINE + content[insert_pos:]
        else:
            # No Conditions section — add one before Resources
            res_match = re.search(r'^Resources:\s*\n', content, re.MULTILINE)
            if res_match:
                insert_pos = res_match.start()
                content = content[:insert_pos] + "Conditions:\n" + CONDITION_LINE + "\n" + content[insert_pos:]

    path.write_text(content, encoding="utf-8")
    return True


def main() -> int:
    repo = Path(__file__).resolve().parent.parent
    modified = 0
    for uc in ALL_UCS:
        tpl = repo / uc / "template.yaml"
        if not tpl.is_file():
            print(f"  SKIP: {tpl} not found")
            continue
        if add_param_to_template(tpl):
            print(f"  ✅ {uc}/template.yaml — S3AccessPointName added")
            modified += 1
        else:
            print(f"  ⏭️  {uc}/template.yaml — already has S3AccessPointName")

    print(f"\nModified {modified} template.yaml files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
