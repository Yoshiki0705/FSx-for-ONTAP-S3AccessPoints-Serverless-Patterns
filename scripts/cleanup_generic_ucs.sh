#!/bin/bash
# Cleanup generic UC demo stacks
set +e

uc_to_dir() {
    case "$1" in
        UC1) echo "legal-compliance" ;;
        UC2) echo "financial-idp" ;;
        UC3) echo "manufacturing-analytics" ;;
        UC4) echo "media-vfx" ;;
        UC5) echo "healthcare-dicom" ;;
        UC7) echo "genomics-pipeline" ;;
        UC8) echo "energy-seismic" ;;
        UC9) echo "autonomous-driving" ;;
        UC10) echo "construction-bim" ;;
        UC11) echo "retail-catalog" ;;
        UC12) echo "logistics-ocr" ;;
        UC13) echo "education-research" ;;
        UC14) echo "insurance-claims" ;;
        *) echo "$1" ;;
    esac
}

for input in "$@"; do
    UC=$(uc_to_dir "$input")
    STACK="fsxn-${UC}-demo"

    # Empty output bucket
    OUT_BUCKET="${STACK}-output-178625946981"
    echo "=== Emptying $OUT_BUCKET ==="
    aws s3api delete-objects --bucket "$OUT_BUCKET" --region ap-northeast-1 \
        --delete "$(aws s3api list-object-versions --bucket "$OUT_BUCKET" --region ap-northeast-1 --output=json --query='{Objects: Versions[].{Key:Key,VersionId:VersionId}}' 2>/dev/null)" 2>&1 | tail -2
    aws s3api delete-objects --bucket "$OUT_BUCKET" --region ap-northeast-1 \
        --delete "$(aws s3api list-object-versions --bucket "$OUT_BUCKET" --region ap-northeast-1 --output=json --query='{Objects: DeleteMarkers[].{Key:Key,VersionId:VersionId}}' 2>/dev/null)" 2>&1 | tail -2
    aws s3 rb "s3://${OUT_BUCKET}" --region ap-northeast-1 2>&1 | tail -1

    # Delete stack
    echo "=== Deleting $STACK ==="
    aws cloudformation delete-stack --stack-name "$STACK" --region ap-northeast-1
    echo "  Initiated"
done

# Also delete UC1 that rolled back
aws cloudformation delete-stack --stack-name fsxn-legal-compliance-demo --region ap-northeast-1 2>&1 | tail -1
