#!/bin/bash
set -euo pipefail

# =============================================================================
# Phase 3 クリーンアップスクリプト (Enhanced)
#
# 孤立リソース（ENI, Security Group）を自動処理し、
# CloudFormation スタック削除の失敗を防止する。
#
# 使い方:
#   ./scripts/cleanup_phase3.sh              # 対話モード
#   ./scripts/cleanup_phase3.sh --force      # 確認プロンプトなし
# =============================================================================

REGION="${AWS_DEFAULT_REGION:-ap-northeast-1}"
ACCOUNT_ID=$(aws sts get-caller-identity --query 'Account' --output text)

# VPC ID はスタック出力またはパラメータから取得（パラメータ化）
VPC_ID="${VPC_ID:-}"

STACKS=(
    "fsxn-alert-automation"
    "fsxn-observability-dashboard"
    "fsxn-autonomous-driving-phase3"
    "fsxn-retail-catalog-phase3"
)

echo "=== Phase 3 Cleanup (Enhanced) ==="
echo "Region: $REGION"
echo "Account: $ACCOUNT_ID"
echo ""

# --- オプション解析 ---
FORCE=false
for arg in "$@"; do
    case "$arg" in
        --force) FORCE=true ;;
    esac
done

# =============================================================================
# ユーティリティ関数
# =============================================================================

confirm_action() {
    local message="$1"
    if [ "$FORCE" = true ]; then
        return 0
    fi
    read -p "$message (y/N): " confirm
    [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]
}

get_vpc_id() {
    # VPC_ID が未設定の場合、スタックパラメータから取得
    if [ -z "$VPC_ID" ]; then
        for stack in "${STACKS[@]}"; do
            VPC_ID=$(aws cloudformation describe-stacks \
                --stack-name "$stack" \
                --query "Stacks[0].Parameters[?ParameterKey=='VpcId'].ParameterValue" \
                --output text \
                --region "$REGION" 2>/dev/null || echo "")
            if [ -n "$VPC_ID" ] && [ "$VPC_ID" != "None" ]; then
                break
            fi
            VPC_ID=""
        done
    fi
    if [ -z "$VPC_ID" ]; then
        echo "  ⚠️  VPC ID not found. Set VPC_ID environment variable for ENI/SG cleanup."
        return 1
    fi
    echo "  VPC ID: $VPC_ID"
    return 0
}

# =============================================================================
# ENI クリーンアップ
# =============================================================================
cleanup_orphaned_enis() {
    echo "  --- Cleaning up orphaned Lambda ENIs ---"

    if ! get_vpc_id; then
        return 1
    fi

    # status=available の ENI を検索（Lambda が作成した ENI）
    local enis
    enis=$(aws ec2 describe-network-interfaces \
        --filters \
            "Name=vpc-id,Values=$VPC_ID" \
            "Name=status,Values=available" \
            "Name=description,Values=*Lambda*" \
        --query 'NetworkInterfaces[].NetworkInterfaceId' \
        --output text \
        --region "$REGION" 2>/dev/null || echo "")

    if [ -z "$enis" ]; then
        enis=$(aws ec2 describe-network-interfaces \
            --filters \
                "Name=vpc-id,Values=$VPC_ID" \
                "Name=status,Values=available" \
                "Name=requester-id,Values=*lambda*" \
            --query 'NetworkInterfaces[].NetworkInterfaceId' \
            --output text \
            --region "$REGION" 2>/dev/null || echo "")
    fi

    if [ -z "$enis" ]; then
        echo "    ℹ️  No orphaned Lambda ENIs found"
        return 0
    fi

    local count=0
    for eni in $enis; do
        echo "    Deleting orphaned ENI: $eni"
        aws ec2 delete-network-interface --network-interface-id "$eni" --region "$REGION" 2>/dev/null || {
            echo "    ⚠️  Failed to delete ENI $eni (may still be detaching)"
        }
        count=$((count + 1))
    done
    echo "    ✅ Processed $count orphaned ENI(s)"
}

