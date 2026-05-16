#!/bin/bash
# =============================================================================
# Phase 12 — Operational Hardening & Observability デプロイスクリプト
# =============================================================================
#
# 全 7 CloudFormation スタックを ap-northeast-1 にデプロイする。
# SAM Transform を使用するテンプレートは自動的に package → deploy を実行。
#
# 使用方法:
#   chmod +x scripts/deploy_phase12.sh
#   ./scripts/deploy_phase12.sh
#
# 前提条件:
#   - AWS CLI が設定済み（ap-northeast-1 リージョン）
#   - 以下の環境変数が設定済み（または下記のデフォルト値を使用）
#
# =============================================================================

set -euo pipefail

# --- Configuration ---
REGION="${AWS_DEFAULT_REGION:-ap-northeast-1}"
PROJECT_PREFIX="${PROJECT_PREFIX:-fsxn-s3ap}"
DEPLOY_BUCKET="${DEPLOY_BUCKET:-fsxn-eda-deploy-178625946981}"

# Infrastructure references (from existing deployment)
FSX_FILE_SYSTEM_ID="${FSX_FILE_SYSTEM_ID:-fs-09ffe72a3b2b7dbbd}"
ONTAP_MGMT_IP="${ONTAP_MGMT_IP:-10.0.3.72}"
VPC_ID="${VPC_ID:-vpc-0ae01826f906191af}"
PRIVATE_SUBNET="${PRIVATE_SUBNET:-subnet-0307ebbd55b35c842}"
SECURITY_GROUP="${SECURITY_GROUP:-sg-04b2fedb571860818}"
SECRET_ARN="${SECRET_ARN:-arn:aws:secretsmanager:ap-northeast-1:178625946981:secret:fsx-ontap-fsxadmin-credentials-P9Ibbi}"
SECRET_NAME="${SECRET_NAME:-fsx-ontap-fsxadmin-credentials}"
SNS_TOPIC_ARN="${SNS_TOPIC_ARN:-arn:aws:sns:ap-northeast-1:178625946981:fsxn-s3ap-aggregated-alerts}"
S3AP_ALIAS="${S3AP_ALIAS:-fsxn-eda-s3ap-fhyst3uaibf46uywh5xka84pnz8jaapn1a-ext-s3alias}"
OAM_SINK_ARN="${OAM_SINK_ARN:-}"  # Empty = OAM Link disabled (single account)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "============================================================"
echo "Phase 12 — Operational Hardening & Observability Deploy"
echo "============================================================"
echo "Region: $REGION"
echo "Project Prefix: $PROJECT_PREFIX"
echo "Deploy Bucket: $DEPLOY_BUCKET"
echo "FSx File System: $FSX_FILE_SYSTEM_ID"
echo "============================================================"
echo ""

# --- Helper function ---
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

    echo "▶ Packaging: $template → s3://$DEPLOY_BUCKET/$s3_prefix/"
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

# --- 1. Guardrails Table ---
deploy_stack "fsxn-phase12-guardrails-table" \
    "shared/cfn/guardrails-table.yaml" \
    "EnableGuardrails=true" \
    "ProjectPrefix=$PROJECT_PREFIX"

# --- 2. Lineage Table ---
deploy_stack "fsxn-phase12-lineage-table" \
    "shared/cfn/lineage-table.yaml" \
    "EnableDataLineage=true" \
    "ProjectPrefix=$PROJECT_PREFIX"

# --- 3. SLO Dashboard ---
deploy_stack "fsxn-phase12-slo-dashboard" \
    "shared/cfn/slo-dashboard.yaml" \
    "EnableSLODashboard=true" \
    "ProjectPrefix=$PROJECT_PREFIX" \
    "SnsTopicArn=$SNS_TOPIC_ARN"

# --- 4. OAM Link ---
deploy_stack "fsxn-phase12-oam-link" \
    "shared/cfn/oam-link.yaml" \
    "MonitoringAccountSinkArn=$OAM_SINK_ARN" \
    "ProjectPrefix=$PROJECT_PREFIX"

# --- 5. Capacity Forecast (SAM) ---
package_and_deploy "fsxn-phase12-capacity-forecast" \
    "shared/cfn/capacity-forecast.yaml" \
    "phase12/capacity-forecast" \
    "EnableCapacityForecast=true" \
    "ProjectPrefix=$PROJECT_PREFIX" \
    "FileSystemId=$FSX_FILE_SYSTEM_ID" \
    "TotalCapacityGb=1024" \
    "SnsTopicArn=$SNS_TOPIC_ARN"

# --- 6. Secrets Rotation (SAM) ---
package_and_deploy "fsxn-phase12-secrets-rotation" \
    "shared/cfn/secrets-rotation.yaml" \
    "phase12/secrets-rotation" \
    "EnableSecretsRotation=true" \
    "ProjectPrefix=$PROJECT_PREFIX" \
    "SecretArn=$SECRET_ARN" \
    "OntapMgmtIp=$ONTAP_MGMT_IP" \
    "VpcId=$VPC_ID" \
    "SubnetIds=$PRIVATE_SUBNET" \
    "SecurityGroupId=$SECURITY_GROUP" \
    "SnsTopicArn=$SNS_TOPIC_ARN"

