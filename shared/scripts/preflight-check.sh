#!/usr/bin/env bash
# =============================================================================
# preflight-check.sh — Pre-deployment environment validation
#
# Validates that the target AWS environment meets requirements before deploying
# FSx for ONTAP S3 Access Points serverless pattern stacks.
#
# Usage:
#   ./shared/scripts/preflight-check.sh [--profile PROFILE] [--vpc VPC_ID]
#                                        [--region REGION] [--verbose]
#
# Profiles:
#   quick-start   — Minimal checks (CLI tools, credentials, region)
#   production    — Full checks (VPC EP, ONTAP S3 server, SG egress, secrets)
#   demo          — DemoMode checks (CLI tools, credentials, S3 bucket access)
#   fpolicy       — FPolicy-specific checks (ECR image, SG inbound, SVM UUID)
#
# Exit Codes:
#   0   — All checks passed
#   2   — Usage error (invalid arguments)
#   75  — Required tool not installed
#   78  — Configuration error (environment not ready for deployment)
#
# Environment Variables:
#   PREFLIGHT_SKIP          — Comma-separated check names to skip
#                             (e.g., "vpc_endpoints,ontap_s3_server")
#   AWS_REGION              — Override default region detection
#   AWS_PROFILE             — AWS CLI profile to use
#   ONTAP_MGMT_IP          — ONTAP management IP for API checks
#   ONTAP_SECRET_NAME       — Secrets Manager secret name for ONTAP credentials
#   VPC_ID                  — Target VPC ID (overrides --vpc flag)
# =============================================================================
set -euo pipefail

# --- Constants ---------------------------------------------------------------
readonly VERSION="1.0.0"
readonly SCRIPT_NAME="$(basename "$0")"
readonly EXIT_OK=0
readonly EXIT_USAGE=2
readonly EXIT_TOOL_MISSING=75
readonly EXIT_CONFIG_ERROR=78

# --- Colors (disabled if not a terminal) -------------------------------------
if [[ -t 1 ]]; then
  readonly RED='\033[0;31m'
  readonly GREEN='\033[0;32m'
  readonly YELLOW='\033[0;33m'
  readonly BLUE='\033[0;34m'
  readonly NC='\033[0m'
else
  readonly RED='' GREEN='' YELLOW='' BLUE='' NC=''
fi

# --- Globals -----------------------------------------------------------------
PROFILE="quick-start"
REGION=""
VERBOSE=false
WARNINGS=0
ERRORS=0
SKIPPED_CHECKS=""
TARGET_VPC=""

# --- Helpers -----------------------------------------------------------------
info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()      { echo -e "${GREEN}[PASS]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; WARNINGS=$((WARNINGS + 1)); }
fail()    { echo -e "${RED}[FAIL]${NC}  $*"; ERRORS=$((ERRORS + 1)); }
verbose() { [[ "$VERBOSE" == "true" ]] && echo -e "${BLUE}[DBG]${NC}   $*" || true; }

usage() {
  cat <<EOF
Usage: $SCRIPT_NAME [OPTIONS]

Pre-deployment environment validation for FSx for ONTAP S3AP serverless patterns.

Options:
  --profile PROFILE   Check profile: quick-start|production|demo|fpolicy (default: quick-start)
  --vpc VPC_ID        Target VPC ID for endpoint conflict checks
  --region REGION     AWS region (default: auto-detect from CLI config)
  --verbose           Show detailed output
  --version           Show version
  -h, --help          Show this help

Environment:
  PREFLIGHT_SKIP      Comma-separated checks to skip (e.g., "vpc_endpoints,ontap_s3_server")

Exit Codes:
  0   All checks passed
  2   Usage error
  75  Required tool missing
  78  Configuration error

Examples:
  $SCRIPT_NAME --profile quick-start
  $SCRIPT_NAME --profile production --vpc vpc-0123456789abcdef0
  PREFLIGHT_SKIP=vpc_endpoints $SCRIPT_NAME --profile production
EOF
}

is_skipped() {
  local check_name="$1"
  [[ ",$SKIPPED_CHECKS," == *",$check_name,"* ]]
}

# --- Argument Parsing --------------------------------------------------------
parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --profile)
        PROFILE="${2:-}"
        [[ -z "$PROFILE" ]] && { echo "Error: --profile requires a value" >&2; exit $EXIT_USAGE; }
        shift 2
        ;;
      --vpc)
        TARGET_VPC="${2:-}"
        [[ -z "$TARGET_VPC" ]] && { echo "Error: --vpc requires a value" >&2; exit $EXIT_USAGE; }
        shift 2
        ;;
      --region)
        REGION="${2:-}"
        [[ -z "$REGION" ]] && { echo "Error: --region requires a value" >&2; exit $EXIT_USAGE; }
        shift 2
        ;;
      --verbose)
        VERBOSE=true
        shift
        ;;
      --version)
        echo "$SCRIPT_NAME v$VERSION"
        exit $EXIT_OK
        ;;
      -h|--help)
        usage
        exit $EXIT_OK
        ;;
      *)
        echo "Error: Unknown option: $1" >&2
        usage >&2
        exit $EXIT_USAGE
        ;;
    esac
  done

  # Validate profile
  case "$PROFILE" in
    quick-start|production|demo|fpolicy) ;;
    *)
      echo "Error: Invalid profile '$PROFILE'. Must be: quick-start|production|demo|fpolicy" >&2
      exit $EXIT_USAGE
      ;;
  esac

  # Environment overrides
  [[ -n "${VPC_ID:-}" ]] && TARGET_VPC="$VPC_ID"
  SKIPPED_CHECKS="${PREFLIGHT_SKIP:-}"
}

