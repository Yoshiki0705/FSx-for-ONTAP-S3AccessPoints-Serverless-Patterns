#!/usr/bin/env python3
"""Gate: every pattern's samconfig.toml.example must be a deployable starting point.

Why this exists. The demo guides tell the operator to copy samconfig.toml.example,
replace the placeholders and deploy. That makes the example the real interface, so a
defect in it is a defect in the documented path. Two shapes were found on 2026-08-12,
both of which let a run look healthy while doing the wrong thing:

  1. Empty value on a parameter the template gates with a Has<Param> condition.
     17 examples shipped `S3AccessPointName=`. The condition
     `HasS3AccessPointName: !Not [!Equals [!Ref S3AccessPointName, ""]]` then drops the
     accesspoint-form ARNs from the IAM policy via !Ref AWS::NoValue, leaving only the
     bucket-form `arn:aws:s3:::${alias}`. Bucket-style ARNs do not authorize an S3 AP
     (docs/agent/pitfalls-s3ap-ontap.md calls this out as the most common error), so the
     stack deploys clean and every object access fails with AccessDenied at runtime.

  2. A required parameter missing entirely. 4 patterns had no example at all, and the
     inline `--parameter-overrides` blocks in the demo guides omit up to 5 parameters
     that the template declares with no Default -- following them verbatim cannot
     succeed, because CloudFormation rejects a missing required parameter.

Neither shape is visible to cfn-lint: the template is valid, and the example is not a
template. Nothing else in the repo reads these files, so without this check they rot
silently every time a parameter is added.

Usage: python3 scripts/check_samconfig_contract.py [--verbose]
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERBOSE = "--verbose" in sys.argv

PARAM_BLOCK = re.compile(r"\nParameters:\n(.*?)(?=\nConditions:|\nGlobals:|\nResources:|\nMappings:|\nOutputs:)", re.S)
# Anchored with re.M, not "\n  ", because PARAM_BLOCK's capture starts at the first
# parameter with no leading newline -- a "\n  " anchor silently drops it, and the first
# parameter is usually S3AccessPointAlias.
PARAM_ENTRY = re.compile(r"^  (\w+):\n((?:    .*\n)+)", re.M)


def template_parameters(text: str) -> tuple[set[str], set[str]]:
    """Collect the parameters a template declares.

    Args:
        text: Full text of the CloudFormation/SAM template.

    Returns:
        A pair of (every declared parameter name, those declared without a Default).
        Parameters without a Default must be supplied or the deployment cannot start.
    """
    block = PARAM_BLOCK.search(text)
    if not block:
        return set(), set()
    every, required = set(), set()
    for m in PARAM_ENTRY.finditer(block.group(1)):
        every.add(m.group(1))
        if not re.search(r"^    Default:", m.group(2), re.M):
            required.add(m.group(1))
    return every, required


def authorization_gated_parameters(text: str) -> set[str]:
    """Find parameters whose empty value strips an access-point ARN from an IAM policy.

    Deliberately narrower than "every parameter a Condition tests for emptiness". Many
    conditions treat empty as a legitimate choice -- an empty OutputBucketName means
    "create one for me", so flagging it would be noise. The defect worth failing on is
    the one that cannot be noticed until runtime: the condition's only job is to add an
    `...:accesspoint/...` Resource, so an empty value silently produces a policy that
    deploys clean and then denies every S3 AP access.

    Args:
        text: Full text of the CloudFormation/SAM template.

    Returns:
        Names of parameters gated by a condition that guards an accesspoint-form ARN.
    """
    emptiness_tested = set()
    for pattern in (
        r'!Not\s*\[\s*!Equals\s*\[\s*!Ref\s+(\w+)\s*,\s*""\s*\]\s*\]',
        r'!Equals\s*\[\s*!Ref\s+(\w+)\s*,\s*""\s*\]',
    ):
        emptiness_tested.update(m.group(1) for m in re.finditer(pattern, text))

    gated = set()
    for param in emptiness_tested:
        # The condition named after the parameter, e.g. HasS3AccessPointName.
        condition = None
        for m in re.finditer(r"^  (\w+):\s*\n?\s*!Not\s*\[\s*!Equals\s*\[\s*!Ref\s+" + param + r"\b", text, re.M):
            condition = m.group(1)
        if not condition:
            continue
        # Does any !If on that condition yield an accesspoint ARN?
        for m in re.finditer(r"!If\s*\n?\s*-\s*" + condition + r"\s*\n\s*-\s*(.+)", text):
            if "accesspoint" in m.group(1):
                gated.add(param)
                break
    return gated


def main() -> int:
    findings: list[str] = []
    checked = 0

    for pattern_dir in sorted((ROOT / "solutions" / "industry").iterdir()):
        template = pattern_dir / "template.yaml"
        example = pattern_dir / "samconfig.toml.example"
        if not template.is_file():
            continue
        checked += 1
        name = pattern_dir.name

        if not example.is_file():
            findings.append(f"{name}: samconfig.toml.example が無い（demo-guide はこれをコピーさせる）")
            continue

        try:
            config = tomllib.loads(example.read_text())
        except tomllib.TOMLDecodeError as exc:
            findings.append(f"{name}: samconfig.toml.example が TOML として壊れている: {exc}")
            continue

        overrides = config.get("default", {}).get("deploy", {}).get("parameters", {}).get("parameter_overrides", [])
        if isinstance(overrides, str):  # SAM also accepts one space-separated string
            overrides = overrides.split()
        values = {}
        for item in overrides:
            key, _, value = str(item).partition("=")
            values[key.strip()] = value.strip()

        text = template.read_text()
        every, required = template_parameters(text)
        gated = authorization_gated_parameters(text)

        for missing in sorted(required - set(values)):
            findings.append(
                f"{name}: 必須パラメータ {missing} が samconfig.toml.example に無い（Default が無いので指定しないとデプロイできない）"
            )

        for key in sorted(k for k, v in values.items() if not v):
            if key in gated:
                findings.append(
                    f"{name}: {key} が空。Condition が空を判定しているので、空のままデプロイすると静かに設定が外れる"
                )

        for unknown in sorted(set(values) - every):
            findings.append(
                f"{name}: samconfig.toml.example の {unknown} はテンプレートに存在しない（CloudFormation が拒否する）"
            )

        if VERBOSE:
            print(f"  {name}: {len(values)} params, {len(required)} required, {len(gated)} gated")

    if findings:
        print(f"SAMCONFIG CONTRACT: FAIL ({len(findings)} 件 / {checked} patterns)", file=sys.stderr)
        for f in findings:
            print(f"  {f}", file=sys.stderr)
        return 1

    print(f"SAMCONFIG CONTRACT: PASS ({checked} patterns)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
