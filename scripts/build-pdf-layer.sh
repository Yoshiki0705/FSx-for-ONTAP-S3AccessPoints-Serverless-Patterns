#!/bin/bash
set -euo pipefail

# =============================================================================
# build-pdf-layer.sh — Build Lambda Layer for PDF processing
#
# Creates a Lambda Layer zip containing:
# - pypdf (PDF read/write/redaction)
# - reportlab (PDF generation)
#
# Output: build/pdf-layer.zip
# =============================================================================

PYTHON_VERSION="${PYTHON_VERSION:-3.13}"
OUTPUT_DIR="${OUTPUT_DIR:-build}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUTPUT_DIR="${PROJECT_ROOT}/${OUTPUT_DIR}"
LAYER_DIR="${OUTPUT_DIR}/pdf-layer/python"

while [[ $# -gt 0 ]]; do
    case $1 in
        --python-version)
            PYTHON_VERSION="$2"
            shift 2
            ;;
        --output)
            OUTPUT_DIR="${PROJECT_ROOT}/$2"
            LAYER_DIR="${OUTPUT_DIR}/pdf-layer/python"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo "=== Building PDF Lambda Layer ==="
echo "Python version: ${PYTHON_VERSION}"

rm -rf "${LAYER_DIR}"
mkdir -p "${LAYER_DIR}"

if command -v docker >/dev/null 2>&1; then
    echo "Building using Docker (Amazon Linux 2023 compatibility)"
    docker run --rm \
        -v "${LAYER_DIR}:/opt/python" \
        --entrypoint /bin/bash \
        "public.ecr.aws/lambda/python:${PYTHON_VERSION}" \
        -c "pip install --target /opt/python \
            pypdf==4.2.0 \
            reportlab==4.0.9 && \
            find /opt/python -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true"
else
    pip install --target "${LAYER_DIR}" pypdf==4.2.0 reportlab==4.0.9
    find "${LAYER_DIR}" -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
fi

cd "${OUTPUT_DIR}/pdf-layer"
LAYER_ZIP="${OUTPUT_DIR}/pdf-layer.zip"
rm -f "${LAYER_ZIP}"
zip -rq "${LAYER_ZIP}" python/

LAYER_SIZE=$(du -h "${LAYER_ZIP}" | cut -f1)
echo ""
echo "=== Build complete ==="
echo "Layer zip: ${LAYER_ZIP} (${LAYER_SIZE})"
