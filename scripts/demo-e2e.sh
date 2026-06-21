#!/bin/bash
# =============================================================================
# FSx for ONTAP S3 Access Points - End-to-End Demo Script
# =============================================================================
# This script deploys UC1 (Legal Compliance), triggers an execution,
# shows results, and optionally cleans up.
#
# Usage: ./scripts/demo-e2e.sh
# =============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

STACK_NAME="fsxn-s3ap-uc1-demo"
UC_DIR="solutions/industry/legal-compliance"

# =============================================================================
# Helper functions
# =============================================================================

info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

prompt_input() {
    local prompt="$1"
    local var_name="$2"
    local default="${3:-}"
    
    if [ -n "$default" ]; then
        read -rp "$(echo -e "${BLUE}?${NC}") $prompt [$default]: " input
        eval "$var_name=\"${input:-$default}\""
    else
        read -rp "$(echo -e "${BLUE}?${NC}") $prompt: " input
        [ -z "$input" ] && error "Value required for: $prompt"
        eval "$var_name=\"$input\""
    fi
}

confirm() {
    local prompt="$1"
    read -rp "$(echo -e "${YELLOW}?${NC}") $prompt [y/N]: " response
    [[ "$response" =~ ^[Yy]$ ]]
}

# =============================================================================
# Step 0: Check prerequisites
# =============================================================================

echo ""
echo "=============================================="
echo "  FSx for ONTAP S3 AP - E2E Demo"
echo "=============================================="
echo ""

info "Checking prerequisites..."

# Check AWS CLI
if ! command -v aws &> /dev/null; then
    error "AWS CLI not found. Install: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
fi
AWS_VERSION=$(aws --version 2>&1 | head -1)
success "AWS CLI: $AWS_VERSION"

# Check SAM CLI
if ! command -v sam &> /dev/null; then
    error "SAM CLI not found. Install: https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html"
fi
SAM_VERSION=$(sam --version 2>&1)
success "SAM CLI: $SAM_VERSION"

# Check Python
if ! command -v python3 &> /dev/null; then
    error "Python 3 not found. Install Python 3.12+"
fi
PYTHON_VERSION=$(python3 --version 2>&1)
success "Python: $PYTHON_VERSION"

# Check AWS credentials
if ! aws sts get-caller-identity &> /dev/null; then
    error "AWS credentials not configured. Run: aws configure"
fi
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=$(aws configure get region || echo "ap-northeast-1")
success "AWS Account: $ACCOUNT_ID (Region: $REGION)"

echo ""
info "All prerequisites met!"
echo ""

# =============================================================================
# Step 1: Gather inputs
# =============================================================================

echo "----------------------------------------------"
info "Step 1: Configuration"
echo "----------------------------------------------"
echo ""

prompt_input "S3 Access Point Alias (e.g., my-fsxn-s3ap-abc123)" S3AP_ALIAS
prompt_input "ONTAP Secret ARN (from Secrets Manager)" SECRET_ARN
prompt_input "Schedule Expression" SCHEDULE "rate(1 hour)"
prompt_input "Output Bucket Name" OUTPUT_BUCKET "fsxn-s3ap-demo-output-${ACCOUNT_ID}"
prompt_input "Stack Name" STACK_NAME "$STACK_NAME"

echo ""
info "Configuration summary:"
echo "  S3 AP Alias:    $S3AP_ALIAS"
echo "  Secret ARN:     $SECRET_ARN"
echo "  Schedule:       $SCHEDULE"
echo "  Output Bucket:  $OUTPUT_BUCKET"
echo "  Stack Name:     $STACK_NAME"
echo "  Region:         $REGION"
echo ""

if ! confirm "Proceed with deployment?"; then
    info "Aborted by user."
    exit 0
fi

# =============================================================================
# Step 2: Deploy UC1 (Legal Compliance)
# =============================================================================

echo ""
echo "----------------------------------------------"
info "Step 2: Deploying $UC_DIR template..."
echo "----------------------------------------------"
echo ""

# Check if UC directory exists
if [ ! -d "$UC_DIR" ]; then
    error "Directory '$UC_DIR' not found. Run this script from the repository root."
fi

cd "$UC_DIR"

# Build
info "Building SAM application..."
sam build --use-container 2>&1 | tail -5
success "Build complete."

# Deploy
info "Deploying stack: $STACK_NAME..."
sam deploy \
    --stack-name "$STACK_NAME" \
    --resolve-s3 \
    --capabilities CAPABILITY_IAM \
    --no-confirm-changeset \
    --parameter-overrides \
        "S3AccessPointAlias=$S3AP_ALIAS" \
        "OntapSecretArn=$SECRET_ARN" \
        "ScheduleExpression=$SCHEDULE" \
        "OutputBucketName=$OUTPUT_BUCKET" \
    2>&1 | tail -20

cd ..

# =============================================================================
# Step 3: Wait for stack creation
# =============================================================================

echo ""
echo "----------------------------------------------"
info "Step 3: Waiting for stack to complete..."
echo "----------------------------------------------"
echo ""

aws cloudformation wait stack-create-complete --stack-name "$STACK_NAME" 2>/dev/null || \
aws cloudformation wait stack-update-complete --stack-name "$STACK_NAME" 2>/dev/null || true

STACK_STATUS=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query 'Stacks[0].StackStatus' \
    --output text 2>/dev/null)