# =============================================================================
# Security Group クリーンアップ
# =============================================================================
cleanup_orphaned_security_groups() {
    echo "  --- Cleaning up orphaned Security Groups ---"

    if ! get_vpc_id; then
        return 1
    fi

    # スタック関連の SG を検索（タグベース）
    local stack_filter=""
    for stack in "${STACKS[@]}"; do
        stack_filter="${stack_filter:+$stack_filter,}$stack"
    done

    local sgs
    sgs=$(aws ec2 describe-security-groups \
        --filters \
            "Name=vpc-id,Values=$VPC_ID" \
            "Name=tag:aws:cloudformation:stack-name,Values=$stack_filter" \
        --query 'SecurityGroups[].GroupId' \
        --output text \
        --region "$REGION" 2>/dev/null || echo "")

    if [ -z "$sgs" ]; then
        echo "    ℹ️  No orphaned Security Groups found"
        return 0
    fi

    # Step 1: クロスSG参照を解除
    echo "    Revoking cross-SG references..."
    for sg in $sgs; do
        # このSGを参照している他のSGのingress ruleを検索
        local referencing_sgs
        referencing_sgs=$(aws ec2 describe-security-groups \
            --filters "Name=ip-permission.group-id,Values=$sg" \
            --query 'SecurityGroups[].GroupId' \
            --output text \
            --region "$REGION" 2>/dev/null || echo "")

        for ref_sg in $referencing_sgs; do
            echo "      Revoking reference: $ref_sg → $sg"
            local rules
            rules=$(aws ec2 describe-security-groups \
                --group-ids "$ref_sg" \
                --query "SecurityGroups[0].IpPermissions[?UserIdGroupPairs[?GroupId=='$sg']]" \
                --output json \
                --region "$REGION" 2>/dev/null || echo "[]")

            if [ "$rules" != "[]" ] && [ -n "$rules" ]; then
                echo "$rules" | aws ec2 revoke-security-group-ingress \
                    --group-id "$ref_sg" \
                    --ip-permissions file:///dev/stdin \
                    --region "$REGION" 2>/dev/null || true
            fi

            local egress_rules
            egress_rules=$(aws ec2 describe-security-groups \
                --group-ids "$ref_sg" \
                --query "SecurityGroups[0].IpPermissionsEgress[?UserIdGroupPairs[?GroupId=='$sg']]" \
                --output json \
                --region "$REGION" 2>/dev/null || echo "[]")

            if [ "$egress_rules" != "[]" ] && [ -n "$egress_rules" ]; then
                echo "$egress_rules" | aws ec2 revoke-security-group-egress \
                    --group-id "$ref_sg" \
                    --ip-permissions file:///dev/stdin \
                    --region "$REGION" 2>/dev/null || true
            fi
        done

        # 自己参照ルールも解除
        local self_rules
        self_rules=$(aws ec2 describe-security-groups \
            --group-ids "$sg" \
            --query "SecurityGroups[0].IpPermissions[?UserIdGroupPairs[?GroupId=='$sg']]" \
            --output json \
            --region "$REGION" 2>/dev/null || echo "[]")

        if [ "$self_rules" != "[]" ] && [ -n "$self_rules" ]; then
            echo "      Revoking self-reference: $sg → $sg"
            echo "$self_rules" | aws ec2 revoke-security-group-ingress \
                --group-id "$sg" \
                --ip-permissions file:///dev/stdin \
                --region "$REGION" 2>/dev/null || true
        fi
    done

    # Step 2: SG を削除
    echo "    Deleting Security Groups..."
    for sg in $sgs; do
        echo "      Deleting SG: $sg"
        aws ec2 delete-security-group --group-id "$sg" --region "$REGION" 2>/dev/null || {
            echo "      ⚠️  Failed to delete SG $sg (may have remaining dependencies)"
        }
    done
    echo "    ✅ Security Group cleanup complete"
}

