#!/usr/bin/env python3
"""Fix misplaced XRayTracing permission statements inside IAM trust policies.

A permission statement (xray:PutTraceSegments/PutTelemetryRecords with Resource)
was mistakenly appended to AssumeRolePolicyDocument. Trust policies may only
contain sts:AssumeRole with a Principal. This:
  1. Removes the misplaced XRayTracing statement that follows `Action: sts:AssumeRole`.
  2. Adds the AWS-managed AWSXRayDaemonWriteAccess policy to each role's
     ManagedPolicyArns (preserving X-Ray functionality).

Usage: python3 scripts/fix_trust_policy_xray.py <template.yaml> [--write]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

XRAY_MANAGED = "arn:aws:iam::aws:policy/AWSXRayDaemonWriteAccess"

# The misplaced block, right after the AssumeRole statement.
MISPLACED_RE = re.compile(
    r'(\n[ \t]+Action:\s*sts:AssumeRole[ \t]*\n)'
    r'[ \t]+- Sid:\s*XRayTracing[ \t]*\n'
    r'[ \t]+Effect:\s*Allow[ \t]*\n'
    r'[ \t]+Action:[ \t]*\n'
    r'[ \t]+-\s*xray:PutTraceSegments[ \t]*\n'
    r'[ \t]+-\s*xray:PutTelemetryRecords[ \t]*\n'
    r'[ \t]+Resource:\s*"\*"[ \t]*\n'
)


def add_xray_managed(content: str) -> str:
    """Add AWSXRayDaemonWriteAccess after each ManagedPolicyArns: header once."""
    def repl(m: re.Match) -> str:
        ind = m.group("ind")
        block = m.group(0)
        if XRAY_MANAGED in block:
            return block
        return f"{ind}ManagedPolicyArns:\n{ind}  - {XRAY_MANAGED}\n" + block[len(f"{ind}ManagedPolicyArns:\n"):]

    return re.sub(
        r'^(?P<ind>[ \t]+)ManagedPolicyArns:[ \t]*\n',
        repl,
        content,
        flags=re.MULTILINE,
    )


def fix(content: str) -> str:
    content = MISPLACED_RE.sub(lambda m: m.group(1), content)
    content = add_xray_managed(content)
    return content


def main() -> int:
    path = Path(sys.argv[1])
    write = "--write" in sys.argv
    new = fix(path.read_text())
    if write:
        path.write_text(new)
        print(f"WROTE {path}")
    else:
        print(new)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
