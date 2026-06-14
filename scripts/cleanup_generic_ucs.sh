#!/bin/bash
# Cleanup generic UC demo stacks — thin wrapper around Python implementation.
#
# DEPRECATED: This script now delegates to cleanup_generic_ucs.py.
# Please use the Python version directly for new workflows:
#   python3 scripts/cleanup_generic_ucs.py [--dry-run] [--wait] [--all] UC1 UC2 ...
#
# This wrapper preserves backward compatibility with existing CI/CD pipelines
# and scripts that call cleanup_generic_ucs.sh directly.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "⚠️  DEPRECATION NOTICE: cleanup_generic_ucs.sh is deprecated."
echo "   Use: python3 scripts/cleanup_generic_ucs.py $*"
echo ""

# Pass all arguments through to the Python version
exec python3 "${SCRIPT_DIR}/cleanup_generic_ucs.py" "$@"
