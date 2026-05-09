#!/bin/bash
set -euo pipefail

# =============================================================================
# deploy-hooks.sh — CloudFormation Guard Hooks デプロイスクリプト
#
# cfn-guard ルールを S3 にアップロードし、Guard Hooks スタックをデプロイする。
# UC テンプレートとは独立したスタックとして管理する。
#
# Usage:
#   ./scripts/deploy-hooks.sh [OPTIONS]
#
# Options:
#   --stack-name NAME       スタック名 (default: fsxn-s3ap-guard-hooks)
#   --bucket-name NAME      S3 バケット名 (default: fsxn-s3ap-guard-rules-{ACCOUNT_ID})
#   --failure-mode MODE     FAIL or WARN (default: FAIL)
#   --region REGION         AWS リージョン (default: ap-northeast-1)
#   --dry-run               ドライラン（S3 アップロードのみ、スタックデプロイなし）
#   --help                  ヘルプ表示
# =============================================================================

# デフォルト値
STACK_NAME="fsxn-s3ap-guard-hooks"
BUCKET_NAME=""
FAILURE_MODE="FAIL"
REGION="ap-northeast-1"
DRY_RUN=false
RULES_PREFIX="cfn-guard-rules/"

# プロジェクトルートディレクトリ
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RULES_DIR="${PROJECT_ROOT}/security/cfn-guard-rules"
TEMPLATE_PATH="${PROJECT_ROOT}/shared/cfn/guard-hooks.yaml"

# カラー出力
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ヘルプ表示
show_help() {
    cat << 'EOF'
CloudFormation Guard Hooks デプロイスクリプト

Usage:
  ./scripts/deploy-hooks.sh [OPTIONS]

Options:
  --stack-name NAME       スタック名 (default: fsxn-s3ap-guard-hooks)
  --bucket-name NAME      S3 バケット名 (default: fsxn-s3ap-guard-rules-{ACCOUNT_ID})
  --failure-mode MODE     FAIL or WARN (default: FAIL)
  --region REGION         AWS リージョン (default: ap-northeast-1)
  --dry-run               ドライラン（S3 アップロードのみ、スタックデプロイなし）
  --help                  ヘルプ表示

Examples:
  # 本番デプロイ（FAIL モード）
  ./scripts/deploy-hooks.sh --failure-mode FAIL

  # テストデプロイ（WARN モード）
  ./scripts/deploy-hooks.sh --failure-mode WARN --stack-name guard-hooks-test

  # ドライラン（ルールアップロードのみ）
  ./scripts/deploy-hooks.sh --dry-run
EOF
}

# 引数パース
while [[ $# -gt 0 ]]; do
    case $1 in
        --stack-name)
            STACK_NAME="$2"
            shift 2
            ;;
        --bucket-name)
            BUCKET_NAME="$2"
            shift 2
            ;;
        --failure-mode)
            FAILURE_MODE="$2"
            shift 2
            ;;
        --region)
            REGION="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --help)
            show_help
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# バリデーション
if [[ "${FAILURE_MODE}" != "FAIL" && "${FAILURE_MODE}" != "WARN" ]]; then
    log_error "Invalid failure-mode: ${FAILURE_MODE}. Must be FAIL or WARN."
    exit 1
fi

if [[ ! -d "${RULES_DIR}" ]]; then
    log_error "Guard rules directory not found: ${RULES_DIR}"
    exit 1
fi

if [[ ! -f "${TEMPLATE_PATH}" ]]; then
    log_error "Guard hooks template not found: ${TEMPLATE_PATH}"
    exit 1
fi

# AWS アカウント ID 取得
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text --region "${REGION}")
log_info "AWS Account: ${ACCOUNT_ID}"
log_info "Region: ${REGION}"

# バケット名のデフォルト設定
if [[ -z "${BUCKET_NAME}" ]]; then
    BUCKET_NAME="fsxn-s3ap-guard-rules-${ACCOUNT_ID}"
fi
log_info "S3 Bucket: ${BUCKET_NAME}"

# =============================================================================
# Phase 1: cfn-guard ルールを S3 にアップロード
# =============================================================================
log_info "=== Phase 1: Uploading cfn-guard rules to S3 ==="

# ルールファイルの存在確認
RULE_FILES=$(find "${RULES_DIR}" -name "*.guard" -type f)
RULE_COUNT=$(echo "${RULE_FILES}" | wc -l | tr -d ' ')

if [[ ${RULE_COUNT} -eq 0 ]]; then
    log_error "No .guard files found in ${RULES_DIR}"
    exit 1
fi

log_info "Found ${RULE_COUNT} guard rule files"

