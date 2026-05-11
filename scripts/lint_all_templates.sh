#!/bin/bash
# lint_all_templates.sh — Run cfn-lint in parallel across all 17 UC templates.
#
# Why parallel: cfn-lint takes ~60-120s per template (remote schema fetches).
# Serial execution for 17 UCs would exceed 30 minutes. 4-way parallelism
# brings it down to ~5-7 minutes.
#
# Benign errors filtered (see scripts/lint_all_templates.py for details):
#   E2530 — Lambda ZipFile size (deploy-time concern)
#   E3030 — AllowedValues regional subset mismatches
#   E3006 — Resource type missing in certain regions (e.g., Glue in ap-southeast-6)
#
# Usage:
#   scripts/lint_all_templates.sh                    # all 17 UCs
#   scripts/lint_all_templates.sh uc-slug1 uc-slug2  # subset (pass UC dir names)

set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 scripts/lint_all_templates.py "$@"