# =============================================================================
# CHECK FUNCTIONS
# =============================================================================

check_cli_tools() {
  if is_skipped "cli_tools"; then
    info "Skipped: cli_tools"
    return
  fi

  info "Checking required CLI tools..."

  # AWS CLI
  if command -v aws &>/dev/null; then
    local aws_version
    aws_version=$(aws --version 2>&1 | head -1)
    ok "AWS CLI: $aws_version"
  else
    fail "AWS CLI not found. Install: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
    return
  fi

  # SAM CLI (optional for DemoMode)
  if command -v sam &>/dev/null; then
    local sam_version
    sam_version=$(sam --version 2>&1)
    ok "SAM CLI: $sam_version"
  else
    if [[ "$PROFILE" == "demo" ]]; then
      warn "SAM CLI not found (optional for demo profile). Install: https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html"
    else
      fail "SAM CLI not found. Install: https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html"
    fi
  fi

  # Python
  if command -v python3 &>/dev/null; then
    local py_version
    py_version=$(python3 --version 2>&1)
    ok "Python: $py_version"
    # Check Python version >= 3.12
    local py_minor
    py_minor=$(python3 -c "import sys; print(sys.version_info.minor)" 2>/dev/null || echo "0")
    if [[ "$py_minor" -lt 12 ]]; then
      warn "Python 3.12+ recommended (Lambda runtime target). Found: $py_version"
    fi
  else
    fail "Python 3 not found"
  fi

  # jq (used in many verification commands)
  if command -v jq &>/dev/null; then
    ok "jq: $(jq --version 2>&1)"
  else
    warn "jq not found (recommended for output parsing). Install: brew install jq"
  fi

  # Docker (required for FPolicy)
  if [[ "$PROFILE" == "fpolicy" ]]; then
    if command -v docker &>/dev/null; then
      ok "Docker: $(docker --version 2>&1)"
    else
      fail "Docker not found (required for FPolicy container build)"
    fi
  fi
}

check_aws_credentials() {
  if is_skipped "aws_credentials"; then
    info "Skipped: aws_credentials"
    return
  fi

  info "Checking AWS credentials..."

  local identity
  if identity=$(aws sts get-caller-identity 2>&1); then
    local account_id arn
    account_id=$(echo "$identity" | jq -r '.Account // "unknown"' 2>/dev/null || echo "unknown")
    arn=$(echo "$identity" | jq -r '.Arn // "unknown"' 2>/dev/null || echo "unknown")
    ok "AWS credentials valid (Account: ${account_id:0:4}...${account_id: -4})"
    verbose "Identity ARN: $arn"
  else
    fail "AWS credentials invalid or expired. Run: aws configure / aws sso login"
    return
  fi

  # Detect region
  if [[ -z "$REGION" ]]; then
    REGION=$(aws configure get region 2>/dev/null || echo "")
    if [[ -z "$REGION" ]]; then
      REGION="${AWS_DEFAULT_REGION:-${AWS_REGION:-}}"
    fi
  fi

  if [[ -n "$REGION" ]]; then
    ok "Region: $REGION"
  else
    fail "Cannot determine AWS region. Set via --region, AWS_REGION, or aws configure"
  fi
}

