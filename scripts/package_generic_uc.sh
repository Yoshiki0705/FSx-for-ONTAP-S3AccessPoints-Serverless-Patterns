#!/bin/bash
# ⚠️ 2026-08-12: このスクリプトは現状動かない。使う前に読むこと。
#
#   `sam build` が CodeUri から直接パッケージするので、このスクリプトは不要。
#
#   動かない理由:
#   1. 下の使用例 `UC=legal-compliance` は `legal-compliance/functions/` を見るが、
#      ディレクトリ再編でパスは `solutions/industry/legal-compliance/` になっている。
#   2. 実際のパスを渡すと S3 キーが `lambda/solutions/industry/<uc>-<fn>.zip` になり、
#      template-deploy.yaml が期待する `lambda/<uc>-<fn>.zip` と一致しない。
#   3. 関数ディレクトリはアンダースコア（sds_extractor）だが、template-deploy.yaml の
#      キーはハイフン（sds-extractor）。7 パターンで食い違う。
#   4. travel-document-processing だけ `${AWS::StackName}/<fn>.zip` という別方式で、
#      agri-food-traceability には template-deploy.yaml が存在しない。
#
# Generic UC Lambda packaging (for UC1-UC14).
# Auto-detects functions from <uc>/functions/*/handler.py
#
# Usage: UC=legal-compliance bash scripts/package_generic_uc.sh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY_BUCKET="${DEPLOY_BUCKET:-fsxn-eda-deploy-${AWS_ACCOUNT_ID}}"
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