# --- 7. Synthetic Monitoring ---
# Upload canary code first
echo "▶ Uploading Canary code to S3..."
mkdir -p /tmp/canary-package/python
cp shared/lambdas/canary/s3ap_health_check.py /tmp/canary-package/python/
(cd /tmp/canary-package && zip -r /tmp/s3ap_health_check.zip python/)
aws s3 cp /tmp/s3ap_health_check.zip "s3://$DEPLOY_BUCKET/canary-code/s3ap_health_check.zip" --region "$REGION"
echo "  ✅ Canary code uploaded"

deploy_stack "fsxn-phase12-synthetic-monitoring" \
    "shared/cfn/synthetic-monitoring.yaml" \
    "EnableSyntheticMonitoring=true" \
    "ProjectPrefix=$PROJECT_PREFIX" \
    "S3AccessPointAlias=$S3AP_ALIAS" \
    "OntapMgmtIp=$ONTAP_MGMT_IP" \
    "OntapCredentialsSecret=$SECRET_NAME" \
    "SnsTopicArn=$SNS_TOPIC_ARN" \
    "ArtifactBucket=$DEPLOY_BUCKET"

# --- Summary ---
echo "============================================================"
echo "Phase 12 Deploy Complete!"
echo "============================================================"
aws cloudformation list-stacks \
    --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE \
    --region "$REGION" \
    --query 'StackSummaries[?starts_with(StackName, `fsxn-phase12`)].[StackName,StackStatus]' \
    --output table
echo ""

# =============================================================================
# Post-Deploy Verification
# =============================================================================
echo "============================================================"
echo "Post-Deploy Verification"
echo "============================================================"
echo ""

# --- Check all 7 stacks are CREATE_COMPLETE ---
echo "▶ Stack Status Check (expecting 7 stacks CREATE_COMPLETE or UPDATE_COMPLETE):"
STACKS=(
    "fsxn-phase12-guardrails-table"
    "fsxn-phase12-lineage-table"
    "fsxn-phase12-slo-dashboard"
    "fsxn-phase12-oam-link"
    "fsxn-phase12-capacity-forecast"
    "fsxn-phase12-secrets-rotation"
    "fsxn-phase12-synthetic-monitoring"
)
ALL_OK=true
for stack in "${STACKS[@]}"; do
    STATUS=$(aws cloudformation describe-stacks --stack-name "$stack" --region "$REGION" \
        --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo "NOT_FOUND")
    if [[ "$STATUS" == "CREATE_COMPLETE" || "$STATUS" == "UPDATE_COMPLETE" ]]; then
        echo "  ✅ $stack: $STATUS"
    else
        echo "  ❌ $stack: $STATUS"
        ALL_OK=false
    fi
done
echo ""

if [ "$ALL_OK" = true ]; then
    echo "  ✅ All 7 stacks deployed successfully"
else
    echo "  ⚠️  Some stacks are not in expected state"
fi
echo ""

# --- Invoke Capacity Forecast Lambda ---
echo "▶ Capacity Forecast Lambda Invocation:"
FORECAST_RESULT=$(aws lambda invoke \
    --function-name "${PROJECT_PREFIX}-capacity-forecast" \
    --region "$REGION" \
    --payload '{}' \
    /tmp/capacity-forecast-result.json 2>&1 && cat /tmp/capacity-forecast-result.json || echo "INVOKE_FAILED")
echo "  Result: $FORECAST_RESULT"
echo ""

# --- Check Canary Status ---
echo "▶ Synthetic Monitoring Canary Status:"
CANARY_STATUS=$(aws synthetics get-canary \
    --name "${PROJECT_PREFIX}-s3ap-health" \
    --region "$REGION" \
    --query 'Canary.Status.State' --output text 2>/dev/null || echo "NOT_FOUND")
echo "  Canary State: $CANARY_STATUS"
CANARY_LAST=$(aws synthetics get-canary-runs \
    --name "${PROJECT_PREFIX}-s3ap-health" \
    --region "$REGION" \
    --max-results 1 \
    --query 'CanaryRuns[0].Status.State' --output text 2>/dev/null || echo "NO_RUNS")
echo "  Last Run: $CANARY_LAST"
echo ""

# --- Check SLO Alarm States ---
echo "▶ SLO Alarm States:"
aws cloudwatch describe-alarms \
    --alarm-name-prefix "${PROJECT_PREFIX}-slo-" \
    --region "$REGION" \
    --query 'MetricAlarms[].[AlarmName,StateValue]' \
    --output table 2>/dev/null || echo "  No SLO alarms found"
echo ""

# --- Print SLO Dashboard URL ---
DASHBOARD_URL="https://${REGION}.console.aws.amazon.com/cloudwatch/home?region=${REGION}#dashboards/dashboard/${PROJECT_PREFIX}-slo-dashboard"
echo "▶ SLO Dashboard URL:"
echo "  $DASHBOARD_URL"
echo ""

echo "============================================================"
echo "Next steps:"
echo "  1. Create health marker file on NFS: /mnt/fsxn/_health/marker.txt"
echo "  2. Verify Canary passes after marker file creation"
echo "  3. Test Secrets Rotation: aws secretsmanager rotate-secret --secret-id $SECRET_ARN"
echo "  4. View SLO Dashboard: $DASHBOARD_URL"
