#!/bin/bash
# Verify `sam build` succeeds for the converted patterns. Cleans up .aws-sam after.
set -u
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_DIR}"
PATTERNS=(
  industry/legal-compliance industry/adtech-creative-management industry/agri-food-traceability
  industry/autonomous-driving industry/construction-bim industry/energy-seismic
  industry/financial-idp industry/genomics-pipeline industry/healthcare-dicom
  industry/manufacturing-analytics industry/media-vfx industry/retail-catalog
  industry/semiconductor-eda industry/telecom-network-analytics industry/transportation-maintenance
  industry/travel-document-processing industry/chemical-sds-management
  industry/hr-document-screening industry/real-estate-portfolio
  industry/education-research industry/insurance-claims
)
pass=0; fail=0
for uc in "${PATTERNS[@]}"; do
  out=$(cd "solutions/$uc" && sam build 2>&1; rm -rf .aws-sam)
  if echo "$out" | grep -q "Build Succeeded"; then
    echo "BUILD OK   $uc"; pass=$((pass+1))
  else
    echo "BUILD FAIL $uc :: $(echo "$out" | grep -iE 'error' | head -1 | cut -c1-90)"; fail=$((fail+1))
  fi
done
echo "=== $pass built, $fail failed ==="
