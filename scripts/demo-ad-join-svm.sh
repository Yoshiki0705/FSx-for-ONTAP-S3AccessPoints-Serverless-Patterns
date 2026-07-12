#!/usr/bin/env bash
# =============================================================================
# demo-ad-join-svm.sh — Join FSx for ONTAP SVM to Active Directory domain
#
# Joins the specified SVM to AD, enabling WINDOWS-type S3 Access Points.
# Can auto-resolve parameters from the demo-ad-environment CloudFormation stack
# outputs, or accept manual parameters.
#
# Usage:
#   ./scripts/demo-ad-join-svm.sh --stack-name <STACK> [OPTIONS]
#   ./scripts/demo-ad-join-svm.sh --manual [OPTIONS]
#
# Prerequisites:
#   - FSx for ONTAP file system with at least one SVM
#   - Active Directory domain (AWS Managed AD or self-managed)
#   - ONTAP admin credentials in Secrets Manager
#   - Network connectivity: SVM → AD DNS (port 53), AD DC (ports 88, 389, 445)
#
# After SVM AD Join:
#   WINDOWS-type S3 Access Points can be created on volumes in this SVM.
#   IMPORTANT: WindowsUser.Name must NOT include domain prefix.
#     CORRECT:   "Admin"
#     INCORRECT: "DEMO\Admin" (causes AccessDenied on data-plane operations)
#
# Exit Codes:
#   0   — Success (SVM joined to AD)
#   1   — General error
#   2   — Usage error
#   78  — Configuration error (missing parameters or connectivity failure)
# =============================================================================
set -euo pipefail

# --- Constants ---------------------------------------------------------------
readonly SCRIPT_NAME="$(basename "$0")"
readonly EXIT_OK=0
readonly EXIT_ERROR=1
readonly EXIT_USAGE=2
readonly EXIT_CONFIG=78

# --- Colors ------------------------------------------------------------------
if [[ -t 1 ]]; then
  readonly RED='\033[0;31m' GREEN='\033[0;32m' YELLOW='\033[0;33m'
  readonly BLUE='\033[0;34m' NC='\033[0m'
else
  readonly RED='' GREEN='' YELLOW='' BLUE='' NC=''
fi

# --- Globals -----------------------------------------------------------------
STACK_NAME=""
REGION=""
DRY_RUN=false
MANUAL_MODE=false

# Manual parameters
ONTAP_MGMT_IP=""
ONTAP_SECRET=""
SVM_NAME=""
DOMAIN_NAME=""
DOMAIN_USER=""
DOMAIN_PASSWORD=""
DNS_IPS=""
OU=""

# --- Helpers -----------------------------------------------------------------
info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
fail()  { echo -e "${RED}[FAIL]${NC}  $*" >&2; }
die()   { fail "$*"; exit $EXIT_ERROR; }

usage() {
  cat <<EOF
Usage: $SCRIPT_NAME [OPTIONS]

Join an FSx for ONTAP SVM to Active Directory, enabling WINDOWS-type S3 Access Points.

Auto-resolve from CloudFormation stack:
  $SCRIPT_NAME --stack-name demo-ad-env --svm-name svm1

Manual parameters:
  $SCRIPT_NAME --manual --ontap-ip 198.51.100.10 --secret fsxn/admin \\
    --svm-name svm1 --domain demo.fsxn.local --domain-user Admin \\
    --domain-password 'P@ssw0rd' --dns-ips 198.51.100.20,198.51.100.21

Options:
  --stack-name NAME     CloudFormation stack name (demo-ad-environment)
  --manual              Use manual parameters instead of stack outputs
  --svm-name NAME       SVM name to join to AD (required)
  --ontap-ip IP         ONTAP management IP (manual mode)
  --secret NAME         Secrets Manager secret name for ONTAP credentials (manual mode)
  --domain FQDN         AD domain FQDN (manual mode, e.g., demo.fsxn.local)
  --domain-user USER    AD admin username — no domain prefix (manual mode)
  --domain-password PW  AD admin password (manual mode)
  --dns-ips IPS         AD DNS IPs, comma-separated (manual mode)
  --ou OU               Target OU for the SVM computer object (optional)
                        Default: CN=Computers,DC=<domain components>
  --region REGION       AWS region (default: from AWS CLI config)
  --dry-run             Show what would be done without executing
  -h, --help            Show this help

After Successful Join:
  Create a WINDOWS-type S3 Access Point:
    aws fsx create-and-attach-s3-access-point \\
      --file-system-id fs-XXXXXXXXX \\
      --s3-access-point-configuration '{
        "Namespace": "s3ap-win-test",
        "FileSystemUserType": "WINDOWS",
        "WindowsUser": {"Name": "Admin"},
        "NetworkOrigin": "Internet"
      }'

  CRITICAL: WindowsUser.Name must be username only — NO domain prefix.
    CORRECT:   "Admin"
    INCORRECT: "DEMO\\Admin" → AccessDenied on ListObjects/GetObject/PutObject
