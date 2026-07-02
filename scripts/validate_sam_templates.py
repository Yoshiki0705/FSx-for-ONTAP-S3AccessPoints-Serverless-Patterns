#!/usr/bin/env python3
"""Regression guard for Issue #53: ensure every pattern `template.yaml` is a
deployable self-contained SAM template.

Checks each solutions/**/template.yaml:
  1. Declares `Transform: AWS::Serverless-2016-10-31`.
  2. Every Lambda/Serverless function has a code source: `CodeUri` (Serverless),
     inline/S3 `Code` (Lambda), or a `CodeUri` defined in Globals. A function
     with no code source fails `sam build`/deploy (the Issue #53 failure mode).

Exit code 0 = all good; 1 = one or more violations (CI-friendly).

Usage: python3 scripts/validate_sam_templates.py
"""
from __future__ import annotations

import glob
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FUNC_TYPES = ("AWS::Serverless::Function", "AWS::Lambda::Function")


def check(path: Path) -> list[str]:
    text = path.read_text()
    errors: list[str] = []

    # SAM Transform is required only when the template uses AWS::Serverless:: resources.
    if "AWS::Serverless::" in text and "AWS::Serverless-2016-10-31" not in text:
        errors.append("uses AWS::Serverless:: resources but missing SAM Transform")

    globals_codeuri = "\nGlobals:" in text and "CodeUri:" in text.split("Resources:", 1)[0]

    # Guard: no permission statement (Resource/xray) inside an IAM trust policy.
    # (Regression guard for the misplaced XRayTracing statement bug.)
    for tm2 in re.finditer(r"AssumeRolePolicyDocument:\n(?P<body>(?:[ \t]+.*\n)+)", text):
        body = tm2.group("body")
        # trust-policy body ends where indentation returns to the role's property level;
        # take only the tightly-indented lines belonging to the document.
        if re.search(r"\n[ \t]+Resource:", body[: body.find("\n") + 4000]):
            # crude but effective: a genuine trust policy has no Resource key
            first_chunk = "\n".join(body.split("\n")[:12])
            if "Resource:" in first_chunk:
                errors.append("IAM trust policy (AssumeRolePolicyDocument) contains a "
                              "Resource/permission statement (must be sts:AssumeRole only)")
                break

    lines = text.split("\n")
    n = len(lines)
    # Move to the Resources section.
    i = 0
    while i < n and not lines[i].startswith("Resources:"):
        i += 1
    i += 1
    while i < n:
        line = lines[i]
        if line and not line[0].isspace() and not line.startswith("#"):
            break  # left the Resources section
        m = re.match(r"^  ([A-Za-z0-9]+):\s*$", line)
        if m:
            j = i + 1
            body: list[str] = []
            while j < n and (lines[j].startswith("    ") or lines[j].strip() == ""):
                body.append(lines[j])
                j += 1
            btext = "\n".join(body)
            tm = re.search(r"Type:\s*(AWS::\S+)", btext)
            rtype = tm.group(1) if tm else ""
            if rtype in FUNC_TYPES:
                has_code = "CodeUri:" in btext or "Code:" in btext or globals_codeuri
                if not has_code:
                    errors.append(f"{m.group(1)} ({rtype}) has no CodeUri/Code")
            i = j
            continue
        i += 1

    return errors


def main() -> int:
    templates = sorted(
        t for t in glob.glob(str(ROOT / "solutions" / "**" / "template.yaml"), recursive=True)
        if ".aws-sam" not in t
    )
    failures = 0
    for t in templates:
        errs = check(Path(t))
        if errs:
            failures += 1
            print(f"FAIL {Path(t).relative_to(ROOT)}")
            for e in errs:
                print(f"     - {e}")
    print(f"\n{len(templates) - failures}/{len(templates)} template.yaml are valid self-contained SAM")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
