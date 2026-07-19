#!/usr/bin/env bash
# =============================================================================
# deploy-agentcore-mcp.sh
#
# One-click deployment: AgentCore MCP Gateway + Lambda for FSx for ONTAP S3 AP
#
# What it does:
#   1. Deploy CloudFormation stack (Lambda + IAM roles)
#   2. Create AgentCore Gateway (NONE auth for PoC)
#   3. Register Lambda as Gateway target with tool schema
#   4. Verify tools/list returns 3 tools
#   5. Generate Quick Desktop MCP config JSON
#
# Prerequisites:
#   - AWS CLI v2.35+ configured
#   - FSx for ONTAP S3 AP created and accessible
#   - jq installed
#
# Usage:
#   # Deploy with parameters
#   ./scripts/deploy-agentcore-mcp.sh \
#     --s3ap-alias my-ap-xxxxx-ext-s3alias \
#     --s3ap-name my-ap-name \
#     --stack-name agentcore-mcp-eda
#
#   # Deploy from existing stack (retrieve Lambda ARN + Role ARN)
#   ./scripts/deploy-agentcore-mcp.sh --from-stack agentcore-mcp-eda
#
#   # Cleanup
#   ./scripts/deploy-agentcore-mcp.sh --cleanup --stack-name agentcore-mcp-eda
#
# Output:
#   - CloudFormation stack in GATEWAY_REGION
#   - AgentCore Gateway (NONE auth) in GATEWAY_REGION
#   - Quick Desktop config at .private/mcp-agentcore-quick.json
#
# Workshop reference:
#   https://catalog.us-east-1.prod.workshops.aws/workshops/
#   9cd82e0b-8348-456b-932a-818b9e5825a1/en-US/09-agentcore
# =============================================================================
set -euo pipefail

# --- Defaults ---
GATEWAY_REGION="${AGENTCORE_REGION:-us-east-1}"
STACK_NAME="agentcore-mcp-eda"
S3AP_ALIAS=""
S3AP_NAME=""
GATEWAY_NAME="eda-mcp-gateway"
ACTION="deploy"
FROM_STACK=""

# --- Parse arguments ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    --s3ap-alias) S3AP_ALIAS="$2"; shift 2 ;;
    --s3ap-name) S3AP_NAME="$2"; shift 2 ;;
    --stack-name) STACK_NAME="$2"; shift 2 ;;
    --gateway-name) GATEWAY_NAME="$2"; shift 2 ;;
    --region) GATEWAY_REGION="$2"; shift 2 ;;
    --from-stack) FROM_STACK="$2"; ACTION="from-stack"; shift 2 ;;
    --cleanup) ACTION="cleanup"; shift ;;
    --help|-h)
      echo "Usage: $0 --s3ap-alias <alias> [--s3ap-name <name>] [--stack-name <name>]"
      echo "       $0 --from-stack <stack-name>"
      echo "       $0 --cleanup --stack-name <name>"
      exit 0
      ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

# --- Helper functions ---
log() { echo "[$(date '+%H:%M:%S')] $*"; }
die() { echo "[ERROR] $*" >&2; exit 1; }

# =============================================================================
# CLEANUP
# =============================================================================
if [[ "$ACTION" == "cleanup" ]]; then
  log "=== Cleanup mode ==="
  ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

  # Find and delete gateway
  log "Looking for gateway with name prefix: ${GATEWAY_NAME}..."
  GATEWAY_ID=$(aws bedrock-agentcore-control list-gateways --region "$GATEWAY_REGION" \
    --query "items[?starts_with(name,'${GATEWAY_NAME}')].gatewayId" --output text 2>/dev/null || echo "")

  if [[ -n "$GATEWAY_ID" && "$GATEWAY_ID" != "None" ]]; then
    log "Deleting gateway targets..."
    TARGETS=$(aws bedrock-agentcore-control list-gateway-targets \
      --gateway-identifier "$GATEWAY_ID" --region "$GATEWAY_REGION" \
      --query "items[*].targetId" --output text 2>/dev/null || echo "")
    for TID in $TARGETS; do
      aws bedrock-agentcore-control delete-gateway-target \
        --gateway-identifier "$GATEWAY_ID" --target-identifier "$TID" \
        --region "$GATEWAY_REGION" 2>/dev/null || true
      log "  Deleted target: $TID"
    done
    sleep 5

    log "Deleting gateway: $GATEWAY_ID"
    aws bedrock-agentcore-control delete-gateway \
      --gateway-identifier "$GATEWAY_ID" --region "$GATEWAY_REGION" 2>/dev/null || true
  fi

  # Delete CloudFormation stack
  log "Deleting stack: $STACK_NAME"
  aws cloudformation delete-stack --stack-name "$STACK_NAME" --region "$GATEWAY_REGION" 2>/dev/null || true
  aws cloudformation wait stack-delete-complete --stack-name "$STACK_NAME" --region "$GATEWAY_REGION" 2>/dev/null || true

  log "Cleanup complete."
  exit 0