EOF
}

# --- Argument Parsing --------------------------------------------------------
parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --stack-name)   STACK_NAME="${2:-}"; shift 2 ;;
      --manual)       MANUAL_MODE=true; shift ;;
      --svm-name)     SVM_NAME="${2:-}"; shift 2 ;;
      --ontap-ip)     ONTAP_MGMT_IP="${2:-}"; shift 2 ;;
      --secret)       ONTAP_SECRET="${2:-}"; shift 2 ;;
      --domain)       DOMAIN_NAME="${2:-}"; shift 2 ;;
      --domain-user)  DOMAIN_USER="${2:-}"; shift 2 ;;
      --domain-password) DOMAIN_PASSWORD="${2:-}"; shift 2 ;;
      --dns-ips)      DNS_IPS="${2:-}"; shift 2 ;;
      --ou)           OU="${2:-}"; shift 2 ;;
      --region)       REGION="${2:-}"; shift 2 ;;
      --dry-run)      DRY_RUN=true; shift ;;
      -h|--help)      usage; exit $EXIT_OK ;;
      *) fail "Unknown option: $1"; usage >&2; exit $EXIT_USAGE ;;
    esac
  done

  # Validate
  if [[ -z "$STACK_NAME" && "$MANUAL_MODE" != "true" ]]; then
    fail "Either --stack-name or --manual is required"
    usage >&2
    exit $EXIT_USAGE
  fi

  if [[ -z "$SVM_NAME" ]]; then
    fail "--svm-name is required"
    exit $EXIT_USAGE
  fi

  # Region
  if [[ -z "$REGION" ]]; then
    REGION=$(aws configure get region 2>/dev/null || echo "")
    REGION="${REGION:-${AWS_REGION:-${AWS_DEFAULT_REGION:-}}}"
    [[ -z "$REGION" ]] && die "Cannot determine region. Use --region or set AWS_REGION."
  fi
}

# --- Stack Output Resolution -------------------------------------------------
resolve_from_stack() {
  info "Resolving parameters from stack: $STACK_NAME (region: $REGION)..."

  local outputs
  outputs=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query "Stacks[0].Outputs" \
    --output json 2>&1) || die "Cannot describe stack '$STACK_NAME': $outputs"

  get_output() {
    echo "$outputs" | jq -r ".[] | select(.OutputKey==\"$1\") | .OutputValue // empty" 2>/dev/null || echo ""
  }

  # Resolve ONTAP parameters
  [[ -z "$ONTAP_MGMT_IP" ]] && ONTAP_MGMT_IP=$(get_output "OntapManagementIp")
  [[ -z "$ONTAP_SECRET" ]] && ONTAP_SECRET=$(get_output "OntapSecretName")
  DOMAIN_NAME=$(get_output "DomainName")

  # For create-new mode, get DNS IPs from AD outputs
  local directory_dns
  directory_dns=$(get_output "DnsIpAddresses")
  [[ -z "$DNS_IPS" && -n "$directory_dns" ]] && DNS_IPS="$directory_dns"

  # Resolve domain user/password from secret or parameters
  local ad_mode
  ad_mode=$(get_output "AdMode")

  if [[ "$ad_mode" == "create-new" || "$ad_mode" == "use-existing-managed" ]]; then
    # For AWS Managed AD, the admin user is always "Admin"
    [[ -z "$DOMAIN_USER" ]] && DOMAIN_USER="Admin"
    # Password comes from AdminPassword parameter (not in outputs for security)
    if [[ -z "$DOMAIN_PASSWORD" ]]; then
      warn "AD admin password not available from stack outputs (NoEcho)."
      warn "Provide via --domain-password or enter interactively."
      read -rsp "AD Admin Password: " DOMAIN_PASSWORD
      echo ""
    fi
  fi

  info "Resolved: domain=$DOMAIN_NAME, dns=$DNS_IPS, user=$DOMAIN_USER"
}

