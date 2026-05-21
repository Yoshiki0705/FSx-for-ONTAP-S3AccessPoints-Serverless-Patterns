#!/bin/bash
# =============================================================================
# Diagnostic Bundle Collection Script
# =============================================================================
#
# SLO 違反時やインシデント対応時に診断情報を一括収集する。
# AWS 側の情報を自動収集し、ONTAP CLI コマンドは手動実行用に表示する。
#
# 使用方法:
#   export PROJECT_PREFIX=fsxn-s3ap
#   export SQS_QUEUE_URL=https://sqs.ap-northeast-1.amazonaws.com/123456789012/queue-name
#   export ECS_CLUSTER=fsxn-s3ap-fpolicy
#   export FPOLICY_SERVICE=fsxn-s3ap-fpolicy-server
#   export SVM_NAME=FSxN_OnPre
#   ./scripts/collect_diagnostic_bundle.sh
#
# 出力:
#   /tmp/diagnostic_bundle_YYYYMMDD_HHMMSS.tar.gz
#
# =============================================================================

set -euo pipefail

# --- Configuration ---
REGION="${AWS_DEFAULT_REGION:-ap-northeast-1}"
PROJECT_PREFIX="${PROJECT_PREFIX:-fsxn-s3ap}"
SQS_QUEUE_URL="${SQS_QUEUE_URL:-}"
ECS_CLUSTER="${ECS_CLUSTER:-${PROJECT_PREFIX}-fpolicy}"
FPOLICY_SERVICE="${FPOLICY_SERVICE:-${PROJECT_PREFIX}-fpolicy-server}"
SVM_NAME="${SVM_NAME:-FSxN_OnPre}"
LOOKBACK_MINUTES="${LOOKBACK_MINUTES:-30}"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_DIR="/tmp/diagnostic_bundle_${TIMESTAMP}"
mkdir -p "$OUTPUT_DIR"

echo "============================================================"
echo "Diagnostic Bundle Collection"
echo "============================================================"
echo "Timestamp: $TIMESTAMP"
echo "Region: $REGION"
echo "Lookback: ${LOOKBACK_MINUTES} minutes"
echo "Output: ${OUTPUT_DIR}"
echo "============================================================"
echo ""

# Calculate start time (N minutes ago in milliseconds)
if [[ "$OSTYPE" == "darwin"* ]]; then
    START_TIME=$(python3 -c "import time; print(int((time.time() - ${LOOKBACK_MINUTES} * 60) * 1000))")
else
    START_TIME=$(date -d "${LOOKBACK_MINUTES} minutes ago" +%s000)
fi

# --- 1. CloudWatch Alarm States ---
echo "▶ Collecting CloudWatch Alarm states..."
aws cloudwatch describe-alarms \
    --alarm-name-prefix "${PROJECT_PREFIX}" \
    --region "$REGION" \
    > "$OUTPUT_DIR/cloudwatch_alarms.json" 2>/dev/null || echo '{"error": "failed"}' > "$OUTPUT_DIR/cloudwatch_alarms.json"
echo "  ✅ cloudwatch_alarms.json"

# --- 2. FPolicy Server Logs ---
echo "▶ Collecting FPolicy server logs (last ${LOOKBACK_MINUTES} min)..."
aws logs filter-log-events \
    --log-group-name "/aws/ecs/${PROJECT_PREFIX}-fpolicy-server" \
    --start-time "$START_TIME" \
    --region "$REGION" \
    > "$OUTPUT_DIR/fpolicy_server_logs.json" 2>/dev/null || echo '{"error": "log group not found"}' > "$OUTPUT_DIR/fpolicy_server_logs.json"
echo "  ✅ fpolicy_server_logs.json"

# --- 3. Lambda Logs (S3AP Monitor) ---
echo "▶ Collecting S3AP monitor Lambda logs..."
aws logs filter-log-events \
    --log-group-name "/aws/lambda/${PROJECT_PREFIX}-s3ap-ext-monitor" \
    --start-time "$START_TIME" \
    --region "$REGION" \
    > "$OUTPUT_DIR/s3ap_monitor_logs.json" 2>/dev/null || echo '{"error": "log group not found"}' > "$OUTPUT_DIR/s3ap_monitor_logs.json"
echo "  ✅ s3ap_monitor_logs.json"

