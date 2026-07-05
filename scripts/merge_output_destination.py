#!/usr/bin/env python3
"""Merge the OutputDestination (FSx for ONTAP S3 AP write-back) feature from
template-deploy.yaml INTO a self-contained SAM template.yaml, preserving the
template's existing X-Ray / FPolicy / TriggerMode wiring.

Proven end-to-end on logistics-ocr (real AWS deploy, FSXN_S3AP + X-Ray retained).

Transforms (idempotent; skips if OutputDestination already present):
  1. Insert OutputDestination / S3AccessPointName / OutputS3AP* params before Conditions:
  2. Insert Output* conditions after Conditions:
  3. Add `Condition: UseStandardS3` to the OutputBucket resource
  4. Every `OUTPUT_BUCKET: !Ref OutputBucket` -> OUTPUT_DESTINATION + conditional bucket
     + OUTPUT_S3AP_ALIAS + OUTPUT_S3AP_PREFIX
  5. Every S3OutputBucketWrite `Resource: [- ${OutputBucket.Arn}/*]` -> conditional
     STANDARD_S3 bucket / FSXN_S3AP access-point ARN

Usage: python3 scripts/merge_output_destination.py <pattern-dir> [--write]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PARAMS = """  # --- OutputDestination (Pattern B: FSx for ONTAP S3 AP write-back) ---
  OutputDestination:
    Type: String
    Default: "STANDARD_S3"
    AllowedValues: ["STANDARD_S3", "FSXN_S3AP"]
    Description: >
      AI/ML 成果物の書き込み先。STANDARD_S3 は新規 S3 バケット、FSXN_S3AP は FSx for ONTAP
      S3 Access Point 経由でオリジナルと同一ボリュームへ書き戻す（no data movement）。
  S3AccessPointName:
    Type: String
    Default: ""
    Description: 入力用 S3 AP 名（ARN 形式 IAM 許可用）。空なら alias 形式のみ。
  OutputS3APAlias:
    Type: String
    Default: ""
    Description: FSXN_S3AP 出力先 S3 AP Alias。空なら入力 S3AccessPointAlias を再利用。
  OutputS3APName:
    Type: String
    Default: ""
    Description: 出力用 S3 AP 名。空なら S3AccessPointName を再利用。
  OutputS3APPrefix:
    Type: String
    Default: "ai-outputs/"
    Description: FSXN_S3AP 出力キーのプレフィックス。

"""

CONDITIONS = """  # --- OutputDestination Conditions ---
  UseStandardS3:
    !Equals [!Ref OutputDestination, "STANDARD_S3"]
  UseFsxnS3AP:
    !Equals [!Ref OutputDestination, "FSXN_S3AP"]
  UseInputApAsOutputAp:
    !Equals [!Ref OutputS3APAlias, ""]
  UseInputApNameAsOutputApName:
    !Equals [!Ref OutputS3APName, ""]
  HasS3AccessPointName:
    !Not [!Equals [!Ref S3AccessPointName, ""]]