fi

# =============================================================================
# DEPLOY
# =============================================================================

# --- Step 1: Validate inputs ---
if [[ "$ACTION" == "from-stack" ]]; then
  STACK_NAME="$FROM_STACK"
  log "Retrieving outputs from existing stack: $STACK_NAME"
  S3AP_ALIAS=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$GATEWAY_REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='S3AccessPointAlias'].OutputValue" --output text)
  [[ -z "$S3AP_ALIAS" ]] && die "Could not retrieve S3AccessPointAlias from stack $STACK_NAME"
elif [[ -z "$S3AP_ALIAS" ]]; then
  die "Specify --s3ap-alias or --from-stack"
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
TEMPLATE_DIR="$(cd "$(dirname "$0")/../infrastructure/agentcore-mcp-gateway" && pwd)"
TEMPLATE_FILE="$TEMPLATE_DIR/template.yaml"

[[ -f "$TEMPLATE_FILE" ]] || die "Template not found: $TEMPLATE_FILE"

log "=== AgentCore MCP Gateway Deployment ==="
log "  Account:      $ACCOUNT_ID"
log "  Region:       $GATEWAY_REGION"
log "  Stack:        $STACK_NAME"
log "  S3 AP Alias:  $S3AP_ALIAS"
log "  S3 AP Name:   ${S3AP_NAME:-'(not set)'}"
log "  Gateway Name: $GATEWAY_NAME"
log ""

# --- Step 2: Deploy CloudFormation ---
if [[ "$ACTION" != "from-stack" ]]; then
  log "Step 1/5: Deploying CloudFormation stack..."
  PARAMS="ParameterKey=S3AccessPointAlias,ParameterValue=$S3AP_ALIAS"
  PARAMS="$PARAMS ParameterKey=GatewayName,ParameterValue=$GATEWAY_NAME"
  [[ -n "$S3AP_NAME" ]] && PARAMS="$PARAMS ParameterKey=S3AccessPointName,ParameterValue=$S3AP_NAME"

  aws cloudformation deploy \
    --template-file "$TEMPLATE_FILE" \
    --stack-name "$STACK_NAME" \
    --parameter-overrides $PARAMS \
    --capabilities CAPABILITY_NAMED_IAM \
    --region "$GATEWAY_REGION" \
    --no-fail-on-empty-changeset

  log "  Stack deployed successfully."
fi

# --- Step 3: Get stack outputs ---
log "Step 2/5: Retrieving stack outputs..."
LAMBDA_ARN=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$GATEWAY_REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='McpToolsFunctionArn'].OutputValue" --output text)
ROLE_ARN=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$GATEWAY_REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='GatewayServiceRoleArn'].OutputValue" --output text)

log "  Lambda ARN: $LAMBDA_ARN"
log "  Role ARN:   $ROLE_ARN"

# --- Step 4: Create AgentCore Gateway ---
log "Step 3/5: Creating AgentCore Gateway (NONE auth)..."

# Check if gateway already exists
EXISTING_GW=$(aws bedrock-agentcore-control list-gateways --region "$GATEWAY_REGION" \
  --query "items[?name=='${GATEWAY_NAME}'].gatewayId" --output text 2>/dev/null || echo "")

if [[ -n "$EXISTING_GW" && "$EXISTING_GW" != "None" ]]; then
  GATEWAY_ID="$EXISTING_GW"
  log "  Gateway already exists: $GATEWAY_ID"
else
  GW_RESPONSE=$(aws bedrock-agentcore-control create-gateway \
    --name "$GATEWAY_NAME" \
    --protocol-type MCP \
    --authorizer-type NONE \
    --role-arn "$ROLE_ARN" \
    --region "$GATEWAY_REGION" \
    --output json)

  GATEWAY_ID=$(echo "$GW_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['gatewayId'])")
  log "  Gateway created: $GATEWAY_ID"

  # Wait for READY
  log "  Waiting for gateway to be READY..."
  for i in {1..30}; do
    STATUS=$(aws bedrock-agentcore-control get-gateway --gateway-identifier "$GATEWAY_ID" \
      --region "$GATEWAY_REGION" --query 'status' --output text 2>/dev/null || echo "CREATING")
    [[ "$STATUS" == "READY" ]] && break
    sleep 5
  done
  [[ "$STATUS" != "READY" ]] && die "Gateway did not become READY (status: $STATUS)"
  log "  Gateway READY."
fi

GATEWAY_URL="https://${GATEWAY_ID}.gateway.bedrock-agentcore.${GATEWAY_REGION}.amazonaws.com/mcp"

# --- Step 5: Register Lambda target ---
log "Step 4/5: Registering Lambda target..."

