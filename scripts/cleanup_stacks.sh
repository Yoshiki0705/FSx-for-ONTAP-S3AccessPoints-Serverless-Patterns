#!/bin/bash
# =============================================================================
# CloudFormation スタック クリーンアップスクリプト
# =============================================================================
#
# DELETE_FAILED スタックを検出し、ブロッカーリソースを事前削除してから
# スタック削除をリトライする汎用スクリプト。
#
# 対応するブロッカー:
#   - Athena WorkGroup (not empty) → RecursiveDeleteOption で強制削除
#   - S3 Bucket (not empty) → バケット内オブジェクト削除後にスタック削除
#   - ECR Repository (images exist) → イメージ削除後にスタック削除
#   - Lambda@Edge (replicas) → リトライ待機
#   - VPC ENI (in use) → 待機後リトライ
#
# 使用方法:
#   chmod +x scripts/cleanup_stacks.sh
#   ./scripts/cleanup_stacks.sh                    # DELETE_FAILED スタックを自動修復
#   ./scripts/cleanup_stacks.sh fsxn-eda-uc6       # 特定スタックを強制削除
#   ./scripts/cleanup_stacks.sh --all-project      # fsxn- プレフィックスの全スタック削除
#
# =============================================================================

set -euo pipefail

REGION="${AWS_DEFAULT_REGION:-ap-northeast-1}"
STACK_PREFIX="fsxn-"

# --- Helper Functions ---

log() { echo "[$(date +%H:%M:%S)] $*"; }
warn() { echo "[$(date +%H:%M:%S)] ⚠️  $*" >&2; }
ok() { echo "[$(date +%H:%M:%S)] ✅ $*"; }
fail() { echo "[$(date +%H:%M:%S)] ❌ $*" >&2; }

# Athena Workgroup を強制削除（中身ごと）
delete_athena_workgroup() {
    local workgroup_name="$1"
    log "Deleting Athena Workgroup: $workgroup_name (recursive)"
    aws athena delete-work-group \
        --work-group "$workgroup_name" \
        --recursive-delete-option \
        --region "$REGION" 2>&1 || true
}

# S3 バケットを空にして削除
empty_and_delete_s3_bucket() {
    local bucket_name="$1"
    log "Emptying S3 Bucket: $bucket_name"
    aws s3 rm "s3://$bucket_name" --recursive --region "$REGION" 2>&1 || true
    # バージョニング有効の場合
    aws s3api list-object-versions --bucket "$bucket_name" --region "$REGION" \
        --query '{Objects: Versions[].{Key:Key,VersionId:VersionId}}' --output json 2>/dev/null | \
        python3 -c "
import sys, json, boto3
data = json.load(sys.stdin)
objects = data.get('Objects') or []
if objects:
    s3 = boto3.client('s3', region_name='$REGION')
    s3.delete_objects(Bucket='$bucket_name', Delete={'Objects': objects[:1000]})
    print(f'  Deleted {len(objects)} versioned objects')
" 2>/dev/null || true
}

# ECR リポジトリのイメージを全削除
delete_ecr_images() {
    local repo_name="$1"
    log "Deleting ECR images in: $repo_name"
    local image_ids
    image_ids=$(aws ecr list-images --repository-name "$repo_name" --region "$REGION" \
        --query 'imageIds[*]' --output json 2>/dev/null)
    if [ "$image_ids" != "[]" ] && [ -n "$image_ids" ]; then
        aws ecr batch-delete-image --repository-name "$repo_name" \
            --image-ids "$image_ids" --region "$REGION" 2>&1 || true
    fi
}

