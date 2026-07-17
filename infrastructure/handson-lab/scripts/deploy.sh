#!/bin/bash
# ============================================================
# FSx for ONTAP Hands-on Lab — Deployment Script
# ============================================================
# Usage:
#   ./scripts/deploy.sh [--existing-fsx] [--existing-vpc]
#
# Prerequisites:
#   - AWS CLI v2 configured with appropriate credentials
#   - Secrets Manager secrets created (see README.md)
#   - S3 bucket for template/Lambda storage
#
# Estimated deployment time:
#   - Full (new resources): ~45-60 minutes
#   - Existing FSx mode:   ~15-20 minutes
# ============================================================

set -euo pipefail

# --- Configuration ---
STACK_NAME="${STACK_NAME:-fsx-ontap-handson}"
REGION="${AWS_REGION:-ap-northeast-1}"
S3_BUCKET="${DEPLOY_S3_BUCKET:-}"
PARAMS_FILE="${PARAMS_FILE:-cloudformation/parameters/dev.json}"

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# --- Parse arguments ---
USE_EXISTING_FSX="false"
USE_EXISTING_VPC="false"

while [[ $# -gt 0 ]]; do
    case $1 in
        --existing-fsx) USE_EXISTING_FSX="true"; shift ;;
        --existing-vpc) USE_EXISTING_VPC="true"; shift ;;
        --stack-name) STACK_NAME="$2"; shift 2 ;;
        --region) REGION="$2"; shift 2 ;;
        --bucket) S3_BUCKET="$2"; shift 2 ;;
        --params) PARAMS_FILE="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: $0 [--existing-fsx] [--existing-vpc] [--stack-name NAME] [--region REGION] [--bucket BUCKET] [--params FILE]"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# --- Validation ---
if [[ -z "$S3_BUCKET" ]]; then
    echo "ERROR: DEPLOY_S3_BUCKET or --bucket is required."
    echo "Create a bucket: aws s3 mb s3://my-handson-deploy-bucket --region $REGION"
    exit 1
fi

echo "============================================================"
echo " FSx for ONTAP Hands-on Lab Deployment"
echo "============================================================"
echo " Stack Name:    $STACK_NAME"
echo " Region:        $REGION"
echo " S3 Bucket:     $S3_BUCKET"
echo " Existing FSx:  $USE_EXISTING_FSX"
echo " Existing VPC:  $USE_EXISTING_VPC"
echo " Params File:   $PARAMS_FILE"
echo "============================================================"
echo ""

# --- Step 1: Package Lambda functions ---
echo "=== Step 1: Packaging Lambda functions ==="
cd "$PROJECT_DIR"

LAMBDA_DIR="lambda"
for func_dir in "$LAMBDA_DIR"/custom_resource_*/; do
    func_name=$(basename "$func_dir")
    zip_file="/tmp/${func_name}.zip"
    echo "  Packaging $func_name..."
    (cd "$func_dir" && zip -r "$zip_file" . -x "*.pyc" -x "__pycache__/*" -x "*.egg-info/*")
    aws s3 cp "$zip_file" "s3://${S3_BUCKET}/lambda/${func_name}.zip" --region "$REGION"
    echo "  Uploaded: s3://${S3_BUCKET}/lambda/${func_name}.zip"
done
echo ""

# --- Step 2: Upload CloudFormation templates to S3 ---
echo "=== Step 2: Uploading CloudFormation templates to S3 ==="
TEMPLATE_PREFIX="handson-lab/cloudformation"

for template in cloudformation/*.yaml; do
    template_name=$(basename "$template")
    aws s3 cp "$template" "s3://${S3_BUCKET}/${TEMPLATE_PREFIX}/${template_name}" --region "$REGION"
    echo "  Uploaded: $template_name"
done
echo ""

TEMPLATE_BASE_URL="https://${S3_BUCKET}.s3.${REGION}.amazonaws.com/${TEMPLATE_PREFIX}"

# --- Step 3: Deploy CloudFormation stack ---
echo "=== Step 3: Deploying CloudFormation stack ==="
echo "  This may take 45-60 minutes for a full deployment..."
echo ""

# Build parameter overrides from JSON file
PARAM_OVERRIDES=""
if [[ -f "$PARAMS_FILE" ]]; then
    # Read JSON parameters and convert to CloudFormation override format
    PARAM_OVERRIDES=$(python3 -c "
import json, sys
with open('$PARAMS_FILE') as f:
    params = json.load(f)
overrides = []
for p in params:
    overrides.append(f\"{p['ParameterKey']}={p['ParameterValue']}\")
print(' '.join(overrides))
")
fi

# Add template URL and S3 bucket
PARAM_OVERRIDES="TemplateBaseUrl=${TEMPLATE_BASE_URL} LambdaCodeS3Bucket=${S3_BUCKET} UseExistingFsx=${USE_EXISTING_FSX} UseExistingVpc=${USE_EXISTING_VPC} ${PARAM_OVERRIDES}"

aws cloudformation deploy \
    --template-file "cloudformation/main.yaml" \
    --stack-name "$STACK_NAME" \
    --parameter-overrides $PARAM_OVERRIDES \
    --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND \
    --region "$REGION" \
    --no-fail-on-empty-changeset

echo ""
echo "=== Step 4: Waiting for stack completion ==="
aws cloudformation wait stack-create-complete \
    --stack-name "$STACK_NAME" \
    --region "$REGION" 2>/dev/null || true

# --- Step 5: Show outputs ---
echo ""
echo "=== Deployment Complete ==="
echo ""
echo "Stack Outputs:"
aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query "Stacks[0].Outputs[*].[OutputKey,OutputValue]" \
    --output table

# --- Step 6: Run health check ---
echo ""
echo "=== Step 6: Running post-deployment health check ==="
if [[ -f "$SCRIPT_DIR/verify_deployment.sh" ]]; then
    "$SCRIPT_DIR/verify_deployment.sh" --stack-name "$STACK_NAME" --region "$REGION" || true
fi

echo ""
echo "============================================================"
echo " Next Steps:"
echo "============================================================"
echo " 1. Wait 2-5 min for EC2 domain join to complete"
echo " 2. Run ONTAP post-config: ./scripts/setup_ontap.sh --stack-name $STACK_NAME"
echo " 3. Access EC2 via Fleet Manager (see output URL above)"
echo " 4. Run map_drives.ps1 on the EC2 desktop"
echo " 5. (Optional) Configure Amazon Q: python3 ./scripts/setup_quick.py"
echo "============================================================"