# Check if target already exists
EXISTING_TARGET=$(aws bedrock-agentcore-control list-gateway-targets \
  --gateway-identifier "$GATEWAY_ID" --region "$GATEWAY_REGION" \
  --query "items[?name=='EDA-MCP-Tools'].targetId" --output text 2>/dev/null || echo "")

if [[ -n "$EXISTING_TARGET" && "$EXISTING_TARGET" != "None" ]]; then
  log "  Target already exists: $EXISTING_TARGET"
else
  # Create target config
  TARGET_CONFIG=$(cat <<TARGETJSON
{
  "mcp": {
    "lambda": {
      "lambdaArn": "${LAMBDA_ARN}",
      "toolSchema": {
        "inlinePayload": [
          {
            "name": "list_files",
            "description": "List files and directories at the specified path on FSx for ONTAP via S3 Access Point.",
            "inputSchema": {
              "type": "object",
              "properties": {
                "path": {"type": "string", "description": "Directory path to list"},
                "max_results": {"type": "integer", "description": "Maximum results (default: 100)"},
                "file_extension": {"type": "string", "description": "Filter by extension (e.g., .log)"}
              },
              "required": []
            }
          },
          {
            "name": "read_file",
            "description": "Read the content of a specific file from FSx for ONTAP via S3 Access Point.",
            "inputSchema": {
              "type": "object",
              "properties": {
                "path": {"type": "string", "description": "Full path to the file"},
                "max_bytes": {"type": "integer", "description": "Maximum bytes to read (default: 65536)"}
              },
              "required": ["path"]
            }
          },
          {
            "name": "search_files",
            "description": "Search for files matching a regex pattern on FSx for ONTAP via S3 Access Point.",
            "inputSchema": {
              "type": "object",
              "properties": {
                "pattern": {"type": "string", "description": "Regex pattern to match file paths"},
                "path": {"type": "string", "description": "Directory to search within"},
                "include_content_preview": {"type": "boolean", "description": "Include first 1KB preview"},
                "max_results": {"type": "integer", "description": "Max results (default: 20)"}
              },
              "required": ["pattern"]
            }
          }
        ]
      }
    }
  }
}
TARGETJSON
)

  echo "$TARGET_CONFIG" > /tmp/agentcore-target-config-deploy.json

  aws bedrock-agentcore-control create-gateway-target \
    --gateway-identifier "$GATEWAY_ID" \
    --name "EDA-MCP-Tools" \
    --description "FSx for ONTAP S3 AP: list, read, search EDA logs" \
    --target-configuration "file:///tmp/agentcore-target-config-deploy.json" \
    --credential-provider-configurations '[{"credentialProviderType":"GATEWAY_IAM_ROLE"}]' \
    --region "$GATEWAY_REGION" > /dev/null

  # Wait for target READY
  sleep 10
  log "  Target registered."
fi

# --- Step 6: Verify ---
log "Step 5/5: Verifying tools/list..."
TOOLS_RESPONSE=$(curl -s -X POST "$GATEWAY_URL" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":"1"}' 2>/dev/null || echo '{"error":"curl failed"}')

TOOL_COUNT=$(echo "$TOOLS_RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(len(data.get('result', {}).get('tools', [])))
except:
    print(0)
" 2>/dev/null || echo "0")

if [[ "$TOOL_COUNT" -ge 3 ]]; then
  log "  ✅ Verified: $TOOL_COUNT tools available"
else
  log "  ⚠️  tools/list returned $TOOL_COUNT tools (expected 3). Gateway may need auth for verification."
fi

# --- Step 7: Generate Quick Desktop config ---
QUICK_CONFIG_PATH="$(cd "$(dirname "$0")/.." && pwd)/.private/mcp-agentcore-quick.json"
cat > "$QUICK_CONFIG_PATH" <<QUICKJSON
{
  "mcpServers": {
    "EDA Log Analyzer": {
      "command": "npx",
      "args": ["-y", "mcp-remote@latest", "${GATEWAY_URL}"],
      "env": {},
      "disabled": false
    }
  }
}
QUICKJSON

log ""
log "============================================================"
log "  DEPLOYMENT COMPLETE"
log "============================================================"
log ""
log "  Gateway ID:   $GATEWAY_ID"
log "  Gateway URL:  $GATEWAY_URL"
log "  Lambda:       $LAMBDA_ARN"
log "  Tools:        list_files, read_file, search_files"
log ""
log "  Quick Desktop Config: $QUICK_CONFIG_PATH"
log ""
log "  NEXT STEPS:"
log "    1. Open Quick Desktop → Settings → Capabilities → Connectors"
log "    2. + Create → MCP server → Import"
log "    3. Config file path: $QUICK_CONFIG_PATH"
log "    4. Load file → Import 1 server → Add server"
log "    5. Chat: 「eda-regression/simulation/ のファイルを一覧表示して」"
log ""
log "  CLEANUP:"
log "    $0 --cleanup --stack-name $STACK_NAME"
log "============================================================"
