#!/bin/bash
set -euo pipefail

# =============================================================================
# Phase 3 クリーンアップスクリプト
# =============================================================================

REGION="${AWS_DEFAULT_REGION:-ap-northeast-1}"

echo "=== Phase 3 Cleanup ==="
echo "Region: $REGION"
echo ""
echo "WARNING: This will delete all Phase 3 CloudFormation stacks."
read -p "Continue? (y/N): " confirm
if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
    echo "Aborted."
    exit 0
fi

STACKS=(
    "fsxn-alert-automation"
    "fsxn-observability-dashboard"
    "fsxn-autonomous-driving-phase3"
    "fsxn-retail-catalog-phase3"
)

for stack in "${STACKS[@]}"; do
    echo "Deleting $stack..."
    aws cloudformation delete-stack --stack-name "$stack" --region "$REGION" 2>/dev/null || true
done

echo "Waiting for stacks to be deleted..."
for stack in "${STACKS[@]}"; do
    aws cloudformation wait stack-delete-complete --stack-name "$stack" --region "$REGION" 2>/dev/null || true
    echo "  $stack: deleted"
done

echo ""
echo "=== Phase 3 Cleanup Complete ==="
