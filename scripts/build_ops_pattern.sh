#!/bin/bash
# Stage shared/ (and the DemoMode fixtures) into every function directory of an
# operations pattern, so `sam build` includes them in the deployment package.
#
# Why this exists: the OPS handlers import shared/ lazily inside functions
# (`from shared.ontap_client import ...` inside a def), so nothing fails at
# import time and the unit tests pass — they run from the repo root where
# shared/ is already importable. The gap only appears in Lambda, as an
# ImportError on the first call. Five of the six patterns shipped without any
# staging step at all; see scripts/check_ops_shared_staged.sh for the gate.
#
# Usage:
#   bash scripts/build_ops_pattern.sh operations/storage-efficiency
#   # or, from inside a pattern, via its own ./build.sh wrapper
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PATTERN_DIR="${1:?pattern directory required (e.g. operations/storage-efficiency)}"

# Accept either an absolute path or one relative to the repo root.
case "$PATTERN_DIR" in
    /*) ABS_PATTERN="$PATTERN_DIR" ;;
    *)  ABS_PATTERN="$PROJECT_ROOT/$PATTERN_DIR" ;;
esac

if [[ ! -d "$ABS_PATTERN/functions" ]]; then
    echo "no functions/ directory under $ABS_PATTERN" >&2
    exit 1
fi

SHARED_DIR="$PROJECT_ROOT/shared"
TEST_DATA_DIR="$PROJECT_ROOT/test-data"

for func_dir in "$ABS_PATTERN/functions"/*/; do
    [[ -f "$func_dir/handler.py" ]] || continue
    echo "Copying shared/ → $func_dir"
    rm -rf "$func_dir/shared" "$func_dir/test-data"
    cp -r "$SHARED_DIR" "$func_dir/shared"
    # Prune non-runtime trees so the package stays small.
    rm -rf "$func_dir/shared/tests" \
           "$func_dir/shared/fpolicy-server" \
           "$func_dir/shared/cfn" \
           "$func_dir/shared/lambdas"
    find "$func_dir/shared" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

    # DemoMode reads its fixtures from test-data/ops.
    if [[ -d "$TEST_DATA_DIR/ops" ]]; then
        mkdir -p "$func_dir/test-data"
        cp -r "$TEST_DATA_DIR/ops" "$func_dir/test-data/ops"
    fi
done

echo "Done. Run: sam build && sam deploy"
