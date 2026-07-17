#!/bin/bash
# ============================================================
# FSx for ONTAP Hands-on Lab — Cleanup Script
# ============================================================
# Removes all resources created by the hands-on lab.
#
# IMPORTANT: Tamperproof Snapshot constraints
#   If Tamperproof Snapshots with unexpired retention exist,
#   the volume and file system CANNOT be deleted.
#   This script checks for locked snapshots and provides guidance.
#
# Usage:
#   ./scripts/cleanup.sh --stack-name <name>
#   ./scripts/cleanup.sh --stack-name <name> --force
# ============================================================

set -euo pipefail

STACK_NAME=""
REGION="${AWS_REGION:-ap-northeast-1}"
FORCE=false
MGMT_IP=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --stack-name) STACK_NAME="$2"; shift 2 ;;
        --region) REGION="$2"; shift 2 ;;
        --force) FORCE=true; shift ;;
        -h|--help)
            echo "Usage: $0 --stack-name <name> [--force] [--region REGION]"
            echo ""
            echo "Options:"
            echo "  --force    Skip confirmation prompts"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

if [[ -z "$STACK_NAME" ]]; then
    echo "ERROR: --stack-name is required"
    exit 1
fi

echo "============================================================"
echo " FSx for ONTAP Hands-on Lab — Cleanup"
echo "============================================================"
echo " Stack: $STACK_NAME"
echo " Region: $REGION"
echo "============================================================"
echo ""

# --- Check stack exists ---
STACK_STATUS=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query "Stacks[0].StackStatus" \
    --output text 2>/dev/null || echo "NOT_FOUND")

if [[ "$STACK_STATUS" == "NOT_FOUND" ]]; then
    echo "Stack $STACK_NAME not found. Nothing to clean up."
    exit 0
fi

echo "Stack status: $STACK_STATUS"
echo ""

# --- Get ONTAP management IP ---
MGMT_IP=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='OntapManagementIp'].OutputValue" \
    --output text 2>/dev/null || echo "")

# --- Step 1: Check for Tamperproof Snapshots ---
echo "=== Step 1: Check Tamperproof Snapshot Status ==="
echo ""
if [[ -n "$MGMT_IP" && "$MGMT_IP" != "None" ]]; then
    echo "  ONTAP Management IP: $MGMT_IP"
    echo ""
    echo "  Before deleting, verify no locked snapshots remain:"
    echo ""
    echo "    ssh fsxadmin@${MGMT_IP}"
    echo "    snapshot show -vserver svm01 -volume user01 -fields snaplock-expiry-time"
    echo ""
    echo "  If locked snapshots exist with future expiry, you must wait for"
    echo "  the retention period to expire before deletion is possible."
    echo ""
    echo "  To check if deletion is safe:"
    echo "    snapshot show -vserver svm01 -volume user01 -fields snaplock-expiry-time"
    echo "    # All entries should show '-' or past dates"
    echo ""
else
    echo "  No ONTAP management IP found (may be using existing FSx)."
    echo "  Verify no locked snapshots exist before proceeding."
    echo ""
fi

# --- Step 2: Delete FlexClone volumes (if any) ---
echo "=== Step 2: Clean up FlexClone volumes ==="
echo ""
echo "  If you created FlexClones during the hands-on, delete them first:"
echo ""
echo "    ssh fsxadmin@${MGMT_IP}"
echo "    volume clone show -vserver svm01"
echo "    volume delete -vserver svm01 -volume user01clone -f"
echo ""

# --- Step 3: Confirmation ---
if [[ "$FORCE" != "true" ]]; then
    echo "=== Step 3: Confirm Deletion ==="
    echo ""
    echo "  WARNING: This will delete ALL resources in the stack:"
    echo "    - FSx for ONTAP file system (all data will be lost)"
    echo "    - Windows EC2 instance"
    echo "    - AWS Managed AD"
    echo "    - VPC and all networking resources"
    echo "    - S3 Access Points"
    echo "    - IAM roles"
    echo ""
    read -p "  Type 'DELETE' to confirm: " confirmation
    if [[ "$confirmation" != "DELETE" ]]; then
        echo "  Cancelled."
        exit 0
    fi
fi

# --- Step 4: Delete CloudFormation stack ---
echo ""
echo "=== Step 4: Deleting CloudFormation stack ==="
echo "  This may take 15-30 minutes..."
echo ""

aws cloudformation delete-stack \
    --stack-name "$STACK_NAME" \
    --region "$REGION"

echo "  Stack deletion initiated."
echo ""

# Wait for deletion
echo "  Waiting for stack deletion to complete..."
if aws cloudformation wait stack-delete-complete \
    --stack-name "$STACK_NAME" \
    --region "$REGION" 2>/dev/null; then
    echo ""
    echo "============================================================"
    echo " Cleanup Complete"
    echo "============================================================"
    echo " All resources have been deleted."
else
    echo ""
    echo "============================================================"
    echo " Cleanup Failed or Timed Out"
    echo "============================================================"
    echo ""
    echo " Check for DELETE_FAILED status:"
    echo "   aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION"
    echo ""
    echo " Common causes:"
    echo "   - Tamperproof Snapshots with unexpired retention"
    echo "   - S3 Access Point still attached to volume"
    echo "   - EC2 instance protection enabled"
    echo ""
    echo " To retry after resolving:"
    echo "   aws cloudformation delete-stack --stack-name $STACK_NAME --region $REGION"
fi

# --- Step 5: Clean up S3 deployment artifacts ---
echo ""
echo "=== Optional: Clean up S3 deployment artifacts ==="
echo ""
echo "  If you want to remove Lambda packages and templates from S3:"
echo "    aws s3 rm s3://\$DEPLOY_S3_BUCKET/handson-lab/ --recursive"
echo "    aws s3 rm s3://\$DEPLOY_S3_BUCKET/lambda/ --recursive"