# S3 バケットの存在確認（存在しない場合はスタックデプロイで作成される）
if aws s3api head-bucket --bucket "${BUCKET_NAME}" --region "${REGION}" 2>/dev/null; then
    log_info "S3 bucket exists: ${BUCKET_NAME}"
else
    log_warn "S3 bucket does not exist yet: ${BUCKET_NAME}"
    log_info "Bucket will be created by the CloudFormation stack"

    if [[ "${DRY_RUN}" == "true" ]]; then
        log_warn "Dry-run mode: skipping S3 upload (bucket doesn't exist)"
        log_info "=== Dry-run complete ==="
        exit 0
    fi
fi

# ルールファイルをアップロード（バケットが存在する場合のみ）
if aws s3api head-bucket --bucket "${BUCKET_NAME}" --region "${REGION}" 2>/dev/null; then
    for rule_file in ${RULE_FILES}; do
        filename=$(basename "${rule_file}")
        s3_key="${RULES_PREFIX}${filename}"
        log_info "Uploading: ${filename} → s3://${BUCKET_NAME}/${s3_key}"
        aws s3 cp "${rule_file}" "s3://${BUCKET_NAME}/${s3_key}" --region "${REGION}"
    done

    # params.json のアップロード（存在する場合）
    PARAMS_FILE="${RULES_DIR}/params.json"
    if [[ -f "${PARAMS_FILE}" ]]; then
        log_info "Uploading params.json"
        aws s3 cp "${PARAMS_FILE}" "s3://${BUCKET_NAME}/${RULES_PREFIX}params.json" --region "${REGION}"
    fi

    log_info "All rules uploaded successfully"
fi

if [[ "${DRY_RUN}" == "true" ]]; then
    log_info "=== Dry-run complete (rules uploaded, stack not deployed) ==="
    exit 0
fi

# =============================================================================
# Phase 2: Guard Hooks スタックをデプロイ
# =============================================================================
log_info "=== Phase 2: Deploying Guard Hooks stack ==="
log_info "Stack name: ${STACK_NAME}"
log_info "Failure mode: ${FAILURE_MODE}"

aws cloudformation deploy \
    --template-file "${TEMPLATE_PATH}" \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}" \
    --capabilities CAPABILITY_NAMED_IAM \
    --parameter-overrides \
        GuardRulesBucketName="${BUCKET_NAME}" \
        GuardRulesKeyPrefix="${RULES_PREFIX}" \
        FailureMode="${FAILURE_MODE}" \
        TargetStacks="ALL" \
    --tags \
        Key=Project,Value=fsxn-s3ap-serverless-patterns \
        Key=Phase,Value=6B \
        Key=Component,Value=guard-hooks

log_info "Stack deployed successfully"

# =============================================================================
# Phase 3: ルールファイルをアップロード（スタック作成後）
# =============================================================================
log_info "=== Phase 3: Uploading rules to newly created bucket ==="

for rule_file in ${RULE_FILES}; do
    filename=$(basename "${rule_file}")
    s3_key="${RULES_PREFIX}${filename}"
    log_info "Uploading: ${filename} → s3://${BUCKET_NAME}/${s3_key}"
    aws s3 cp "${rule_file}" "s3://${BUCKET_NAME}/${s3_key}" --region "${REGION}"
done

# params.json のアップロード（存在する場合）
PARAMS_FILE="${RULES_DIR}/params.json"
if [[ -f "${PARAMS_FILE}" ]]; then
    log_info "Uploading params.json"
    aws s3 cp "${PARAMS_FILE}" "s3://${BUCKET_NAME}/${RULES_PREFIX}params.json" --region "${REGION}"
fi

# =============================================================================
# Phase 4: デプロイ確認
# =============================================================================
log_info "=== Phase 4: Verifying deployment ==="

STACK_STATUS=$(aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}" \
    --query "Stacks[0].StackStatus" \
    --output text)

if [[ "${STACK_STATUS}" == *"COMPLETE"* ]]; then
    log_info "Stack status: ${STACK_STATUS} ✅"
else
    log_error "Stack status: ${STACK_STATUS} ❌"
    exit 1
fi

# Outputs 表示
log_info "=== Stack Outputs ==="
aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}" \
    --query "Stacks[0].Outputs[*].[OutputKey,OutputValue]" \
    --output table

log_info "=== Guard Hooks deployment complete ==="
log_info ""
log_info "次のステップ:"
log_info "  1. テスト: 意図的にルール違反するテンプレートでブロック確認"
log_info "  2. 監視: CloudWatch Logs で Hook 実行ログを確認"
log_info "  3. 無効化: --failure-mode WARN で再デプロイ、または TargetStacks=NONE"