# --- ONTAP Credential Retrieval ----------------------------------------------
get_ontap_credentials() {
  if [[ -z "$ONTAP_SECRET" ]]; then
    die "ONTAP secret name not set. Use --secret or ensure stack has OntapSecretName output."
  fi

  info "Retrieving ONTAP credentials from Secrets Manager ($ONTAP_SECRET)..."
  local secret_value
  secret_value=$(aws secretsmanager get-secret-value \
    --secret-id "$ONTAP_SECRET" \
    --region "$REGION" \
    --query SecretString --output text 2>&1) || die "Cannot retrieve secret: $secret_value"

  ONTAP_USER=$(echo "$secret_value" | jq -r '.username // .user // empty')
  ONTAP_PASS=$(echo "$secret_value" | jq -r '.password // .pass // empty')

  [[ -z "$ONTAP_USER" || -z "$ONTAP_PASS" ]] && die "Cannot parse ONTAP credentials from secret"
  ok "ONTAP credentials retrieved (user: $ONTAP_USER)"
}

# --- SVM UUID Resolution -----------------------------------------------------
resolve_svm_uuid() {
  info "Resolving SVM UUID for '$SVM_NAME'..."

  local svm_response
  svm_response=$(curl -sku "$ONTAP_USER:$ONTAP_PASS" \
    "https://$ONTAP_MGMT_IP/api/svm/svms?name=$SVM_NAME&fields=uuid,name,cifs" \
    --connect-timeout 10 --max-time 30 2>/dev/null) || die "Cannot connect to ONTAP API at $ONTAP_MGMT_IP"

  SVM_UUID=$(echo "$svm_response" | jq -r '.records[0].uuid // empty')
  [[ -z "$SVM_UUID" ]] && die "SVM '$SVM_NAME' not found on $ONTAP_MGMT_IP"

  # Check if already AD-joined
  local cifs_enabled
  cifs_enabled=$(echo "$svm_response" | jq -r '.records[0].cifs.enabled // false')
  if [[ "$cifs_enabled" == "true" ]]; then
    warn "SVM '$SVM_NAME' appears to already have CIFS/AD configured."
    warn "Proceeding may update existing AD configuration."
  fi

  ok "SVM UUID: $SVM_UUID"
}

