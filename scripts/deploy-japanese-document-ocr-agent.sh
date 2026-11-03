#!/usr/bin/env bash
# =============================================================================
# deploy-japanese-document-ocr-agent.sh
#
# Deploy the Japanese document OCR x AgentCore pattern. The whole pattern is declarative
# CloudFormation, including the AgentCore Gateway and the Step Functions connector target
# (AWS::BedrockAgentCore::Gateway / ::GatewayTarget), so this script is a thin wrapper around
# `sam build` + `sam package` + `aws cloudformation deploy` that then verifies the gateway's tools/list.
#
# Why not `sam deploy`: found on a live deploy (2026-11-03), `sam deploy --parameter-overrides` cuts a JSON
# value at its first `{` (the stack parameter became the single character `{`), with or without
# Japanese text. `aws cloudformation deploy` keeps the JSON, so the template is packaged by SAM and
# deployed by CloudFormation.
#
# Prerequisites:
#   - AWS CLI v2 configured (SSO login current), SAM CLI, python3, curl
#   - An FSx for ONTAP S3 Access Point (Internet network origin), or a regular bucket for DemoMode
#   - Amazon Textract available in the Region (ap-northeast-1 since 2026-11-02)
#
# Usage:
#   ./scripts/deploy-japanese-document-ocr-agent.sh --s3ap-alias my-ap-xxxxx-ext-s3alias
#   ./scripts/deploy-japanese-document-ocr-agent.sh --s3ap-alias my-bucket --demo-mode
#   ./scripts/deploy-japanese-document-ocr-agent.sh --s3ap-alias my-ap --auth iam \
#       --collections-file collections.json --enable-field-extraction
#   ./scripts/deploy-japanese-document-ocr-agent.sh --cleanup --stack-name ja-ocr-agent [--delete-results]
#
# Reference:
#   solutions/genai/japanese-document-ocr-agent/docs/demo-guide.md
# =============================================================================
set -euo pipefail

# --- Defaults ---
REGION="${AGENTCORE_REGION:-ap-northeast-1}"
STACK_NAME="ja-ocr-agent"
S3AP_ALIAS=""
GATEWAY_NAME="ja-ocr-agent-gateway"
ACTION="deploy"
DEMO_MODE="false"
AUTH="none"
COLLECTIONS_FILE=""
FIELD_EXTRACTION="false"
DELETE_RESULTS="false"

usage() {
  cat <<'EOF'
Usage: deploy-japanese-document-ocr-agent.sh --s3ap-alias <alias> [options]
       deploy-japanese-document-ocr-agent.sh --cleanup --stack-name <name> [--delete-results]

Options:
  --s3ap-alias <alias>        S3 Access Point alias (or a bucket name with --demo-mode)
  --stack-name <name>         CloudFormation stack name (default: ja-ocr-agent)
  --gateway-name <name>       AgentCore Gateway name (default: ja-ocr-agent-gateway)
  --region <region>           Region (default: ap-northeast-1, or $AGENTCORE_REGION)
  --demo-mode                 The alias is a regular bucket (no FSx for ONTAP needed)
  --auth none|iam             Gateway inbound authorization (default: none; none is for a PoC only)
  --collections-file <file>   JSON allow-list of collections (see the README)
  --enable-field-extraction   Turn on Bedrock field extraction
  --cleanup                   Empty the staging bucket and delete the stack
  --delete-results            With --cleanup: also empty and delete the retained results bucket
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --s3ap-alias) S3AP_ALIAS="$2"; shift 2 ;;
    --stack-name) STACK_NAME="$2"; shift 2 ;;
    --gateway-name) GATEWAY_NAME="$2"; shift 2 ;;
    --region) REGION="$2"; shift 2 ;;
    --demo-mode) DEMO_MODE="true"; shift ;;
    --auth) AUTH="$2"; shift 2 ;;
    --collections-file) COLLECTIONS_FILE="$2"; shift 2 ;;
    --enable-field-extraction) FIELD_EXTRACTION="true"; shift ;;
    --cleanup) ACTION="cleanup"; shift ;;
    --delete-results) DELETE_RESULTS="true"; shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage >&2; exit 1 ;;
  esac
done

log() { echo "[$(date '+%H:%M:%S')] $*"; }
die() { echo "[ERROR] $*" >&2; exit 1; }

case "$AUTH" in
  none) AUTHORIZER="NONE" ;;
  iam) AUTHORIZER="AWS_IAM" ;;
  *) die "--auth must be none or iam" ;;