check_vpc_endpoints() {
  if is_skipped "vpc_endpoints"; then
    info "Skipped: vpc_endpoints"
    return
  fi

  if [[ -z "$TARGET_VPC" ]]; then
    warn "VPC Endpoint check skipped: no --vpc specified (use --vpc vpc-XXXXX)"
    return
  fi

  info "Checking VPC Endpoints in $TARGET_VPC..."

  local existing_eps
  existing_eps=$(aws ec2 describe-vpc-endpoints \
    --filters "Name=vpc-id,Values=$TARGET_VPC" \
    --query "VpcEndpoints[].{Service:ServiceName,State:State,Type:VpcEndpointType}" \
    --region "$REGION" --output json 2>/dev/null || echo "[]")

  if [[ "$existing_eps" == "[]" ]]; then
    info "No existing VPC Endpoints in $TARGET_VPC"
    info "  → Deploy first stack with EnableVpcEndpoints=true, EnableS3GatewayEndpoint=true"
    return
  fi

  local ep_count
  ep_count=$(echo "$existing_eps" | jq 'length')
  info "Found $ep_count existing VPC Endpoint(s)"

  # Check for S3 Gateway
  local s3_gw
  s3_gw=$(echo "$existing_eps" | jq -r '[.[] | select(.Service | endswith(".s3")) | select(.Type=="Gateway")] | length')
  if [[ "$s3_gw" -gt 0 ]]; then
    warn "S3 Gateway Endpoint already exists → Set EnableS3GatewayEndpoint=false in your stack"
  fi

  # Check for Interface Endpoints that would conflict
  local services=("secretsmanager" "sts" "logs" "bedrock-runtime" "athena" "glue")
  for svc in "${services[@]}"; do
    local svc_ep
    svc_ep=$(echo "$existing_eps" | jq -r "[.[] | select(.Service | endswith(\".$svc\")) | select(.Type==\"Interface\")] | length")
    if [[ "$svc_ep" -gt 0 ]]; then
      warn "Interface Endpoint for '$svc' already exists → Set EnableVpcEndpoints=false in your stack"
    fi
  done

  # Summary recommendation
  if [[ "$s3_gw" -gt 0 ]] || echo "$existing_eps" | jq -e '[.[] | select(.Type=="Interface")] | length > 0' &>/dev/null; then
    info "  → Recommendation: Deploy with EnableVpcEndpoints=false, EnableS3GatewayEndpoint=false"
  fi
}

check_ontap_s3_server() {
  if is_skipped "ontap_s3_server"; then
    info "Skipped: ontap_s3_server"
    return
  fi

  local mgmt_ip="${ONTAP_MGMT_IP:-}"
  local secret_name="${ONTAP_SECRET_NAME:-}"

  if [[ -z "$mgmt_ip" ]]; then
    info "ONTAP S3 server check skipped: ONTAP_MGMT_IP not set"
    info "  → Set ONTAP_MGMT_IP to enable this check"
    return
  fi

  if [[ -z "$secret_name" ]]; then
    info "ONTAP S3 server check skipped: ONTAP_SECRET_NAME not set"
    return
  fi

  info "Checking for ONTAP native S3 server on management IP $mgmt_ip..."

  # Retrieve credentials from Secrets Manager
  local creds
  creds=$(aws secretsmanager get-secret-value --secret-id "$secret_name" \
    --query SecretString --output text --region "$REGION" 2>/dev/null || echo "")

  if [[ -z "$creds" ]]; then
    warn "Cannot retrieve ONTAP credentials from Secrets Manager ($secret_name)"
    return
  fi

  local username password
  username=$(echo "$creds" | jq -r '.username // .user // empty' 2>/dev/null || echo "")
  password=$(echo "$creds" | jq -r '.password // .pass // empty' 2>/dev/null || echo "")

  if [[ -z "$username" || -z "$password" ]]; then
    warn "Cannot parse username/password from secret $secret_name"
    return
  fi

  # Query ONTAP REST API for S3 services
  local s3_services
  s3_services=$(curl -sku "$username:$password" \
    "https://$mgmt_ip/api/protocols/s3/services" \
    --connect-timeout 5 --max-time 10 2>/dev/null || echo "")

  if [[ -z "$s3_services" ]]; then
    warn "Cannot connect to ONTAP REST API at $mgmt_ip (timeout or unreachable)"
    info "  → Ensure network connectivity from this host to ONTAP management LIF"
    return
  fi

  local s3_count
  s3_count=$(echo "$s3_services" | jq '.num_records // 0' 2>/dev/null || echo "0")

  if [[ "$s3_count" -gt 0 ]]; then
    fail "ONTAP native S3 server detected on $mgmt_ip ($s3_count SVM(s) with S3 enabled)"
    echo -e "  ${RED}→ S3 Access Point creation will FAIL on SVMs with an active ONTAP S3 server${NC}"
    echo -e "  ${RED}→ Use a different SVM, or disable the ONTAP S3 server first${NC}"
    echo -e "  ${RED}→ See: docs/en/deployment-guide.md#ontap-version-requirements (Known Constraints)${NC}"

    # Show which SVMs are affected
    verbose "Affected SVMs:"
    echo "$s3_services" | jq -r '.records[]? | "    SVM: \(.svm.name) (UUID: \(.svm.uuid))"' 2>/dev/null || true
  else
    ok "No ONTAP native S3 server found — S3 Access Point creation is safe"
  fi
}

