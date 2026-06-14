#!/bin/bash
# =============================================================================
# Phase 13 — Operational Readiness デプロイスクリプト
# =============================================================================
#
# Phase 13 の CloudFormation スタックをデプロイする。
# Phase 12 デプロイスクリプトのパターンを踏襲。
#
# 必須環境変数:
#   FSX_FILE_SYSTEM_ID  - FSx for ONTAP ファイルシステム ID
#   ONTAP_MGMT_IP       - ONTAP SVM 管理 IP アドレス
#   VPC_ID              - VPC ID
#   PRIVATE_SUBNET      - Private Subnet ID
#   SECURITY_GROUP      - Security Group ID
#   S3AP_ALIAS          - S3 Access Point エイリアス (xxx-ext-s3alias)
#   S3AP_NAME           - S3 Access Point 名 (IAM ARN 用)
#
# オプション環境変数:
#   AWS_DEFAULT_REGION   - デプロイリージョン (default: ap-northeast-1)
#   PROJECT_PREFIX       - リソース命名プレフィックス (default: fsxn-s3ap)
#   DEPLOY_BUCKET        - SAM パッケージ用 S3 バケット
#   SECRET_NAME          - Secrets Manager シークレット名
#   SNS_TOPIC_ARN        - SNS Topic ARN
#   SVM_UUID             - SVM UUID (FlexClone pipeline 用)
#   PARENT_VOLUME_UUID   - 親ボリューム UUID (FlexClone pipeline 用)
#   LINEAGE_TABLE_NAME   - Lineage DynamoDB テーブル名
#   ECS_CLUSTER          - ECS クラスター名 (Cost Dashboard 用)
#   ECS_SERVICE          - ECS サービス名 (Cost Dashboard 用)
#
# =============================================================================

set -euo pipefail

# --- Configuration ---
REGION="${AWS_DEFAULT_REGION:-ap-northeast-1}"
PROJECT_PREFIX="${PROJECT_PREFIX:-fsxn-s3ap}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo 'ACCOUNT_ID_NOT_SET')}"
DEPLOY_BUCKET="${DEPLOY_BUCKET:-fsxn-eda-deploy-${AWS_ACCOUNT_ID}}"

# Infrastructure references
# IMPORTANT: ONTAP_MGMT_IP must be the FILESYSTEM management IP, not the SVM management IP.
# fsxadmin only authenticates on the filesystem-level endpoint.
# Get it with: aws fsx describe-file-systems --query 'FileSystems[0].OntapConfiguration.Endpoints.Management.IpAddresses[0]'
ONTAP_MGMT_IP="${ONTAP_MGMT_IP:?'Set ONTAP_MGMT_IP env var (filesystem mgmt IP, NOT SVM mgmt IP)'}"
VPC_ID="${VPC_ID:?'Set VPC_ID env var'}"
PRIVATE_SUBNET="${PRIVATE_SUBNET:?'Set PRIVATE_SUBNET env var'}"
SECURITY_GROUP="${SECURITY_GROUP:?'Set SECURITY_GROUP env var'}"
S3AP_ALIAS="${S3AP_ALIAS:?'Set S3AP_ALIAS env var'}"
S3AP_NAME="${S3AP_NAME:?'Set S3AP_NAME env var'}"
SECRET_NAME="${SECRET_NAME:-fsx-ontap-fsxadmin-credentials}"  # Override with your Secrets Manager secret name
SNS_TOPIC_ARN="${SNS_TOPIC_ARN:-arn:aws:sns:${REGION}:${AWS_ACCOUNT_ID}:${PROJECT_PREFIX}-aggregated-alerts}"
SVM_UUID="${SVM_UUID:-}"
PARENT_VOLUME_UUID="${PARENT_VOLUME_UUID:-}"
LINEAGE_TABLE_NAME="${LINEAGE_TABLE_NAME:-${PROJECT_PREFIX}-data-lineage}"
ECS_CLUSTER="${ECS_CLUSTER:-${PROJECT_PREFIX}-fpolicy}"
ECS_SERVICE="${ECS_SERVICE:-${PROJECT_PREFIX}-fpolicy-server}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "============================================================"
echo "Phase 13 — Operational Readiness Deploy"
echo "============================================================"
echo "Region: $REGION"
echo "Project Prefix: $PROJECT_PREFIX"
echo "S3AP Alias: $S3AP_ALIAS"
echo "============================================================"
echo ""

# --- Helper functions ---
deploy_stack() {
    local stack_name="$1"
    local template="$2"
    shift 2
    local params=("$@")

    echo "▶ Deploying: $stack_name"
    aws cloudformation deploy \
        --template-file "$template" \
        --stack-name "$stack_name" \
        --parameter-overrides "${params[@]}" \
        --capabilities CAPABILITY_NAMED_IAM \
        --region "$REGION" \
        --no-fail-on-empty-changeset
    echo "  ✅ $stack_name: $(aws cloudformation describe-stacks --stack-name "$stack_name" --region "$REGION" --query 'Stacks[0].StackStatus' --output text)"
    echo ""
}