"""


def env_block(indent: str) -> str:
    i = indent
    return (
        f"{i}OUTPUT_DESTINATION: !Ref OutputDestination\n"
        f'{i}OUTPUT_BUCKET: !If [UseStandardS3, !Ref OutputBucket, ""]\n'
        f"{i}OUTPUT_S3AP_ALIAS:\n"
        f"{i}  !If\n"
        f"{i}    - UseFsxnS3AP\n"
        f"{i}    - !If [UseInputApAsOutputAp, !Ref S3AccessPointAlias, !Ref OutputS3APAlias]\n"
        f'{i}    - ""\n'
        f"{i}OUTPUT_S3AP_PREFIX: !Ref OutputS3APPrefix"
    )


def iam_block(indent: str) -> str:
    # indent is the indent of `Resource:` line
    i = indent
    return (
        f"{i}Resource: !If\n"
        f"{i}  - UseStandardS3\n"
        f'{i}  - - !Sub "${{OutputBucket.Arn}}/*"\n'
        f"{i}  - !If\n"
        f"{i}    - HasS3AccessPointName\n"
        f"{i}    - - !Sub\n"
        f'{i}        - "arn:aws:s3:::${{Alias}}/*"\n'
        f"{i}        - Alias: !If [UseInputApAsOutputAp, !Ref S3AccessPointAlias, !Ref OutputS3APAlias]\n"
        f"{i}      - !Sub\n"
        f'{i}        - "arn:aws:s3:${{AWS::Region}}:${{AWS::AccountId}}:accesspoint/${{Name}}/object/*"\n'
        f"{i}        - Name: !If [UseInputApNameAsOutputApName, !Ref S3AccessPointName, !Ref OutputS3APName]\n"
        f"{i}    - - !Sub\n"
        f'{i}        - "arn:aws:s3:::${{Alias}}/*"\n'
        f"{i}        - Alias: !If [UseInputApAsOutputAp, !Ref S3AccessPointAlias, !Ref OutputS3APAlias]"
    )


def merge(text: str) -> tuple[str, list[str]]:
    notes: list[str] = []
    if "OutputDestination:" in text:
        return text, ["skip: OutputDestination already present"]

    # 1. params before top-level Conditions:
    if "\nConditions:\n" not in text:
        return text, ["ERROR: no top-level Conditions: section"]
    params = PARAMS
    if "S3AccessPointName:" in text:
        # already has S3AccessPointName; drop it from our params block
        params = re.sub(r"  S3AccessPointName:\n(?:    .*\n)+?(?=  [A-Za-z])", "", params, count=1)
    text = text.replace("\nConditions:\n", "\n" + params + "Conditions:\n", 1)

    # 2. conditions after Conditions:
    conditions = CONDITIONS
    if "HasS3AccessPointName:" in text:
        conditions = conditions.replace(
            '  HasS3AccessPointName:\n    !Not [!Equals [!Ref S3AccessPointName, ""]]\n', ""
        )
    text = text.replace("Conditions:\n", "Conditions:\n" + conditions, 1)

    # 3. OutputBucket condition
    text, n = re.subn(
        r"(\n  OutputBucket:\n    Type: AWS::S3::Bucket\n)(    Properties:)",
        r"\1    Condition: UseStandardS3\n\2",
        text,
        count=1,
    )
    notes.append(f"OutputBucket condition: {n}")

    # 4. env blocks
    def env_repl(m: re.Match) -> str:
        return env_block(m.group("ind"))

    text, ne = re.subn(
        r"^(?P<ind>[ \t]+)OUTPUT_BUCKET: !Ref OutputBucket$",
        env_repl,
        text,
        flags=re.MULTILINE,
    )
    notes.append(f"env blocks: {ne}")

    # 5. IAM output-write resource blocks
    def iam_repl(m: re.Match) -> str:
        return iam_block(m.group("ind"))

    text, ni = re.subn(
        r"^(?P<ind>[ \t]+)Resource:\n[ \t]+- !Sub \"\$\{OutputBucket\.Arn\}/\*\"$",
        iam_repl,
        text,
        flags=re.MULTILINE,
    )
    notes.append(f"iam blocks: {ni}")

    # 5b. inline-form IAM output-write: `Resource: !Sub "${OutputBucket.Arn}/*"`
    def iam_inline_repl(m: re.Match) -> str:
        return iam_block(m.group("ind"))

    text, ni2 = re.subn(
        r'^(?P<ind>[ \t]+)Resource: !Sub "\$\{OutputBucket\.Arn\}/\*"$',
        iam_inline_repl,
        text,
        flags=re.MULTILINE,
    )
    notes.append(f"iam inline blocks: {ni2}")
    return text, notes


def main() -> int:
    pattern_dir = Path(sys.argv[1])
    write = "--write" in sys.argv
    tpl = pattern_dir / "template.yaml"
    new, notes = merge(tpl.read_text())
    if write and "skip" not in notes[0] and not notes[0].startswith("ERROR"):
        tpl.write_text(new)
    print(f"{pattern_dir.name}: {notes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
