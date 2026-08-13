#!/bin/bash
# Pre-build: stage shared/ into each function directory so `sam build` packages it.
# The logic lives in scripts/build_ops_pattern.sh so all OPS patterns share it.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec bash "$SCRIPT_DIR/../../scripts/build_ops_pattern.sh" "$SCRIPT_DIR"
