#!/usr/bin/env python3
"""Insert OutputDestination parameters + conditions into a CloudFormation template
that already has EnableSnapStart and UseAutoOutputBucket.
"""

from __future__ import annotations

import sys
from pathlib import Path

PARAMS_BLOCK = """
  OutputDestination:
    Type: String
    Default: "STANDARD_S3"
    AllowedValues: ["STANDARD_S3", "FSXN_S3AP"]
    Description: |
      AI/ML 成果物の書き込み先。STANDARD_S3（デフォルト）は新しい S3 バケットに書き込み。
      FSXN_S3AP は FSxN S3 Access Point 経由でオリジナルデータと同一ボリュームに書き込み
      （"no data movement" パターン）。詳細: docs/aws-feature-requests/fsxn-s3ap-improvements.md

  OutputS3APAlias:
    Type: String
    Default: ""
    Description: |
      OutputDestination=FSXN_S3AP 時の出力先 S3 AP Alias。空なら入力用 S3AccessPointAlias を再利用。

  OutputS3APPrefix:
    Type: String
    Default: "ai-outputs/"
    Description: |
      OutputDestination=FSXN_S3AP 時、全出力キーに付与するプレフィックス。

  S3AccessPointName:
    Type: String
    Default: ""
    Description: |
      入力用 S3 Access Point の名前（alias ではなく）。指定すると AP ARN 形式でも
      IAM アクセスを許可する（FSxN S3AP の permission 判定で両形式をサポート）。

  OutputS3APName:
    Type: String
    Default: ""
    Description: |
      出力用 S3 AP の名前。空なら S3AccessPointName を再利用。
"""

CONDITIONS_BLOCK = """  UseStandardS3:
    !Equals [!Ref OutputDestination, "STANDARD_S3"]
  UseFsxnS3AP:
    !Equals [!Ref OutputDestination, "FSXN_S3AP"]
  UseInputApAsOutputAp:
    !Equals [!Ref OutputS3APAlias, ""]
  HasS3AccessPointName:
    !Not [!Equals [!Ref S3AccessPointName, ""]]
  UseInputApNameAsOutputApName:
    !Equals [!Ref OutputS3APName, ""]
"""


def patch(path: Path) -> bool:
    text = path.read_text()

    if "OutputDestination:" in text:
        print(f"ALREADY PATCHED: {path}")
        return False

    # 1. Insert Parameters block before the "# =========" that separates
    # "Parameters" from "Conditions"
    # Heuristic: before the "# === Conditions ===" section or before "Conditions:"
    marker = "\n# =====================================================================\n# Conditions\n# =====================================================================\n"
    if marker in text:
        text = text.replace(marker, PARAMS_BLOCK + marker, 1)
    else:
        # Fallback: insert before Conditions:
        text = text.replace("\nConditions:\n", "\n" + PARAMS_BLOCK + "\nConditions:\n", 1)

    # 2. Insert Conditions block right after UseAutoOutputBucket
    old_cond = """  UseAutoOutputBucket:
    !Equals [!Ref OutputBucketName, ""]
"""
    if old_cond not in text:
        # try single-line variant
        old_cond = '  UseAutoOutputBucket: !Equals [!Ref OutputBucketName, ""]\n'
    if old_cond in text:
        text = text.replace(old_cond, old_cond + CONDITIONS_BLOCK, 1)
    else:
        print(f"WARNING: Could not find UseAutoOutputBucket condition in {path}")

    # 3. Add Condition: UseStandardS3 to OutputBucket resource
    # Pattern:   OutputBucket:\n    Type: AWS::S3::Bucket\n    Properties:
    old_res = """  OutputBucket:
    Type: AWS::S3::Bucket
    Properties:"""
    new_res = """  OutputBucket:
    Type: AWS::S3::Bucket
    Condition: UseStandardS3
    Properties:"""
    if old_res in text:
        text = text.replace(old_res, new_res, 1)

    path.write_text(text)
    print(f"PATCHED: {path}")
    return True


def main() -> int:
    total = 0
    for arg in sys.argv[1:]:
        p = Path(arg)
        if not p.exists():
            print(f"MISSING: {p}", file=sys.stderr)
            continue
        if patch(p):
            total += 1
    return 0 if total else 1


if __name__ == "__main__":
    sys.exit(main())
