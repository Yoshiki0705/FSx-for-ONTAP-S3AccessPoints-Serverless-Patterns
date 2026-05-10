#!/bin/bash
# Upload sample data + start Step Functions for a single UC.
set -u

REGION="${AWS_REGION:-ap-northeast-1}"
ACCOUNT_ID="${ACCOUNT_ID:-<ACCOUNT_ID>}"
S3_AP_NAME="${S3_AP_NAME:-eda-demo-s3ap}"
# For put-object, must use the AP ARN form (can't use alias for uploads)
S3_AP_ARN_PREFIX="s3://arn:aws:s3:${REGION}:${ACCOUNT_ID}:accesspoint/${S3_AP_NAME}"

UC="${1:-}"
if [[ -z "$UC" ]]; then
  echo "Usage: $0 <UC_NAME>"
  echo "Example: UC1, UC2, UC3, UC5, UC7, UC8, UC9, UC10, UC12, UC13"
  exit 1
fi

# Map UC → directory + sample key + local file + prefix
case "$UC" in
  UC1)
    DIR="legal-compliance"
    STACK="fsxn-legal-compliance-demo"
    LOCAL_FILE="/tmp/uc1_contract.pdf"
    S3_KEY="contracts/2026/05/sample_contract.pdf"
    ;;
  UC2)
    DIR="financial-idp"
    STACK="fsxn-financial-idp-demo"
    LOCAL_FILE="/tmp/uc2_invoice.pdf"
    S3_KEY="invoices/2026/05/sample_invoice.pdf"
    ;;
  UC3)
    DIR="manufacturing-analytics"
    STACK="fsxn-manufacturing-analytics-demo"
    LOCAL_FILE="/tmp/uc3_sensors.csv"
    S3_KEY="sensors/2026/05/sensor_data.csv"
    ;;
  UC5)
    DIR="healthcare-dicom"
    STACK="fsxn-healthcare-dicom-demo"
    LOCAL_FILE="/tmp/uc5_dicom_meta.json"
    S3_KEY="dicom/2026/05/patient001.json"
    ;;
  UC7)
    DIR="genomics-pipeline"
    STACK="fsxn-genomics-pipeline-demo"
    LOCAL_FILE="/tmp/uc7_sample.fastq"
    S3_KEY="genomics/2026/05/sample001.fastq"
    ;;
  UC8)
    DIR="energy-seismic"
    STACK="fsxn-energy-seismic-demo"
    LOCAL_FILE="/tmp/uc8_seismic.segy"
    S3_KEY="seismic/2026/05/survey001.segy"
    ;;
  UC9)
    DIR="autonomous-driving"
    STACK="fsxn-autonomous-driving-demo"
    LOCAL_FILE="/tmp/uc3_inspection.jpg"
    S3_KEY="adas/2026/05/sensor_frame.jpg"
    ;;
  UC10)
    DIR="construction-bim"
    STACK="fsxn-construction-bim-demo"
    LOCAL_FILE="/tmp/uc10_drawing.pdf"
    S3_KEY="drawings/2026/05/floor_plan.pdf"
    ;;
  UC12)
    DIR="logistics-ocr"
    STACK="fsxn-logistics-ocr-demo"
    LOCAL_FILE="/tmp/uc12_waybill.pdf"
    S3_KEY="waybills/2026/05/WB-2026-5001.pdf"
    ;;
  UC13)
    DIR="education-research"
    STACK="fsxn-education-research-demo"
    LOCAL_FILE="/tmp/uc13_paper.pdf"
    S3_KEY="papers/2026/05/paper001.pdf"
    ;;
  *)
    echo "Unknown UC: $UC"
    exit 1
    ;;
esac

if [[ ! -f "$LOCAL_FILE" ]]; then
  echo "ERROR: Local sample not found: $LOCAL_FILE"
  echo "Run: python3 build/gen_samples.py first"
  exit 1
fi

echo "=== $UC: Upload $LOCAL_FILE → s3://<AP>/$S3_KEY ==="
aws s3 cp "$LOCAL_FILE" "${S3_AP_ARN_PREFIX}/${S3_KEY}" --region "$REGION" 2>&1 | tail -3 || {
  echo "Upload failed. Trying fallback direct bucket write..."
}

# Also upload a 2nd file for UC3 (image)
if [[ "$UC" == "UC3" ]]; then
  echo "=== UC3: Upload image ==="
  aws s3 cp /tmp/uc3_inspection.jpg "${S3_AP_ARN_PREFIX}/sensors/2026/05/inspection.jpg" --region "$REGION" 2>&1 | tail -3 || true
fi

# Find Step Functions ARN from stack
SFN_ARN=$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" --query "Stacks[0].Outputs[?OutputKey=='StateMachineArn' || OutputKey=='WorkflowStateMachineArn'].OutputValue" --output text 2>&1)

if [[ -z "$SFN_ARN" || "$SFN_ARN" == "None" ]]; then
  echo "Looking for State Machine directly..."
  SFN_ARN=$(aws stepfunctions list-state-machines --region "$REGION" --query "stateMachines[?contains(name, '${STACK}')].stateMachineArn" --output text | head -1)
fi

if [[ -z "$SFN_ARN" ]]; then
  echo "ERROR: Could not find Step Functions ARN for $STACK"
  exit 1
fi

echo "=== $UC: Start Step Functions execution ==="
EXEC_ARN=$(aws stepfunctions start-execution \
  --region "$REGION" \
  --state-machine-arn "$SFN_ARN" \
  --input '{}' \
  --query 'executionArn' --output text 2>&1)

echo "Execution ARN: $EXEC_ARN"
echo "Waiting for completion (up to 120s)..."

for i in {1..24}; do
  sleep 5
  STATUS=$(aws stepfunctions describe-execution --region "$REGION" --execution-arn "$EXEC_ARN" --query 'status' --output text 2>&1)
  echo "  [${i}/24] Status: $STATUS"
  if [[ "$STATUS" == "SUCCEEDED" ]]; then
    echo "✅ $UC: SUCCEEDED"
    aws stepfunctions describe-execution --region "$REGION" --execution-arn "$EXEC_ARN" --query '{Status:status, Duration:executionTime}' --output json 2>&1 | head -5
    exit 0
  elif [[ "$STATUS" == "FAILED" || "$STATUS" == "TIMED_OUT" || "$STATUS" == "ABORTED" ]]; then
    echo "❌ $UC: $STATUS"
    aws stepfunctions describe-execution --region "$REGION" --execution-arn "$EXEC_ARN" --query '{Status:status, Input:input, Cause:cause}' --output json 2>&1 | head -20
    exit 1
  fi
done

echo "⏱️  $UC: Still running after 120s"
exit 2