# --- AD Join via ONTAP REST API ----------------------------------------------
join_svm_to_ad() {
  info "Joining SVM '$SVM_NAME' to domain '$DOMAIN_NAME'..."

  # Build the CIFS server create payload
  local payload
  payload=$(jq -n \
    --arg name "$SVM_NAME" \
    --arg domain "$DOMAIN_NAME" \
    --arg user "$DOMAIN_USER" \
    --arg pass "$DOMAIN_PASSWORD" \
    '{
      "name": $name,
      "ad_domain": {
        "fqdn": $domain,
        "user": $user,
        "password": $pass
      }
    }')

  # Add OU if specified
  if [[ -n "$OU" ]]; then
    payload=$(echo "$payload" | jq --arg ou "$OU" '.ad_domain.organizational_unit = $ou')
  fi

  # Add DNS if available (for name resolution during join)
  if [[ -n "$DNS_IPS" ]]; then
    local dns_array
    dns_array=$(echo "$DNS_IPS" | jq -R 'split(",") | map(gsub("\\s";""))')
    # Set DNS on the SVM first
    info "Configuring DNS on SVM (servers: $DNS_IPS)..."
    local dns_payload
    dns_payload=$(jq -n --arg domain "$DOMAIN_NAME" --argjson servers "$dns_array" \
      '{"domains": [$domain], "servers": $servers}')

    if [[ "$DRY_RUN" == "true" ]]; then
      info "[DRY-RUN] Would configure DNS: $dns_payload"
    else
      local dns_result
      dns_result=$(curl -sku "$ONTAP_USER:$ONTAP_PASS" \
        -X POST "https://$ONTAP_MGMT_IP/api/name-services/dns" \
        -H "Content-Type: application/json" \
        -d "{\"svm\":{\"uuid\":\"$SVM_UUID\"},\"domains\":[\"$DOMAIN_NAME\"],\"servers\":$dns_array}" \
        --connect-timeout 10 --max-time 30 2>/dev/null)

      local dns_error
      dns_error=$(echo "$dns_result" | jq -r '.error.message // empty' 2>/dev/null || echo "")
      if [[ -n "$dns_error" && "$dns_error" != *"already exists"* && "$dns_error" != *"duplicate"* ]]; then
        warn "DNS configuration note: $dns_error"
      else
        ok "DNS configured on SVM"
      fi
    fi
  fi

  # Create CIFS server (this performs the AD join)
  if [[ "$DRY_RUN" == "true" ]]; then
    info "[DRY-RUN] Would create CIFS server with payload:"
    echo "$payload" | jq .
    info "[DRY-RUN] API call: POST https://$ONTAP_MGMT_IP/api/protocols/cifs/services"
    info "[DRY-RUN] SVM UUID: $SVM_UUID"
    echo ""
    info "[DRY-RUN] After join completes, create WINDOWS-type S3 AP:"
    info "  aws fsx create-and-attach-s3-access-point \\"
    info "    --file-system-id <FS-ID> \\"
    info "    --s3-access-point-configuration '{"
    info "      \"Namespace\": \"s3ap-win-test\","
    info "      \"FileSystemUserType\": \"WINDOWS\","
    info "      \"WindowsUser\": {\"Name\": \"Admin\"},"
    info "      \"NetworkOrigin\": \"Internet\""
    info "    }'"
    info ""
    warn "REMINDER: WindowsUser.Name = username only (no domain prefix)"
    return
  fi

  info "Creating CIFS server (AD join in progress — may take 30-60 seconds)..."
  local result
  result=$(curl -sku "$ONTAP_USER:$ONTAP_PASS" \
    -X POST "https://$ONTAP_MGMT_IP/api/protocols/cifs/services" \
    -H "Content-Type: application/json" \
    -d "{\"svm\":{\"uuid\":\"$SVM_UUID\"},$(echo "$payload" | jq -c 'del(.svm)' | sed 's/^{//' | sed 's/}$//')}" \
    --connect-timeout 10 --max-time 120 2>/dev/null)

  # Check for async job
  local job_uuid
  job_uuid=$(echo "$result" | jq -r '.job.uuid // empty' 2>/dev/null || echo "")

  if [[ -n "$job_uuid" ]]; then
    info "AD join job submitted (UUID: $job_uuid). Waiting for completion..."
    local max_wait=120
    local elapsed=0
    while [[ $elapsed -lt $max_wait ]]; do
      sleep 5
      elapsed=$((elapsed + 5))
      local job_status
      job_status=$(curl -sku "$ONTAP_USER:$ONTAP_PASS" \
        "https://$ONTAP_MGMT_IP/api/cluster/jobs/$job_uuid" \
        --connect-timeout 10 --max-time 15 2>/dev/null)

      local state
      state=$(echo "$job_status" | jq -r '.state // "unknown"')

      case "$state" in
        success)
          ok "SVM '$SVM_NAME' successfully joined to AD domain '$DOMAIN_NAME'"
          print_next_steps
          return
          ;;
        failure)
          local msg
          msg=$(echo "$job_status" | jq -r '.message // "unknown error"')
          die "AD join failed: $msg"
          ;;
        running|queued)
          info "  ...still running (${elapsed}s elapsed)"
          ;;
      esac
    done
    die "AD join timed out after ${max_wait}s. Check ONTAP job: $job_uuid"
  fi

  # Check for immediate error
  local error_msg
  error_msg=$(echo "$result" | jq -r '.error.message // empty' 2>/dev/null || echo "")
  if [[ -n "$error_msg" ]]; then
    die "AD join failed: $error_msg"
  fi

  # Check for immediate success (no job)
  local cifs_name
  cifs_name=$(echo "$result" | jq -r '.name // empty' 2>/dev/null || echo "")
  if [[ -n "$cifs_name" ]]; then
    ok "SVM '$SVM_NAME' successfully joined to AD domain '$DOMAIN_NAME' (CIFS: $cifs_name)"
    print_next_steps
    return
  fi

  # Unknown response
  warn "Unexpected response from ONTAP API:"
  echo "$result" | jq . 2>/dev/null || echo "$result"
  info "Verify AD join status: curl -sku user:pass 'https://$ONTAP_MGMT_IP/api/protocols/cifs/services?svm.name=$SVM_NAME'"
}

