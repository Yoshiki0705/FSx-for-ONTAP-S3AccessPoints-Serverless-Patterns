#!/usr/bin/env python3
"""Update Lambda environment variables in UC1-5 templates to use the new
OutputDestination fallback chain.

Transforms:
    S3_ACCESS_POINT_OUTPUT: !Ref S3AccessPointOutputAlias

Into:
    S3_ACCESS_POINT_OUTPUT:
      !If
        - HasOutputS3APAlias
        - !Ref OutputS3APAlias
        - !If
          - HasLegacyOutputAlias
          - !Ref S3AccessPointOutputAlias
          - !Ref S3AccessPointAlias
    OUTPUT_DESTINATION: !Ref OutputDestination
    OUTPUT_S3AP_ALIAS:
      !If
        - UseFsxnS3AP
        - !If
          - HasOutputS3APAlias
          - !Ref OutputS3APAlias
          - !If
            - HasLegacyOutputAlias
            - !Ref S3AccessPointOutputAlias
            - !Ref S3AccessPointAlias
        - ""
    OUTPUT_S3AP_PREFIX: !Ref OutputS3APPrefix

This keeps backward compat (handlers still read S3_ACCESS_POINT_OUTPUT and
get a valid alias) while also populating the unified env vars for future
handler migration.

Usage: python3 scripts/_update_env_vars_uc1_5.py
"""

from __future__ import annotations

import sys
from pathlib import Path


UC_DIRS = [
    "legal-compliance",
    "financial-idp",
    "manufacturing-analytics",
    "media-vfx",
    "healthcare-dicom",
]


OLD_ENV_LINE = "          S3_ACCESS_POINT_OUTPUT: !Ref S3AccessPointOutputAlias"

NEW_ENV_BLOCK = """          S3_ACCESS_POINT_OUTPUT:
            !If
              - HasOutputS3APAlias
              - !Ref OutputS3APAlias
              - !If
                - HasLegacyOutputAlias
                - !Ref S3AccessPointOutputAlias
                - !Ref S3AccessPointAlias
          OUTPUT_DESTINATION: !Ref OutputDestination
          OUTPUT_S3AP_ALIAS:
            !If
              - UseFsxnS3AP
              - !If
                - HasOutputS3APAlias
                - !Ref OutputS3APAlias
                - !If
                  - HasLegacyOutputAlias
                  - !Ref S3AccessPointOutputAlias
                  - !Ref S3AccessPointAlias
              - ""
          OUTPUT_S3AP_PREFIX: !Ref OutputS3APPrefix"""


def patch_template(path: Path) -> int:
    text = path.read_text()
    count = text.count(OLD_ENV_LINE)

    if count == 0:
        print(f"NO MATCHES in {path}")
        return 0

    if "OUTPUT_DESTINATION: !Ref OutputDestination" in text:
        print(f"ALREADY PATCHED: {path}")
        return 0

    text = text.replace(OLD_ENV_LINE, NEW_ENV_BLOCK)
    path.write_text(text)
    print(f"PATCHED {count} env blocks in {path}")
    return count


def main() -> int:
    total = 0
    for uc_dir in UC_DIRS:
        path = Path(f"{uc_dir}/template-deploy.yaml")
        if not path.exists():
            print(f"MISSING: {path}")
            continue
        total += patch_template(path)
    print(f"\nTotal env blocks updated: {total}")
    return 0 if total else 1


if __name__ == "__main__":
    sys.exit(main())