# DELETE_FAILED スタックのブロッカーリソースを特定・削除
fix_delete_failed_stack() {
    local stack_name="$1"
    log "Analyzing DELETE_FAILED stack: $stack_name"

    # 失敗したリソースを取得
    local failed_resources
    failed_resources=$(aws cloudformation describe-stack-events \
        --stack-name "$stack_name" --region "$REGION" \
        --query 'StackEvents[?ResourceStatus==`DELETE_FAILED`].[LogicalResourceId,ResourceType,PhysicalResourceId,ResourceStatusReason]' \
        --output json 2>/dev/null)

    echo "$failed_resources" | python3 -c "
import sys, json, subprocess

events = json.load(sys.stdin)
if not events:
    print('  No DELETE_FAILED resources found')
    sys.exit(0)

for logical_id, resource_type, physical_id, reason in events:
    print(f'  Blocker: {logical_id} ({resource_type}) - {reason[:80]}')

    if resource_type == 'AWS::Athena::WorkGroup':
        subprocess.run(['bash', '-c', f'aws athena delete-work-group --work-group \"{physical_id}\" --recursive-delete-option --region $REGION 2>&1'], check=False)
        print(f'    → Deleted Athena WorkGroup: {physical_id}')

    elif resource_type == 'AWS::S3::Bucket':
        subprocess.run(['bash', '-c', f'aws s3 rm s3://{physical_id} --recursive --region $REGION 2>&1'], check=False)
        print(f'    → Emptied S3 Bucket: {physical_id}')

    elif resource_type == 'AWS::ECR::Repository':
        subprocess.run(['bash', '-c', f'aws ecr delete-repository --repository-name \"{physical_id}\" --force --region $REGION 2>&1'], check=False)
        print(f'    → Deleted ECR Repository: {physical_id}')

    elif 'NetworkInterface' in (reason or ''):
        print(f'    → ENI in use, will retry stack deletion (ENI auto-releases after ~20min)')

    else:
        print(f'    → Unknown blocker, attempting skip: {resource_type}')
" 2>/dev/null

    # ブロッカー削除後にスタック削除をリトライ
    log "Retrying stack deletion: $stack_name"
    aws cloudformation delete-stack --stack-name "$stack_name" --region "$REGION" 2>&1
    ok "Delete retry initiated for: $stack_name"
}

# スタックを削除（DELETE_FAILED の場合は修復してリトライ）
delete_stack() {
    local stack_name="$1"
    local status
    status=$(aws cloudformation describe-stacks --stack-name "$stack_name" --region "$REGION" \
        --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo "NOT_FOUND")

    case "$status" in
        DELETE_FAILED)
            warn "$stack_name is DELETE_FAILED — fixing blockers and retrying"
            fix_delete_failed_stack "$stack_name"
            ;;
        CREATE_COMPLETE|UPDATE_COMPLETE|UPDATE_ROLLBACK_COMPLETE|ROLLBACK_COMPLETE)
            log "Deleting stack: $stack_name (status: $status)"
            aws cloudformation delete-stack --stack-name "$stack_name" --region "$REGION" 2>&1
            ok "Delete initiated: $stack_name"
            ;;
        DELETE_IN_PROGRESS)
            log "Already deleting: $stack_name"
            ;;
        DELETE_COMPLETE|NOT_FOUND)
            log "Already deleted or not found: $stack_name"
            ;;
        *)
            warn "Unexpected status for $stack_name: $status"
            ;;
    esac
}

# --- Main ---

if [ "${1:-}" = "--all-project" ]; then
    log "Deleting ALL stacks with prefix: $STACK_PREFIX"
    STACKS=$(aws cloudformation list-stacks \
        --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE DELETE_FAILED UPDATE_ROLLBACK_COMPLETE ROLLBACK_COMPLETE \
        --region "$REGION" \
        --query "StackSummaries[?starts_with(StackName, \`$STACK_PREFIX\`)].StackName" \
        --output text 2>/dev/null)

    if [ -z "$STACKS" ]; then
        ok "No stacks found with prefix: $STACK_PREFIX"
        exit 0
    fi

    echo "Stacks to delete:"
    echo "$STACKS" | tr '\t' '\n' | sed 's/^/  /'
    echo ""
    read -p "Proceed? (y/N) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log "Aborted."
        exit 0
    fi

    for stack in $STACKS; do
        delete_stack "$stack"
    done

elif [ -n "${1:-}" ]; then
    delete_stack "$1"

else
    # Default: fix all DELETE_FAILED stacks
    log "Scanning for DELETE_FAILED stacks..."
    FAILED_STACKS=$(aws cloudformation list-stacks \
        --stack-status-filter DELETE_FAILED \
        --region "$REGION" \
        --query "StackSummaries[?starts_with(StackName, \`$STACK_PREFIX\`)].StackName" \
        --output text 2>/dev/null)

    if [ -z "$FAILED_STACKS" ]; then
        ok "No DELETE_FAILED stacks found."
        exit 0
    fi

    echo "DELETE_FAILED stacks found:"
    echo "$FAILED_STACKS" | tr '\t' '\n' | sed 's/^/  /'
    echo ""

    for stack in $FAILED_STACKS; do
        fix_delete_failed_stack "$stack"
    done
fi

log "Done. Use 'aws cloudformation list-stacks --stack-status-filter DELETE_IN_PROGRESS' to monitor progress."
