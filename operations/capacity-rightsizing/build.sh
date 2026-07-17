#!/bin/bash
# Pre-build script: Copy shared/ modules into each function directory
# so SAM build includes them in the Lambda deployment package.
# Run this before `sam build`.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SHARED_DIR="$PROJECT_ROOT/shared"
TEST_DATA_DIR="$PROJECT_ROOT/test-data"

for func_dir in "$SCRIPT_DIR/functions"/*/; do
    echo "Copying shared/ → $func_dir"
    rm -rf "$func_dir/shared" "$func_dir/test-data"
    cp -r "$SHARED_DIR" "$func_dir/shared"
    # Remove non-runtime files
    rm -rf "$func_dir/shared/tests" "$func_dir/shared/fpolicy-server" "$func_dir/shared/cfn" "$func_dir/shared/lambdas"
    find "$func_dir/shared" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

    # Copy test-data for DemoMode
    mkdir -p "$func_dir/test-data"
    cp -r "$TEST_DATA_DIR/ops" "$func_dir/test-data/ops"
done

echo "Done. Run: sam build && sam deploy"