print_next_steps() {
  echo ""
  echo "═══════════════════════════════════════════════════════════════════"
  echo "  SVM AD Join Complete — Next Steps"
  echo "═══════════════════════════════════════════════════════════════════"
  echo ""
  echo "  1. Create a WINDOWS-type S3 Access Point:"
  echo ""
  echo "     aws fsx create-and-attach-s3-access-point \\"
  echo "       --file-system-id <FS-ID> \\"
  echo "       --s3-access-point-configuration '{"
  echo "         \"Namespace\": \"s3ap-windows-test\","
  echo "         \"FileSystemUserType\": \"WINDOWS\","
  echo "         \"WindowsUser\": {\"Name\": \"Admin\"},"
  echo "         \"NetworkOrigin\": \"Internet\""
  echo "       }'"
  echo ""
  echo -e "  ${RED}CRITICAL: WindowsUser.Name must be username ONLY${NC}"
  echo -e "  ${GREEN}CORRECT:   \"Admin\"${NC}"
  echo -e "  ${RED}INCORRECT: \"${DOMAIN_NAME%%.*}\\Admin\" → AccessDenied on data-plane${NC}"
  echo ""
  echo "  2. Test S3 AP operations from the Windows EC2 instance:"
  echo ""
  echo "     aws s3 ls s3://<s3ap-alias>/ --region $REGION"
  echo "     aws s3 cp test.txt s3://<s3ap-alias>/test.txt --region $REGION"
  echo ""
  echo "═══════════════════════════════════════════════════════════════════"
}

# =============================================================================
# MAIN
# =============================================================================
main() {
  parse_args "$@"

  echo ""
  echo "═══════════════════════════════════════════════════════════════════"
  echo "  FSx for ONTAP SVM — AD Domain Join"
  echo "═══════════════════════════════════════════════════════════════════"
  echo ""

  # Resolve parameters
  if [[ "$MANUAL_MODE" == "true" ]]; then
    info "Using manual parameters"
    [[ -z "$ONTAP_MGMT_IP" ]] && die "--ontap-ip required in manual mode"
    [[ -z "$DOMAIN_NAME" ]] && die "--domain required in manual mode"
    [[ -z "$DOMAIN_USER" ]] && die "--domain-user required in manual mode"
    [[ -z "$DNS_IPS" ]] && warn "--dns-ips not provided; SVM must already have DNS configured"
    if [[ -z "$DOMAIN_PASSWORD" ]]; then
      read -rsp "AD Admin Password: " DOMAIN_PASSWORD
      echo ""
    fi
  else
    resolve_from_stack
  fi

  # Get ONTAP credentials
  if [[ -n "$ONTAP_SECRET" ]]; then
    get_ontap_credentials
  elif [[ -z "${ONTAP_USER:-}" ]]; then
    die "No ONTAP credentials available. Use --secret or set ONTAP_SECRET_NAME."
  fi

  # Resolve SVM
  resolve_svm_uuid

  # Execute AD join
  join_svm_to_ad
}

main "$@"