check_security_group_egress() {
  if is_skipped "sg_egress"; then
    info "Skipped: sg_egress"
    return
  fi

  if [[ -z "$TARGET_VPC" ]]; then
    info "Security Group egress check skipped: no --vpc specified"
    return
  fi

  info "Checking Lambda Security Group egress rules..."

  # Find security groups in the VPC that might be used by Lambda
  local sgs
  sgs=$(aws ec2 describe-security-groups \
    --filters "Name=vpc-id,Values=$TARGET_VPC" \
    --query "SecurityGroups[?contains(GroupName,'lambda') || contains(GroupName,'Lambda') || contains(GroupName,'fsxn')].[GroupId,GroupName]" \
    --region "$REGION" --output json 2>/dev/null || echo "[]")

  if [[ "$sgs" == "[]" ]]; then
    info "No Lambda/FSxN security groups found in $TARGET_VPC"
    info "  → Security groups will be created during stack deployment"
    return
  fi

  # Check that at least one SG allows HTTPS (443) outbound
  local sg_ids
  sg_ids=$(echo "$sgs" | jq -r '.[][0]' 2>/dev/null || echo "")

  for sg_id in $sg_ids; do
    local egress_443
    egress_443=$(aws ec2 describe-security-groups --group-ids "$sg_id" \
      --query "SecurityGroups[0].IpPermissionsEgress[?ToPort==\`443\` || ToPort==\`-1\`]" \
      --region "$REGION" --output json 2>/dev/null || echo "[]")

    if [[ "$egress_443" != "[]" ]]; then
      ok "SG $sg_id allows HTTPS (443) egress"
    else
      warn "SG $sg_id may not allow HTTPS (443) egress — Lambda needs 443 for AWS API calls"
    fi
  done
}

check_secrets_manager() {
  if is_skipped "secrets_manager"; then
    info "Skipped: secrets_manager"
    return
  fi

  local secret_name="${ONTAP_SECRET_NAME:-}"
  if [[ -z "$secret_name" ]]; then
    if [[ "$PROFILE" == "production" || "$PROFILE" == "fpolicy" ]]; then
      info "Secrets Manager check skipped: ONTAP_SECRET_NAME not set"
      info "  → Set ONTAP_SECRET_NAME to validate credential access"
    fi
    return
  fi

  info "Checking Secrets Manager access for '$secret_name'..."

  local secret_meta
  secret_meta=$(aws secretsmanager describe-secret --secret-id "$secret_name" \
    --region "$REGION" 2>&1 || echo "ERROR")

  if [[ "$secret_meta" == *"ERROR"* ]] || [[ "$secret_meta" == *"ResourceNotFoundException"* ]]; then
    fail "Secret '$secret_name' not found or access denied"
    return
  fi

  local rotation_enabled last_rotated
  rotation_enabled=$(echo "$secret_meta" | jq -r '.RotationEnabled // false' 2>/dev/null || echo "false")
  last_rotated=$(echo "$secret_meta" | jq -r '.LastRotatedDate // "never"' 2>/dev/null || echo "never")

  ok "Secret '$secret_name' accessible"
  verbose "Rotation enabled: $rotation_enabled | Last rotated: $last_rotated"

  if [[ "$rotation_enabled" == "false" ]]; then
    warn "Secret rotation not enabled for '$secret_name' — consider enabling automatic rotation"
  fi
}

check_ecr_image() {
  if is_skipped "ecr_image"; then
    info "Skipped: ecr_image"
    return
  fi

  if [[ "$PROFILE" != "fpolicy" ]]; then
    return
  fi

  info "Checking ECR image availability..."

  local repo_name="fpolicy-server"
  local images
  images=$(aws ecr describe-images --repository-name "$repo_name" \
    --query "imageDetails[0].imageTags" \
    --region "$REGION" --output json 2>&1 || echo "ERROR")

  if [[ "$images" == *"ERROR"* ]] || [[ "$images" == *"RepositoryNotFoundException"* ]]; then
    fail "ECR repository '$repo_name' not found — build and push the FPolicy server image first"
    info "  → See: solutions/event-driven/fpolicy/README.md for container build instructions"
  else
    ok "ECR repository '$repo_name' found with images"
    verbose "Tags: $images"
  fi
}