esac

PATTERN_DIR="$(cd "$(dirname "$0")/../solutions/genai/japanese-document-ocr-agent" && pwd)"
TEMPLATE_FILE="$PATTERN_DIR/template.yaml"
[[ -f "$TEMPLATE_FILE" ]] || die "Template not found: $TEMPLATE_FILE"

# errexit does not fire inside $( ), so check the assignment explicitly. An expired SSO token
# here should stop with a clear message, not an empty value that surfaces as a confusing
# failure in a later AWS call.
if ! ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>&1); then
  die "AWS credentials are not usable (got: $ACCOUNT_ID). Run 'aws sso login' and retry."
fi

stack_output() {
  aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text
}

# Empty a bucket (the stack cannot delete a bucket that holds objects). No versioning is enabled.
empty_bucket() {
  local bucket="$1"
  [[ -n "$bucket" && "$bucket" != "None" ]] || return 0
  if aws s3api head-bucket --bucket "$bucket" --region "$REGION" 2>/dev/null; then
    log "Emptying s3://$bucket"
    aws s3 rm "s3://$bucket" --recursive --region "$REGION" --only-show-errors
  fi
}

# =============================================================================
# CLEANUP — one stack delete removes the Gateway and the connector target too.
# The staging bucket must be empty first. The results bucket is retained by design.
# =============================================================================
if [[ "$ACTION" == "cleanup" ]]; then
  STAGING="" ; RESULTS=""
  if aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" >/dev/null 2>&1; then
    STAGING=$(stack_output StagingBucketName)
    RESULTS=$(stack_output ResultsBucketName)
  else
    log "Stack $STACK_NAME does not exist; nothing to delete."
  fi
  empty_bucket "$STAGING"
  if [[ "$DELETE_RESULTS" == "true" ]]; then empty_bucket "$RESULTS"; fi
  log "Deleting stack: $STACK_NAME"
  aws cloudformation delete-stack --stack-name "$STACK_NAME" --region "$REGION"
  aws cloudformation wait stack-delete-complete --stack-name "$STACK_NAME" --region "$REGION"
  if [[ "$DELETE_RESULTS" == "true" && -n "$RESULTS" && "$RESULTS" != "None" ]]; then
    log "Deleting the retained results bucket s3://$RESULTS"
    aws s3api delete-bucket --bucket "$RESULTS" --region "$REGION"
  elif [[ -n "$RESULTS" && "$RESULTS" != "None" ]]; then
    log "The results bucket s3://$RESULTS is retained. Delete it with --cleanup --delete-results."
  fi
  log "Cleanup complete."
  exit 0
fi

# =============================================================================
# DEPLOY
# =============================================================================
[[ -n "$S3AP_ALIAS" ]] || die "Specify --s3ap-alias"

