#!/usr/bin/env bash
# =============================================================================
# deploy-stepfunctions-agentcore.sh
#
# Deploy the Step Functions x AgentCore Gateway pattern. The whole pattern is
# declarative CloudFormation, including the AgentCore Gateway and the Step
# Functions connector target (AWS::BedrockAgentCore::Gateway / ::GatewayTarget),
# so this script is a thin wrapper around `sam build` + `sam deploy` that then
# verifies the gateway's tools/list.
#
# Prerequisites:
#   - AWS CLI v2 configured (SSO login current)
#   - A deployed S3 Access Point (or a regular bucket for DemoMode)
#   - SAM CLI, python3
#
# Usage:
#   ./scripts/deploy-stepfunctions-agentcore.sh \
#     --s3ap-alias my-ap-xxxxx-ext-s3alias --stack-name sfn-agentcore-tools
#
#   ./scripts/deploy-stepfunctions-agentcore.sh --s3ap-alias my-bucket --demo-mode
#   ./scripts/deploy-stepfunctions-agentcore.sh --cleanup --stack-name sfn-agentcore-tools
#
# Reference:
#   solutions/genai/stepfunctions-agentcore-tools/docs/demo-guide.md
# =============================================================================
set -euo pipefail

# --- Defaults ---
GATEWAY_REGION="${AGENTCORE_REGION:-ap-northeast-1}"
STACK_NAME="sfn-agentcore-tools"
S3AP_ALIAS=""
GATEWAY_NAME="sfn-agentcore-tools-gateway"
ACTION="deploy"
DEMO_MODE="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --s3ap-alias) S3AP_ALIAS="$2"; shift 2 ;;
    --stack-name) STACK_NAME="$2"; shift 2 ;;
    --gateway-name) GATEWAY_NAME="$2"; shift 2 ;;
    --region) GATEWAY_REGION="$2"; shift 2 ;;
    --demo-mode) DEMO_MODE="true"; shift ;;
    --cleanup) ACTION="cleanup"; shift ;;
    --help|-h)
      echo "Usage: $0 --s3ap-alias <alias> [--stack-name <name>] [--demo-mode]"
      echo "       $0 --cleanup --stack-name <name>"
      exit 0
      ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

log() { echo "[$(date '+%H:%M:%S')] $*"; }
die() { echo "[ERROR] $*" >&2; exit 1; }

TEMPLATE_DIR="$(cd "$(dirname "$0")/../solutions/genai/stepfunctions-agentcore-tools" && pwd)"
TEMPLATE_FILE="$TEMPLATE_DIR/template.yaml"
[[ -f "$TEMPLATE_FILE" ]] || die "Template not found: $TEMPLATE_FILE"

# errexit does not fire inside $( ), so check the assignment explicitly. An expired
# SSO token here should stop with a clear message, not an empty value that surfaces
# as a confusing failure in a later AWS call.
if ! ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>&1); then
  die "AWS credentials are not usable (got: $ACCOUNT_ID). Run 'aws sso login' and retry."
fi

# =============================================================================
# CLEANUP — one stack delete removes everything, gateway and target included.
# =============================================================================
if [[ "$ACTION" == "cleanup" ]]; then
  log "Deleting stack: $STACK_NAME"
  aws cloudformation delete-stack --stack-name "$STACK_NAME" --region "$GATEWAY_REGION"
  aws cloudformation wait stack-delete-complete --stack-name "$STACK_NAME" --region "$GATEWAY_REGION"
  log "Cleanup complete."
  exit 0
fi

# =============================================================================
# DEPLOY
# =============================================================================
[[ -n "$S3AP_ALIAS" ]] || die "Specify --s3ap-alias"

log "=== Step Functions x AgentCore Gateway deployment ==="
log "  Account: $ACCOUNT_ID  Region: $GATEWAY_REGION  Stack: $STACK_NAME"

# --- Build and deploy (gateway + target are in the template) ---
log "Building..."
sam build --template-file "$TEMPLATE_FILE" >/dev/null
log "Deploying (creates Lambdas, state machine, Gateway, connector target)..."
sam deploy \
  --template-file "$TEMPLATE_FILE" \
  --stack-name "$STACK_NAME" \
  --region "$GATEWAY_REGION" \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3 \
  --no-fail-on-empty-changeset \
  --parameter-overrides \
    "S3AccessPointAlias=$S3AP_ALIAS" \
    "DemoMode=$DEMO_MODE" \
    "GatewayName=$GATEWAY_NAME"

# --- Read the gateway URL from the stack output ---
GATEWAY_URL=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$GATEWAY_REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='GatewayUrl'].OutputValue" --output text)
[[ -n "$GATEWAY_URL" && "$GATEWAY_URL" != "None" ]] || die "Could not read GatewayUrl from stack"

# --- Verify tools/list ---
log "Verifying tools/list at $GATEWAY_URL ..."
TOOLS=$(curl -s -X POST "$GATEWAY_URL" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":"1"}' 2>/dev/null || echo '{}')
if echo "$TOOLS" | grep -q "___StartExecution"; then
  log "  Verified: StartExecution tool is present."
else
  log "  tools/list did not show StartExecution (gateway may require auth to list)."
fi

log ""
log "============================================================"
log "  DEPLOYMENT COMPLETE"
log "  Gateway URL: $GATEWAY_URL"
log "  Tools: workflow___StartExecution / ___ListExecutions /"
log "         ___DescribeStateMachine / ___DescribeExecution / ___GetExecutionHistory"
log ""
log "  CLEANUP: $0 --cleanup --stack-name $STACK_NAME"
log "============================================================"
