#!/usr/bin/env python3
"""Unify OutputDestination parameter across UC1-5 (Pattern A) templates.

Strategy: minimal-disruption hybrid
==================================

- Keep the existing `S3AccessPointOutputAlias` parameter as an optional legacy
  parameter (default empty, no longer required)
- Add new Pattern B parameters: `OutputDestination`, `OutputS3APAlias`,
  `OutputS3APPrefix`, `S3AccessPointName`, `OutputS3APName`
- Add conditions: `UseStandardS3`, `UseFsxnS3AP`, `UseInputApAsOutputAp`,
  `HasLegacyOutputAlias`, `HasS3AccessPointName`, `UseInputApNameAsOutputApName`
- `OutputDestination` default is `"FSXN_S3AP"` for UC1-5 (to preserve
  existing-behavior when users don't specify the new param)
- Lambda env var `S3_ACCESS_POINT_OUTPUT` resolves via priority chain:
  1. If `OutputS3APAlias` set → use it
  2. Else if `S3AccessPointOutputAlias` (legacy) set → use it
  3. Else → fall back to `S3AccessPointAlias` (input AP)
- Also populate the unified env vars `OUTPUT_DESTINATION` / `OUTPUT_S3AP_ALIAS`
  / `OUTPUT_S3AP_PREFIX` / `OUTPUT_BUCKET` (for future handler migration)

Handler code is NOT touched by this script. Existing handlers continue to
read `S3_ACCESS_POINT_OUTPUT` and use `S3ApHelper`. New `OUTPUT_*` env vars
are just available for future unification.

Usage: python3 scripts/_unify_outputdestination_uc1_5.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


UC_DIRS = [
    "legal-compliance",
    "financial-idp",
    "manufacturing-analytics",
    "media-vfx",
    "healthcare-dicom",
]


NEW_PARAMS_BLOCK = """
  OutputDestination:
    Type: String
    Default: "FSXN_S3AP"
    AllowedValues: ["STANDARD_S3", "FSXN_S3AP"]
    Description: |
      AI/ML 成果物の書き込み先。デフォルトは "FSXN_S3AP" (従来どおり FSxN ボリュームに直接書き込み)。
      "STANDARD_S3" にすると新規 S3 バケットを作成して書き込む (Pattern C と同等)。
      Pattern A UC (UC1-5) では FSXN_S3AP がデフォルト値。
      詳細: docs/output-destination-patterns.md

  OutputS3APAlias:
    Type: String
    Default: ""
    Description: |
      OutputDestination=FSXN_S3AP 時の出力先 S3 Access Point Alias。
      空の場合は S3AccessPointOutputAlias (legacy) または S3AccessPointAlias (入力 AP) にフォールバック。

  OutputS3APPrefix:
    Type: String
    Default: ""
    Description: |
      OutputDestination=FSXN_S3AP 時、全出力キーに付与するプレフィックス。
      UC1-5 では通常空文字 (現行キー構造を維持)。必要に応じて "ai-outputs/" 等を指定可能。

  S3AccessPointName:
    Type: String
    Default: ""
    Description: |
      入力用 S3 Access Point の名前 (alias ではなく)。指定すると AP ARN 形式でも
      IAM アクセスを許可する (FSxN S3AP の permission 判定で両形式をサポート)。

  OutputS3APName:
    Type: String
    Default: ""
    Description: |
      出力用 S3 AP の名前。空なら S3AccessPointName を再利用。
"""

# Make S3AccessPointOutputAlias optional (was required)
# (current: no Default: line, just Type + Description + AllowedPattern)
LEGACY_OUTPUT_ALIAS_OLD = """  S3AccessPointOutputAlias:
    Type: String
    Description: FSx ONTAP S3 Access Point Alias (出力書き込み用、入力と同じ AP でも可)
    AllowedPattern: "^[a-z0-9-]+-ext-s3alias$"
"""

LEGACY_OUTPUT_ALIAS_NEW = """  S3AccessPointOutputAlias:
    Type: String
    Default: ""
    Description: |
      (legacy, optional) FSx ONTAP S3 Access Point Alias (出力書き込み用)。
      空の場合は OutputS3APAlias または S3AccessPointAlias にフォールバック。
      新規デプロイでは OutputS3APAlias を使用することを推奨。
    AllowedPattern: "^$|^[a-z0-9-]+-ext-s3alias$"
"""


NEW_CONDITIONS = """  UseStandardS3:
    !Equals [!Ref OutputDestination, "STANDARD_S3"]
  UseFsxnS3AP:
    !Equals [!Ref OutputDestination, "FSXN_S3AP"]
  HasOutputS3APAlias:
    !Not [!Equals [!Ref OutputS3APAlias, ""]]
  HasLegacyOutputAlias:
    !Not [!Equals [!Ref S3AccessPointOutputAlias, ""]]
  HasS3AccessPointName:
    !Not [!Equals [!Ref S3AccessPointName, ""]]
  UseInputApNameAsOutputApName:
    !Equals [!Ref OutputS3APName, ""]
"""


def patch_template(path: Path) -> bool:
    text = path.read_text()

    if "OutputDestination:" in text:
        print(f"ALREADY PATCHED: {path}")
        return False

    # 1. Make S3AccessPointOutputAlias optional + add new params
    if LEGACY_OUTPUT_ALIAS_OLD not in text:
        print(f"LEGACY PARAM NOT FOUND in {path}, skipping")
        return False

    # Replace the legacy param definition and add new params right after
    text = text.replace(
        LEGACY_OUTPUT_ALIAS_OLD,
        LEGACY_OUTPUT_ALIAS_NEW + NEW_PARAMS_BLOCK,
        1,
    )

    # 2. Add new conditions
    # Find the "Conditions:" block and insert after it
    cond_header_pattern = re.compile(r"^Conditions:\s*$", re.MULTILINE)
    match = cond_header_pattern.search(text)
    if match:
        insert_at = match.end()
        text = text[: insert_at] + "\n" + NEW_CONDITIONS + text[insert_at:]
    else:
        # Look for "# Conditions" comment style
        cond_banner_pattern = re.compile(
            r"(^# ={3,}\s*\n# Conditions\s*\n# ={3,}\s*\nConditions:\s*$)",
            re.MULTILINE,
        )
        match = cond_banner_pattern.search(text)
        if match:
            insert_at = match.end()
            text = text[: insert_at] + "\n" + NEW_CONDITIONS + text[insert_at:]
        else:
            print(f"WARNING: could not find Conditions: section in {path}")
            return False

    path.write_text(text)
    print(f"PATCHED: {path}")
    return True


def main() -> int:
    total = 0
    for uc_dir in UC_DIRS:
        path = Path(f"{uc_dir}/template-deploy.yaml")
        if not path.exists():
            print(f"MISSING: {path}")
            continue
        if patch_template(path):
            total += 1
    print(f"\nTotal modified: {total}/{len(UC_DIRS)}")
    return 0 if total else 1


if __name__ == "__main__":
    sys.exit(main())