# =============================================================================
# スタック削除リトライ
# =============================================================================
wait_for_stack_deletion_with_retry() {
    local stack="$1"
    local max_retries=3
    local retry=0

    while [ $retry -lt $max_retries ]; do
        echo "  Waiting for $stack deletion (attempt $((retry + 1))/$max_retries)..."

        # スタックが存在するか確認
        if ! aws cloudformation describe-stacks --stack-name "$stack" --region "$REGION" 2>/dev/null; then
            echo "  ✅ $stack: deleted successfully"
            return 0
        fi

        # 削除完了を待機
        if aws cloudformation wait stack-delete-complete \
            --stack-name "$stack" \
            --region "$REGION" 2>/dev/null; then
            echo "  ✅ $stack: deleted successfully"
            return 0
        fi

        # 削除失敗 — 孤立リソースをクリーンアップしてリトライ
        local status
        status=$(aws cloudformation describe-stacks \
            --stack-name "$stack" \
            --query 'Stacks[0].StackStatus' \
            --output text \
            --region "$REGION" 2>/dev/null || echo "UNKNOWN")

        if [ "$status" = "DELETE_FAILED" ]; then
            echo "  ⚠️  Stack deletion failed. Cleaning up orphaned resources..."

            aws cloudformation describe-stack-events \
                --stack-name "$stack" \
                --query "StackEvents[?ResourceStatus=='DELETE_FAILED'].[LogicalResourceId,ResourceStatusReason]" \
                --output table \
                --region "$REGION" 2>/dev/null || true

            cleanup_orphaned_enis
            cleanup_orphaned_security_groups

            echo "  Waiting 30 seconds before retry..."
            sleep 30

            echo "  Retrying stack deletion..."
            aws cloudformation delete-stack --stack-name "$stack" --region "$REGION" 2>/dev/null || true
        else
            echo "  Stack status: $status (waiting...)"
            sleep 30
        fi

        retry=$((retry + 1))
    done

    echo "  ❌ Failed to delete $stack after $max_retries attempts"
    echo "     Manual intervention may be required."
    return 1
}

# =============================================================================
# メイン実行
# =============================================================================

echo "WARNING: This will delete all Phase 3 CloudFormation stacks:"
for stack in "${STACKS[@]}"; do
    echo "  - $stack"
done
echo ""
echo "Enhanced cleanup will handle:"
echo "  - Orphaned Lambda ENIs (5-20 min release delay)"
echo "  - Cross-referenced Security Groups"
echo "  - Automatic retry on DELETE_FAILED"
echo ""

if ! confirm_action "Continue with Phase 3 cleanup?"; then
    echo "Aborted."
    exit 0
fi

# Pre-deletion ENI cleanup (proactive — don't wait for stack failure)
echo ""
echo "--- Pre-deletion: Proactive ENI/SG cleanup ---"
cleanup_orphaned_enis
cleanup_orphaned_security_groups
echo ""

# Delete stacks
echo "--- Deleting CloudFormation Stacks ---"
for stack in "${STACKS[@]}"; do
    if aws cloudformation describe-stacks --stack-name "$stack" --region "$REGION" 2>/dev/null; then
        echo "  Initiating deletion: $stack"
        aws cloudformation delete-stack --stack-name "$stack" --region "$REGION" 2>/dev/null || true
    else
        echo "  ℹ️  Stack not found: $stack"
    fi
done

echo ""
echo "--- Waiting for stack deletions (with retry on failure) ---"
FAILED_STACKS=()
for stack in "${STACKS[@]}"; do
    if ! wait_for_stack_deletion_with_retry "$stack"; then
        FAILED_STACKS+=("$stack")
    fi
done

echo ""
if [ ${#FAILED_STACKS[@]} -eq 0 ]; then
    echo "=== ✅ Phase 3 Cleanup Complete — All stacks deleted ==="
else
    echo "=== ⚠️  Phase 3 Cleanup Complete — ${#FAILED_STACKS[@]} stack(s) require attention ==="
    for stack in "${FAILED_STACKS[@]}"; do
        echo "  ❌ $stack"
    done
fi
