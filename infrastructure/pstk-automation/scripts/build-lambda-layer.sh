#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
# Build Lambda Layer for NetApp.ONTAP PowerShell Module
#
# This script builds a Lambda-compatible zip containing:
#   - NetApp.ONTAP module
#   - AWS.Tools.SecretsManager module
#   - PowerShell custom runtime bootstrap
#
# Usage:
#   ./build-lambda-layer.sh [output-dir]
#
# Prerequisites:
#   - pwsh (PowerShell 7.x) installed locally
#   - Docker (optional, for Amazon Linux 2023 compatibility testing)
# ═══════════════════════════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="${1:-${SCRIPT_DIR}/../layers}"
LAYER_DIR="${OUTPUT_DIR}/build"
ZIP_FILE="${OUTPUT_DIR}/netapp-ontap-pstk.zip"

echo "============================================"
echo " Building NetApp.ONTAP Lambda Layer"
echo "============================================"
echo ""

# Clean previous build
rm -rf "${LAYER_DIR}" "${ZIP_FILE}"
mkdir -p "${LAYER_DIR}/modules"

echo "[1/4] Downloading NetApp.ONTAP module..."
pwsh -NoProfile -Command "
    Save-Module -Name 'NetApp.ONTAP' -Path '${LAYER_DIR}/modules' -Force
"

echo "[2/4] Downloading AWS.Tools.SecretsManager..."
pwsh -NoProfile -Command "
    Save-Module -Name 'AWS.Tools.SecretsManager' -Path '${LAYER_DIR}/modules' -Force
    Save-Module -Name 'AWS.Tools.Common' -Path '${LAYER_DIR}/modules' -Force
"

echo "[3/4] Creating PSModulePath configuration..."
cat > "${LAYER_DIR}/modules-path.ps1" << 'EOF'
# Lambda Layer module path setup
$env:PSModulePath = "/opt/modules:" + $env:PSModulePath
EOF

echo "[4/4] Creating zip archive..."
cd "${LAYER_DIR}"
zip -r "${ZIP_FILE}" . -x "*.DS_Store"
cd "${SCRIPT_DIR}"

# Report
LAYER_SIZE=$(du -sh "${ZIP_FILE}" | cut -f1)
echo ""
echo "============================================"
echo " Layer build complete"
echo "============================================"
echo "  Output: ${ZIP_FILE}"
echo "  Size:   ${LAYER_SIZE}"
echo ""
echo "Upload to S3:"
echo "  aws s3 cp ${ZIP_FILE} s3://<your-bucket>/layers/netapp-ontap-pstk.zip"
echo ""
echo "Or publish directly:"
echo "  aws lambda publish-layer-version \\"
echo "    --layer-name netapp-ontap-pstk \\"
echo "    --zip-file fileb://${ZIP_FILE} \\"
echo "    --compatible-runtimes dotnet8 \\"
echo "    --compatible-architectures x86_64"
echo ""

# Cleanup build dir
rm -rf "${LAYER_DIR}"
