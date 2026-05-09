#!/bin/bash
set -euo pipefail

# =============================================================================
# build-geo-layer.sh — Build Lambda Layer with geospatial libraries
#
# Creates a Lambda Layer zip file containing:
# - rasterio (GeoTIFF reading + COG conversion)
# - pyproj (CRS transformation)
# - laspy (LAS/LAZ point cloud reading)
# - shapely (geometric operations)
#
# Output: build/geo-layer.zip (uploaded to S3 for Lambda Layer creation)
#
# Usage:
#   ./scripts/build-geo-layer.sh [--python-version 3.13] [--output build/]
# =============================================================================

PYTHON_VERSION="${PYTHON_VERSION:-3.13}"
OUTPUT_DIR="${OUTPUT_DIR:-build}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUTPUT_DIR="${PROJECT_ROOT}/${OUTPUT_DIR}"
LAYER_DIR="${OUTPUT_DIR}/geo-layer/python"

while [[ $# -gt 0 ]]; do
    case $1 in
        --python-version)
            PYTHON_VERSION="$2"
            shift 2
            ;;
        --output)
            OUTPUT_DIR="${PROJECT_ROOT}/$2"
            LAYER_DIR="${OUTPUT_DIR}/geo-layer/python"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo "=== Building geospatial Lambda Layer ==="
echo "Python version: ${PYTHON_VERSION}"
echo "Output directory: ${OUTPUT_DIR}"

# Clean previous build
rm -rf "${LAYER_DIR}"
mkdir -p "${LAYER_DIR}"

# Use Docker to ensure binary compatibility with Lambda runtime (Amazon Linux 2023)
if command -v docker >/dev/null 2>&1; then
    echo "Building using Docker (Amazon Linux 2023 compatibility)"
    docker run --rm \
        -v "${LAYER_DIR}:/opt/python" \
        --entrypoint /bin/bash \
        "public.ecr.aws/lambda/python:${PYTHON_VERSION}" \
        -c "pip install --target /opt/python \
            rasterio==1.3.9 \
            pyproj==3.6.1 \
            laspy==2.5.4 \
            shapely==2.0.2 \
            numpy==1.26.4 && \
            find /opt/python -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true && \
            find /opt/python -name '*.pyc' -delete 2>/dev/null || true"
else
    echo "Warning: Docker not found. Building with host pip (binary compatibility not guaranteed)."
    pip install --target "${LAYER_DIR}" \
        rasterio==1.3.9 \
        pyproj==3.6.1 \
        laspy==2.5.4 \
        shapely==2.0.2 \
        numpy==1.26.4
    find "${LAYER_DIR}" -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
fi

# Create zip file
cd "${OUTPUT_DIR}/geo-layer"
LAYER_ZIP="${OUTPUT_DIR}/geo-layer.zip"
rm -f "${LAYER_ZIP}"
zip -rq "${LAYER_ZIP}" python/

LAYER_SIZE=$(du -h "${LAYER_ZIP}" | cut -f1)
echo ""
echo "=== Build complete ==="
echo "Layer zip: ${LAYER_ZIP}"
echo "Size: ${LAYER_SIZE}"
echo ""
echo "Next steps:"
echo "  1. Upload to S3:"
echo "     aws s3 cp ${LAYER_ZIP} s3://\${DEPLOY_BUCKET}/layers/geo-layer.zip"
echo "  2. Reference in CloudFormation:"
echo "     Layers: [!Ref GeoLayer]"