check_bedrock_access() {
  if is_skipped "bedrock_access"; then
    info "Skipped: bedrock_access"
    return
  fi

  if [[ "$PROFILE" == "demo" ]]; then
    # Still check bedrock for demo mode since patterns use Bedrock
    :
  fi

  info "Checking Bedrock model access..."

  local models
  models=$(aws bedrock list-foundation-models \
    --query "modelSummaries[?contains(modelId,'nova')].modelId" \
    --region "$REGION" --output json 2>&1 || echo "ERROR")

  if [[ "$models" == *"ERROR"* ]] || [[ "$models" == *"AccessDeniedException"* ]]; then
    warn "Cannot list Bedrock models — ensure Bedrock access is enabled in $REGION"
    info "  → Check: AWS Console > Amazon Bedrock > Model access"
    return
  fi

  local nova_count
  nova_count=$(echo "$models" | jq 'length' 2>/dev/null || echo "0")

  if [[ "$nova_count" -gt 0 ]]; then
    ok "Bedrock access confirmed ($nova_count Nova model(s) available)"
  else
    warn "No Nova models found in $REGION — may need to enable model access or use inference profiles"
    info "  → For Asia Pacific: use 'apac.amazon.nova-pro-v1:0' (cross-region inference profile)"
  fi
}

# =============================================================================
# PROFILE RUNNERS
# =============================================================================

run_quick_start() {
  echo ""
  echo "═══════════════════════════════════════════════════════════════════"
  echo "  Preflight Check — Profile: quick-start"
  echo "═══════════════════════════════════════════════════════════════════"
  echo ""
  check_cli_tools
  echo ""
  check_aws_credentials
  echo ""
  check_bedrock_access
}

run_production() {
  echo ""
  echo "═══════════════════════════════════════════════════════════════════"
  echo "  Preflight Check — Profile: production"
  echo "═══════════════════════════════════════════════════════════════════"
  echo ""
  check_cli_tools
  echo ""
  check_aws_credentials
  echo ""
  check_vpc_endpoints
  echo ""
  check_ontap_s3_server
  echo ""
  check_security_group_egress
  echo ""
  check_secrets_manager
  echo ""
  check_bedrock_access
}

run_demo() {
  echo ""
  echo "═══════════════════════════════════════════════════════════════════"
  echo "  Preflight Check — Profile: demo"
  echo "═══════════════════════════════════════════════════════════════════"
  echo ""
  check_cli_tools
  echo ""
  check_aws_credentials
  echo ""
  check_bedrock_access
}

run_fpolicy() {
  echo ""
  echo "═══════════════════════════════════════════════════════════════════"
  echo "  Preflight Check — Profile: fpolicy"
  echo "═══════════════════════════════════════════════════════════════════"
  echo ""
  check_cli_tools
  echo ""
  check_aws_credentials
  echo ""
  check_vpc_endpoints
  echo ""
  check_ontap_s3_server
  echo ""
  check_security_group_egress
  echo ""
  check_secrets_manager
  echo ""
  check_ecr_image
}

# =============================================================================
# MAIN
# =============================================================================

main() {
  parse_args "$@"

  case "$PROFILE" in
    quick-start) run_quick_start ;;
    production)  run_production ;;
    demo)        run_demo ;;
    fpolicy)     run_fpolicy ;;
  esac

  # Summary
  echo ""
  echo "───────────────────────────────────────────────────────────────────"
  if [[ $ERRORS -eq 0 && $WARNINGS -eq 0 ]]; then
    echo -e "  ${GREEN}Result: ALL CHECKS PASSED${NC}"
    echo "  Ready to deploy with profile: $PROFILE"
  elif [[ $ERRORS -eq 0 ]]; then
    echo -e "  ${YELLOW}Result: PASSED with $WARNINGS warning(s)${NC}"
    echo "  Deployment can proceed; review warnings above."
  else
    echo -e "  ${RED}Result: $ERRORS error(s), $WARNINGS warning(s)${NC}"
    echo "  Fix errors before deploying."
  fi
  echo "───────────────────────────────────────────────────────────────────"
  echo ""

  # Exit code
  if [[ $ERRORS -gt 0 ]]; then
    exit $EXIT_CONFIG_ERROR
  fi
  exit $EXIT_OK
}

main "$@"