package_and_deploy() {
    local stack_name="$1"
    local template="$2"
    local s3_prefix="$3"
    shift 3
    local params=("$@")

    echo "▶ Packaging: $template"
    local packaged="/tmp/${stack_name}-packaged.yaml"
    aws cloudformation package \
        --template-file "$template" \
        --s3-bucket "$DEPLOY_BUCKET" \
        --s3-prefix "$s3_prefix" \
        --output-template-file "$packaged" \
        --region "$REGION"

    echo "▶ Deploying: $stack_name"
    aws cloudformation deploy \
        --template-file "$packaged" \
        --stack-name "$stack_name" \
        --parameter-overrides "${params[@]}" \
        --capabilities CAPABILITY_NAMED_IAM \
        --region "$REGION" \
        --no-fail-on-empty-changeset
    echo "  ✅ $stack_name: $(aws cloudformation describe-stacks --stack-name "$stack_name" --region "$REGION" --query 'Stacks[0].StackStatus' --output text)"
    echo ""
}

cd "$PROJECT_ROOT"

# --- 1. S3AP External Monitor (SAM) ---
package_and_deploy "fsxn-phase13-s3ap-external-monitor" \
    "shared/cfn/s3ap-external-monitor.yaml" \
    "phase13/s3ap-external-monitor" \
    "EnableS3APExternalMonitor=true" \
    "ProjectPrefix=$PROJECT_PREFIX" \
    "S3APAlias=$S3AP_ALIAS" \
    "S3AccessPointName=$S3AP_NAME" \
    "AlarmSNSTopic=$SNS_TOPIC_ARN"

# --- 1b. S3AP Resource Policy (required for Lambda access) ---
echo "▶ Setting S3AP resource policy for external monitor Lambda..."
aws s3control put-access-point-policy \
    --account-id "$AWS_ACCOUNT_ID" \
    --name "$S3AP_NAME" \
    --region "$REGION" \
    --policy "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"Phase13ExternalMonitor\",\"Effect\":\"Allow\",\"Principal\":{\"AWS\":\"arn:aws:iam::${AWS_ACCOUNT_ID}:role/${PROJECT_PREFIX}-s3ap-ext-monitor-role\"},\"Action\":[\"s3:ListBucket\",\"s3:GetObject\"],\"Resource\":[\"arn:aws:s3:${REGION}:${AWS_ACCOUNT_ID}:accesspoint/${S3AP_NAME}\",\"arn:aws:s3:${REGION}:${AWS_ACCOUNT_ID}:accesspoint/${S3AP_NAME}/object/*\"]}]}" 2>/dev/null \
    && echo "  ✅ S3AP resource policy set" \
    || echo "  ⚠️  S3AP resource policy update failed (may need manual configuration)"
echo ""

# --- 2. Cost Dashboard ---
deploy_stack "fsxn-phase13-cost-dashboard" \
    "shared/cfn/cost-dashboard.yaml" \
    "EnableCostDashboard=true" \
    "ProjectPrefix=$PROJECT_PREFIX" \
    "FPolicyClusterName=$ECS_CLUSTER" \
    "FPolicyServiceName=$ECS_SERVICE"

# --- 3. Lineage Retention (SAM) ---
package_and_deploy "fsxn-phase13-lineage-retention" \
    "shared/cfn/lineage-retention.yaml" \
    "phase13/lineage-retention" \
    "EnableLineageRetention=true" \
    "ProjectPrefix=$PROJECT_PREFIX" \
    "LineageTableName=$LINEAGE_TABLE_NAME" \
    "SnsTopicArn=$SNS_TOPIC_ARN"

# --- 4. FlexClone Pipeline (SAM, optional) ---
if [ -n "$SVM_UUID" ] && [ -n "$PARENT_VOLUME_UUID" ]; then
    package_and_deploy "fsxn-phase13-flexclone-pipeline" \
        "shared/cfn/flexclone-serverless-pipeline.yaml" \
        "phase13/flexclone-pipeline" \
        "EnableFlexClonePipeline=true" \
        "ProjectPrefix=$PROJECT_PREFIX" \
        "OntapMgmtIp=$ONTAP_MGMT_IP" \
        "OntapCredentialsSecret=$SECRET_NAME" \
        "SvmUuid=$SVM_UUID" \
        "ParentVolumeUuid=$PARENT_VOLUME_UUID" \
        "S3AccessPointAlias=$S3AP_ALIAS" \
        "S3AccessPointName=$S3AP_NAME" \
        "NotificationTopicArn=$SNS_TOPIC_ARN" \
        "VpcId=$VPC_ID" \
        "SubnetIds=$PRIVATE_SUBNET" \
        "SecurityGroupId=$SECURITY_GROUP"
else
    echo "⏭️  Skipping FlexClone Pipeline (SVM_UUID and PARENT_VOLUME_UUID not set)"
    echo ""
fi

# --- Summary ---
echo "============================================================"
echo "Phase 13 Deploy Complete!"
echo "============================================================"
aws cloudformation list-stacks \
    --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE \
    --region "$REGION" \
    --query 'StackSummaries[?starts_with(StackName, `fsxn-phase13`)].[StackName,StackStatus]' \
    --output table
echo ""

# --- Post-Deploy Verification ---
echo "▶ S3AP External Monitor Lambda Test:"
aws lambda invoke \
    --function-name "${PROJECT_PREFIX}-s3ap-ext-monitor" \
    --region "$REGION" \
    --payload '{}' \
    /tmp/s3ap-monitor-result.json 2>/dev/null && cat /tmp/s3ap-monitor-result.json || echo "  (invoke skipped)"
echo ""

echo "============================================================"
echo "Next steps:"
echo "  1. Verify S3AP monitor metric in CloudWatch"
echo "  2. Review Cost Dashboard"
echo "  3. Test Lineage Export: aws lambda invoke --function-name ${PROJECT_PREFIX}-lineage-export ..."
echo "  4. Run Operational Acceptance Criteria: docs/guides/operational-acceptance-criteria.md"
echo "============================================================"