PARAMS=(
  "S3AccessPointAlias=$S3AP_ALIAS"
  "DemoMode=$DEMO_MODE"
  "GatewayName=$GATEWAY_NAME"
  "GatewayAuthorizerType=$AUTHORIZER"
  "EnableFieldExtraction=$FIELD_EXTRACTION"
)
if [[ -n "$COLLECTIONS_FILE" ]]; then
  [[ -f "$COLLECTIONS_FILE" ]] || die "Collections file not found: $COLLECTIONS_FILE"
  # Re-encode as compact ASCII JSON so the value survives CloudFormation; this also validates
  # that the file is JSON before anything is deployed.
  if ! COLLECTIONS_COMPACT=$(python3 -c '
import json, sys
try:
    data = json.load(open(sys.argv[1], encoding="utf-8"))
except ValueError as e:
    sys.exit(f"{type(e).__name__}: {e}")
# ensure_ascii=True: CloudFormation replaces every non-ASCII character in a parameter value with `?`
# (seen on a live check, even for a UTF-8 value sent through the API). json.loads in the Lambda
# turns the \uXXXX escapes back into the original Japanese text.
print(json.dumps(data, ensure_ascii=True, separators=(",", ":")))' "$COLLECTIONS_FILE" 2>&1); then
    die "Collections file is not valid JSON: $COLLECTIONS_COMPACT"
  fi
  PARAMS+=("CollectionsJson=$COLLECTIONS_COMPACT")
fi

log "=== Japanese document OCR x AgentCore deployment ==="
log "  Account: $ACCOUNT_ID  Region: $REGION  Stack: $STACK_NAME  Auth: $AUTHORIZER"

# Package the BUILT template (.aws-sam/build/template.yaml), not the source. The source SharedLayer
# ContentUri is ../../../ (the repository root); packaging it directly uploads the whole repo
# (.venv, .hypothesis, ...), about 1.4 GB. `sam build` rewrites ContentUri to the pruned artifact,
# so packaging must consume the build output.
log "Building..."
(cd "$PATTERN_DIR" && sam build >/dev/null)
PACKAGED="$PATTERN_DIR/.aws-sam/packaged.yaml"
log "Packaging (uploads the Lambda code and the shared layer to the SAM-managed bucket)..."
(cd "$PATTERN_DIR" && sam package \
  --template-file .aws-sam/build/template.yaml \
  --output-template-file .aws-sam/packaged.yaml \
  --region "$REGION" \
  --resolve-s3 >/dev/null)
log "Deploying (Lambda functions, state machine, buckets, Gateway, connector target)..."
aws cloudformation deploy \
  --template-file "$PACKAGED" \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --capabilities CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset \
  --parameter-overrides "${PARAMS[@]}"

# --- Verify that the allow-list reached the stack unchanged. A deploy that "succeeds" with a mangled
# CollectionsJson (a parameter cut at "{", or Japanese turned into "?") leaves the discovery function
# failing on every run, so a mismatch is an error here, not a warning.
if [[ -n "$COLLECTIONS_FILE" ]]; then
  STORED=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" \
    --query "Stacks[0].Parameters[?ParameterKey=='CollectionsJson'].ParameterValue" --output json)
  if ! python3 -c '
import json, sys
stored = json.loads(sys.argv[1])[0]
expected = json.load(open(sys.argv[2], encoding="utf-8"))
try:
    actual = json.loads(stored)
except ValueError:
    sys.exit(f"stored value is not JSON: {stored[:60]!r}")
if actual != expected:
    sys.exit("stored value differs from the file (non-ASCII characters replaced by ?, or truncated)")
' "$STORED" "$COLLECTIONS_FILE"; then
    die "CollectionsJson did not reach the stack unchanged. Fix this before using the pattern."
  fi
  log "  Verified: CollectionsJson reached the stack unchanged."
fi

GATEWAY_URL=$(stack_output GatewayUrl)
[[ -n "$GATEWAY_URL" && "$GATEWAY_URL" != "None" ]] || die "Could not read GatewayUrl from the stack"

# --- Verify tools/list ---
log "Verifying tools/list at $GATEWAY_URL ..."
if [[ "$AUTHORIZER" == "NONE" ]]; then
  TOOLS=$(curl -s -X POST "$GATEWAY_URL" -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","method":"tools/list","id":"1"}' 2>/dev/null || echo '{}')
else
  # AWS_IAM: sign with SigV4 (service name bedrock-agentcore). Export short-lived credentials from
  # the CLI session; they are used for this one call and not written anywhere.
  if ! CREDS=$(aws configure export-credentials --format process 2>&1); then
    die "Could not export credentials for SigV4 signing: $CREDS"
  fi
  AK=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["AccessKeyId"])' "$CREDS")
  SK=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["SecretAccessKey"])' "$CREDS")
  ST=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1]).get("SessionToken",""))' "$CREDS")
  TOOLS=$(curl -s -X POST "$GATEWAY_URL" --aws-sigv4 "aws:amz:$REGION:bedrock-agentcore" \
    --user "$AK:$SK" -H "x-amz-security-token: $ST" -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","method":"tools/list","id":"1"}' 2>/dev/null || echo '{}')
fi
if echo "$TOOLS" | grep -q "___StartExecution"; then
  log "  Verified: the ocr___StartExecution tool is present."
else
  log "  tools/list did not show StartExecution. Response: $(echo "$TOOLS" | head -c 300)"
fi

log ""
log "============================================================"
log "  DEPLOYMENT COMPLETE"
log "  Gateway URL: $GATEWAY_URL"
log "  Tools: ocr___StartExecution / ___ListExecutions / ___DescribeStateMachine /"
log "         ___DescribeExecution / ___GetExecutionHistory"
log "  Results bucket: $(stack_output ResultsBucketName)"
if [[ "$AUTHORIZER" == "NONE" ]]; then
  log "  NOTE: authorization is NONE. Anyone with the URL can start OCR runs. PoC only."
fi
log ""
log "  CLEANUP: $0 --cleanup --stack-name $STACK_NAME [--delete-results]"
log "============================================================"
