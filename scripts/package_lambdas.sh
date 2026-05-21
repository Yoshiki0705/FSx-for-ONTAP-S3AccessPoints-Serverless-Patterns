#!/bin/bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || dirname "$(dirname "$(realpath "$0")")")}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-$(aws sts get-caller-identity --query Account --output text)}"
DEPLOY_BUCKET="fsxn-eda-deploy-${AWS_ACCOUNT_ID}"
REGION="${AWS_REGION:-ap-northeast-1}"

cd "${PROJECT_DIR}"

for func in discovery metadata_extraction drc_aggregation report_generation; do
  echo "Packaging ${func}..."
  TMPDIR=$(mktemp -d)
  cp "semiconductor-eda/functions/${func}/handler.py" "${TMPDIR}/"
  cp -r shared "${TMPDIR}/shared"
  (cd "${TMPDIR}" && zip -r "/tmp/semiconductor-eda-${func}.zip" . -x "*.pyc" "__pycache__/*" "shared/tests/*" "shared/cfn/*") > /dev/null
  aws s3 cp "/tmp/semiconductor-eda-${func}.zip" "s3://${DEPLOY_BUCKET}/lambda/semiconductor-eda-${func}.zip" --region "${REGION}"
  rm -rf "${TMPDIR}"
  echo "  Done: semiconductor-eda-${func}.zip"
done

echo ""
echo "All packages uploaded to s3://${DEPLOY_BUCKET}/lambda/"
