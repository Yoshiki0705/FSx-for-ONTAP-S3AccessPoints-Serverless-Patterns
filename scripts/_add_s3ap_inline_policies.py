#!/usr/bin/env python3
"""Add inline S3AP PutObject policies to Lambda roles in a template.

Strategy: for each `AWS::IAM::Role` that has a `Policies` block containing
`s3:PutObject`, append a conditional S3AP-writing policy statement.

This runs ONCE per template. Subsequent runs detect the added policy and skip.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# The new IAM statement to add (after existing PutObject statement inside each role)
# Matches handlers that write to `${OutputBucket.Arn}/*`
NEW_STATEMENT = """              - Sid: S3APOutputWrite
                Effect: !If [UseFsxnS3AP, "Allow", "Deny"]
                Action:
                  - s3:PutObject
                Resource: !If
                  - UseFsxnS3AP
                  - !If
                    - HasS3AccessPointName
                    - - !Sub
                        - "arn:aws:s3:::${Alias}/*"
                        - Alias: !If [UseInputApAsOutputAp, !Ref S3AccessPointAlias, !Ref OutputS3APAlias]
                      - !Sub
                        - "arn:aws:s3:${AWS::Region}:${AWS::AccountId}:accesspoint/${Name}/object/*"
                        - Name: !If [UseInputApNameAsOutputApName, !Ref S3AccessPointName, !Ref OutputS3APName]
                    - - !Sub
                        - "arn:aws:s3:::${Alias}/*"
                        - Alias: !If [UseInputApAsOutputAp, !Ref S3AccessPointAlias, !Ref OutputS3APAlias]
                  - - !Ref AWS::NoValue"""

# The simplest heuristic is to search for occurrences of `Resource: !Sub "${OutputBucket.Arn}/*"`
# and right after that block, insert our new statement. CloudFormation allows
# Effect: Deny to make it a no-op when UseFsxnS3AP=false.

# But using Effect: !If is not valid in IAM. We need conditional inclusion.
# Better approach: replace the existing "Resource: !Sub ${OutputBucket.Arn}/*" with
# a dual resource using !If [UseStandardS3, ...]

# SIMPLER approach: find `Resource: !Sub "${OutputBucket.Arn}/*"` in PutObject
# statements and replace with conditional dual resources.

PUT_OBJECT_RESOURCE_OLD = '                Resource:\n                  - !Sub "${OutputBucket.Arn}/*"'
PUT_OBJECT_RESOURCE_NEW = """                Resource: !If
                  - UseStandardS3
                  - - !Sub "${OutputBucket.Arn}/*"
                  - !If
                    - HasS3AccessPointName
                    - - !Sub
                        - "arn:aws:s3:::${Alias}/*"
                        - Alias: !If [UseInputApAsOutputAp, !Ref S3AccessPointAlias, !Ref OutputS3APAlias]
                      - !Sub
                        - "arn:aws:s3:${AWS::Region}:${AWS::AccountId}:accesspoint/${Name}/object/*"
                        - Name: !If [UseInputApNameAsOutputApName, !Ref S3AccessPointName, !Ref OutputS3APName]
                    - - !Sub
                        - "arn:aws:s3:::${Alias}/*"
                        - Alias: !If [UseInputApAsOutputAp, !Ref S3AccessPointAlias, !Ref OutputS3APAlias]"""


def patch(path: Path) -> int:
    text = path.read_text()
    count = text.count(PUT_OBJECT_RESOURCE_OLD)
    if count == 0:
        print(f"NO MATCHES: {path}")
        return 0
    if "UseStandardS3" not in text:
        print(f"WARNING: UseStandardS3 condition not found in {path}, skipping")
        return 0
    # Check if already patched (look for the new pattern)
    if 'Resource: !If\n                  - UseStandardS3' in text:
        # Count only occurrences that haven't been replaced
        already = text.count('Resource: !If\n                  - UseStandardS3')
        print(f"ALREADY PARTIALLY PATCHED: {path} ({already} instances already patched, {count} remaining)")

    text = text.replace(PUT_OBJECT_RESOURCE_OLD, PUT_OBJECT_RESOURCE_NEW)
    path.write_text(text)
    print(f"PATCHED {count} PutObject resources in {path}")
    return count


def main() -> int:
    total = 0
    for arg in sys.argv[1:]:
        p = Path(arg)
        if not p.exists():
            print(f"MISSING: {p}", file=sys.stderr)
            continue
        total += patch(p)
    return 0 if total else 1


if __name__ == "__main__":
    sys.exit(main())
