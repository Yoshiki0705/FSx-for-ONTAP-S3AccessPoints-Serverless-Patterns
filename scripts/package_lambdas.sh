#!/bin/bash
set -euo pipefail

PROJECT_DIR="/Users/yoshiki/Downloads/fsxn-s3ap-serverless-patterns"
DEPLOY_BUCKET="fsxn-eda-deploy-178625946981"
REGION="ap-northeast-1"

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
