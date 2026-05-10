#!/usr/bin/env python3
"""One-shot helper: expand `OUTPUT_BUCKET: !Ref OutputBucket` to the
OutputDestination-aware set of env vars across all Lambda blocks in a template.
"""

from __future__ import annotations

import sys
from pathlib import Path

EXPAND_BLOCK = """          OUTPUT_DESTINATION: !Ref OutputDestination
          OUTPUT_BUCKET: !If [UseStandardS3, !Ref OutputBucket, ""]
          OUTPUT_S3AP_ALIAS:
            !If
              - UseFsxnS3AP
              - !If [UseInputApAsOutputAp, !Ref S3AccessPointAlias, !Ref OutputS3APAlias]
              - ""
          OUTPUT_S3AP_PREFIX: !Ref OutputS3APPrefix"""

NEEDLE = "          OUTPUT_BUCKET: !Ref OutputBucket"


def patch(path: Path) -> int:
    text = path.read_text()
    count = text.count(NEEDLE)
    if count == 0:
        return 0
    # Only replace if not already expanded
    if "OUTPUT_DESTINATION: !Ref OutputDestination" in text:
        print(f"ALREADY EXPANDED: {path} (skipping)")
        return 0
    text = text.replace(NEEDLE, EXPAND_BLOCK)
    path.write_text(text)
    return count


def main() -> int:
    total = 0
    for arg in sys.argv[1:]:
        p = Path(arg)
        if not p.exists():
            print(f"MISSING: {p}", file=sys.stderr)
            continue
        n = patch(p)
        print(f"Patched {n} env blocks in {p}")
        total += n
    return 0 if total else 1


if __name__ == "__main__":
    sys.exit(main())
