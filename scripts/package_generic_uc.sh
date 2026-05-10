#!/bin/bash
# Generic UC Lambda packaging (for UC1-UC14).
# Auto-detects functions from <uc>/functions/*/handler.py
#
# Usage: UC=legal-compliance bash scripts/package_generic_uc.sh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY_BUCKET="${DEPLOY_BUCKET:-fsxn-eda-deploy-<ACCOUNT_ID>}"
REGION="${AWS_REGION:-ap-northeast-1}"
UC="${UC:?UC env var required (e.g. UC=legal-compliance)}"

cd "${PROJECT_DIR}"

# Auto-detect function directories
FUNCS=()
for dir in "${UC}/functions"/*/; do
    fname=$(basename "$dir")
    if [[ -f "${dir}handler.py" ]] && [[ "$fname" != "__pycache__" ]]; then
        FUNCS+=("$fname")
    fi
done

echo "=== Packaging ${UC}: ${FUNCS[*]} ==="
for func in "${FUNCS[@]}"; do
    echo "  Packaging ${func}..."
    TMPDIR=$(mktemp -d)
    cp "${UC}/functions/${func}/handler.py" "${TMPDIR}/"
    cp -r shared "${TMPDIR}/shared"
    (cd "${TMPDIR}" && zip -r "/tmp/${UC}-${func}.zip" . \
        -x "*.pyc" "__pycache__/*" "shared/tests/*" "shared/cfn/*" "shared/streaming/tests/*") > /dev/null
    aws s3 cp "/tmp/${UC}-${func}.zip" "s3://${DEPLOY_BUCKET}/lambda/${UC}-${func}.zip" --region "${REGION}" --quiet
    rm -rf "${TMPDIR}"
done
echo "✅ ${UC} packaged"