# --- 4. SQS Metrics ---
echo "▶ Collecting SQS queue attributes..."
if [ -n "$SQS_QUEUE_URL" ]; then
    aws sqs get-queue-attributes \
        --queue-url "$SQS_QUEUE_URL" \
        --attribute-names All \
        --region "$REGION" \
        > "$OUTPUT_DIR/sqs_attributes.json" 2>/dev/null || echo '{"error": "queue not found"}' > "$OUTPUT_DIR/sqs_attributes.json"
else
    echo '{"note": "SQS_QUEUE_URL not set"}' > "$OUTPUT_DIR/sqs_attributes.json"
fi
echo "  ✅ sqs_attributes.json"

# --- 5. ECS Service Status ---
echo "▶ Collecting ECS service status..."
aws ecs describe-services \
    --cluster "$ECS_CLUSTER" \
    --services "$FPOLICY_SERVICE" \
    --region "$REGION" \
    > "$OUTPUT_DIR/ecs_service.json" 2>/dev/null || echo '{"error": "service not found"}' > "$OUTPUT_DIR/ecs_service.json"
echo "  ✅ ecs_service.json"

# --- 6. ECS Tasks ---
echo "▶ Collecting ECS task details..."
TASK_ARNS=$(aws ecs list-tasks \
    --cluster "$ECS_CLUSTER" \
    --service-name "$FPOLICY_SERVICE" \
    --region "$REGION" \
    --query 'taskArns' --output json 2>/dev/null || echo '[]')
if [ "$TASK_ARNS" != "[]" ] && [ "$TASK_ARNS" != "" ]; then
    aws ecs describe-tasks \
        --cluster "$ECS_CLUSTER" \
        --tasks $(echo "$TASK_ARNS" | python3 -c "import sys,json; print(' '.join(json.load(sys.stdin)))") \
        --region "$REGION" \
        > "$OUTPUT_DIR/ecs_tasks.json" 2>/dev/null || echo '{"error": "describe failed"}' > "$OUTPUT_DIR/ecs_tasks.json"
else
    echo '{"note": "no running tasks"}' > "$OUTPUT_DIR/ecs_tasks.json"
fi
echo "  ✅ ecs_tasks.json"

# --- 7. Step Functions Recent Executions ---
echo "▶ Collecting Step Functions recent executions..."
aws stepfunctions list-executions \
    --state-machine-arn "arn:aws:states:${REGION}:$(aws sts get-caller-identity --query Account --output text):stateMachine:${PROJECT_PREFIX}-flexclone-pipeline" \
    --max-results 10 \
    --region "$REGION" \
    > "$OUTPUT_DIR/stepfunctions_executions.json" 2>/dev/null || echo '{"error": "state machine not found"}' > "$OUTPUT_DIR/stepfunctions_executions.json"
echo "  ✅ stepfunctions_executions.json"

# --- 8. CloudFormation Stack Status ---
echo "▶ Collecting CloudFormation stack status..."
aws cloudformation list-stacks \
    --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE CREATE_FAILED UPDATE_FAILED \
    --region "$REGION" \
    --query 'StackSummaries[?contains(StackName, `fsxn`)]' \
    > "$OUTPUT_DIR/cfn_stacks.json" 2>/dev/null || echo '[]' > "$OUTPUT_DIR/cfn_stacks.json"
echo "  ✅ cfn_stacks.json"

# --- Package ---
echo ""
echo "▶ Packaging bundle..."
tar -czf "${OUTPUT_DIR}.tar.gz" -C /tmp "diagnostic_bundle_${TIMESTAMP}"
BUNDLE_SIZE=$(ls -lh "${OUTPUT_DIR}.tar.gz" | awk '{print $5}')
echo "  ✅ ${OUTPUT_DIR}.tar.gz (${BUNDLE_SIZE})"

# --- ONTAP CLI Commands (manual) ---
echo ""
echo "============================================================"
echo "ONTAP CLI Commands (run manually on FSx ONTAP CLI)"
echo "============================================================"
echo ""
echo "  # FPolicy status"
echo "  fpolicy show -vserver ${SVM_NAME} -fields policy-name,status"
echo "  fpolicy show-engine -vserver ${SVM_NAME}"
echo ""
echo "  # Persistent Store"
echo "  fpolicy persistent-store show -vserver ${SVM_NAME}"
echo ""
echo "  # EMS logs"
echo "  event log show -messagename *fpolicy* -time >${LOOKBACK_MINUTES}m"
echo ""
echo "  # Network connectivity"
echo "  network ping -node \$(node show -query true -fields name | head -1) -destination <FARGATE_IP>"
echo ""
echo "============================================================"
echo "Bundle ready: ${OUTPUT_DIR}.tar.gz"
echo "============================================================"