if [[ "$STACK_STATUS" == *"COMPLETE"* ]] && [[ "$STACK_STATUS" != *"ROLLBACK"* ]]; then
    success "Stack deployed successfully: $STACK_STATUS"
else
    error "Stack deployment failed: $STACK_STATUS"
fi

# Get State Machine ARN
STATE_MACHINE_ARN=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query 'Stacks[0].Outputs[?OutputKey==`StateMachineArn`].OutputValue' \
    --output text)

info "State Machine ARN: $STATE_MACHINE_ARN"

# =============================================================================
# Step 4: Trigger manual execution
# =============================================================================

echo ""
echo "----------------------------------------------"
info "Step 4: Triggering manual Step Functions execution..."
echo "----------------------------------------------"
echo ""

EXECUTION_ARN=$(aws stepfunctions start-execution \
    --state-machine-arn "$STATE_MACHINE_ARN" \
    --input '{}' \
    --query 'executionArn' \
    --output text)

success "Execution started: $EXECUTION_ARN"

# =============================================================================
# Step 5: Wait for execution to complete
# =============================================================================

echo ""
echo "----------------------------------------------"
info "Step 5: Waiting for execution to complete..."
echo "----------------------------------------------"
echo ""

TIMEOUT=300
ELAPSED=0
INTERVAL=10

while [ $ELAPSED -lt $TIMEOUT ]; do
    STATUS=$(aws stepfunctions describe-execution \
        --execution-arn "$EXECUTION_ARN" \
        --query 'status' \
        --output text)
    
    if [ "$STATUS" == "SUCCEEDED" ]; then
        success "Execution completed successfully!"
        break
    elif [ "$STATUS" == "FAILED" ] || [ "$STATUS" == "TIMED_OUT" ] || [ "$STATUS" == "ABORTED" ]; then
        warn "Execution ended with status: $STATUS"
        # Show error details
        aws stepfunctions describe-execution \
            --execution-arn "$EXECUTION_ARN" \
            --query 'error' \
            --output text 2>/dev/null || true
        break
    fi
    
    echo -ne "\r  Status: $STATUS (${ELAPSED}s / ${TIMEOUT}s timeout)..."
    sleep $INTERVAL
    ELAPSED=$((ELAPSED + INTERVAL))
done

if [ $ELAPSED -ge $TIMEOUT ]; then
    warn "Timed out waiting for execution (${TIMEOUT}s). Check console manually."
fi

echo ""

# =============================================================================
# Step 6: Show results
# =============================================================================

echo ""
echo "----------------------------------------------"
info "Step 6: Results"
echo "----------------------------------------------"
echo ""

# Show execution output
info "Execution output:"
aws stepfunctions describe-execution \
    --execution-arn "$EXECUTION_ARN" \
    --query 'output' \
    --output text 2>/dev/null | python3 -m json.tool 2>/dev/null || echo "  (no output or parse error)"

echo ""

# Show CloudWatch Logs (last 10 entries from Discovery function)
DISCOVERY_LOG_GROUP="/aws/lambda/${STACK_NAME}-DiscoveryFunction"
info "Recent CloudWatch Logs (Discovery):"
aws logs tail "$DISCOVERY_LOG_GROUP" \
    --since 30m \
    --format short 2>/dev/null | head -20 || warn "Could not fetch logs from $DISCOVERY_LOG_GROUP"

echo ""

# Show S3 output
info "S3 Output Bucket contents:"
aws s3 ls "s3://${OUTPUT_BUCKET}/" --recursive 2>/dev/null | head -20 || warn "Bucket empty or not accessible"

echo ""

# Console links
info "Console links:"
echo "  Step Functions: https://${REGION}.console.aws.amazon.com/states/home?region=${REGION}#/statemachines/view/${STATE_MACHINE_ARN}"
echo "  CloudWatch:     https://${REGION}.console.aws.amazon.com/cloudwatch/home?region=${REGION}#logsV2:log-groups"
echo "  S3 Output:      https://s3.console.aws.amazon.com/s3/buckets/${OUTPUT_BUCKET}"

# =============================================================================
# Step 7: Cleanup (optional)
# =============================================================================

echo ""
echo "----------------------------------------------"
info "Step 7: Cleanup"
echo "----------------------------------------------"
echo ""

if confirm "Delete the demo stack ($STACK_NAME)?"; then
    info "Emptying output bucket..."
    aws s3 rm "s3://${OUTPUT_BUCKET}" --recursive 2>/dev/null || true
    
    info "Deleting stack..."
    sam delete --stack-name "$STACK_NAME" --no-prompts 2>&1 | tail -5
    
    success "Stack deleted."
    
    if confirm "Also delete the output bucket ($OUTPUT_BUCKET)?"; then
        aws s3 rb "s3://${OUTPUT_BUCKET}" --force 2>/dev/null || true
        success "Bucket deleted."
    fi
else
    info "Stack preserved. To clean up later:"
    echo "  sam delete --stack-name $STACK_NAME"
fi

echo ""
echo "=============================================="
success "Demo complete!"
echo "=============================================="
echo ""
echo "Next steps:"
echo "  - Try event-driven mode: cd solutions/event-driven/fpolicy/"
echo "  - Deploy SAP pattern:    cd solutions/sap/erp-adjacent/"
echo "  - Read the docs:         docs/quick-start.md"
echo ""
