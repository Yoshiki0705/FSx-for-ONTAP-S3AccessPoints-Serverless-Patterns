#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY_BUCKET="${DEPLOY_BUCKET:-fsxn-eda-deploy-178625946981}"
REGION="${AWS_REGION:-ap-northeast-1}"
UC="${UC:-defense-satellite}"

cd "${PROJECT_DIR}"

FUNCS=("$@")
if [[ ${#FUNCS[@]} -eq 0 ]]; then
  # Default function list by UC
  case "${UC}" in
    defense-satellite)
      FUNCS=(discovery tiling object_detection change_detection geo_enrichment alert_generation)
      ;;
    government-archives)
      FUNCS=(discovery ocr classification entity_extraction redaction index_generation compliance_check foia_deadline_reminder)
      ;;
    smart-city-geospatial)
      FUNCS=(discovery preprocessing land_use_classification change_detection infra_assessment risk_mapping report_generation)
      ;;
    *)
      echo "Unknown UC: ${UC}" >&2
      exit 1
      ;;
  esac
fi

echo "=== Packaging ${UC} Lambda functions ==="
for func in "${FUNCS[@]}"; do
  echo "Packaging ${func}..."
  TMPDIR=$(mktemp -d)
  cp "${UC}/functions/${func}/handler.py" "${TMPDIR}/"
  cp -r shared "${TMPDIR}/shared"
  (cd "${TMPDIR}" && zip -r "/tmp/${UC}-${func}.zip" . -x "*.pyc" "__pycache__/*" "shared/tests/*" "shared/cfn/*" "shared/streaming/tests/*") > /dev/null
  aws s3 cp "/tmp/${UC}-${func}.zip" "s3://${DEPLOY_BUCKET}/lambda/${UC}-${func}.zip" --region "${REGION}"
  rm -rf "${TMPDIR}"
  echo "  Done: ${UC}-${func}.zip"
done

echo ""
echo "All ${UC} packages uploaded to s3://${DEPLOY_BUCKET}/lambda/"
