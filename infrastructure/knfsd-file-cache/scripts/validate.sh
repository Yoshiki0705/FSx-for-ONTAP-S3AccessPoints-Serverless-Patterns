#!/usr/bin/env bash
# =============================================================================
# validate.sh — Post-deploy validation of KNFSD File Cache
#
# Checks:
#   1. Instance is running + SSM online
#   2. proxy-startup.sh completed (NFS exports active)
#   3. Source NFS mount is active
#   4. Cache is ready (FS-Cache or Page Cache)
#   5. Optional: test mount from this machine (if in same VPC)
#
# Usage:
#   ./scripts/validate.sh                    # Use Terraform output for instance ID
#   ./scripts/validate.sh --instance-id i-0xxx  # Explicit instance ID
# =============================================================================
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly TF_DIR="$(cd "$SCRIPT_DIR/../terraform" && pwd)"

INSTANCE_ID=""
REGION="ap-northeast-1"

# --- Colors ---
if [[ -t 1 ]]; then
  readonly GREEN='\033[0;32m' RED='\033[0;31m' YELLOW='\033[0;33m'
  readonly BLUE='\033[0;34m' BOLD='\033[1m' NC='\033[0m'
else
  readonly GREEN='' RED='' YELLOW='' BLUE='' BOLD='' NC=''
fi

pass() { echo -e "  ${GREEN}✓${NC} $*"; }
fail() { echo -e "  ${RED}✗${NC} $*"; }
info() { echo -e "  ${BLUE}ℹ${NC} $*"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --instance-id) INSTANCE_ID="$2"; shift 2 ;;
    --region)      REGION="$2"; shift 2 ;;
    *) echo "Unknown: $1"; exit 1 ;;
  esac
done

# Get instance ID from Terraform if not provided
if [[ -z "$INSTANCE_ID" ]]; then
  if [[ -f "$TF_DIR/terraform.tfstate" ]]; then
    cd "$TF_DIR"
    INSTANCE_ID=$(terraform output -json knfsd_instance_ids 2>/dev/null | jq -r '.[0]' || echo "")
  fi
fi

if [[ -z "$INSTANCE_ID" || "$INSTANCE_ID" == "null" ]]; then
  echo "ERROR: No instance ID found. Provide --instance-id or run from deployed terraform directory."
  exit 1
fi

echo -e "${BOLD}KNFSD File Cache Validation${NC}"
echo "Instance: $INSTANCE_ID"
echo "Region:   $REGION"
echo ""

FAILURES=0

# --- Check 1: Instance Running ---
echo -e "${BOLD}1. Instance State${NC}"
STATE=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].State.Name' --output text --region "$REGION" 2>/dev/null || echo "unknown")
if [[ "$STATE" == "running" ]]; then
  pass "Instance is running"
else
  fail "Instance state: $STATE"
  ((FAILURES++))
fi

# --- Check 2: SSM Online ---
echo -e "${BOLD}2. SSM Agent${NC}"
SSM_STATUS=$(aws ssm describe-instance-information \
  --filters "Key=InstanceIds,Values=$INSTANCE_ID" \
  --query 'InstanceInformationList[0].PingStatus' --output text --region "$REGION" 2>/dev/null || echo "unknown")
if [[ "$SSM_STATUS" == "Online" ]]; then
  pass "SSM agent online"
else
  fail "SSM status: $SSM_STATUS (wait 2 min after boot)"
  ((FAILURES++))
fi

if [[ "$SSM_STATUS" != "Online" ]]; then
  echo ""
  echo "SSM not online yet. Wait 1-2 minutes and retry."
  exit 1
fi

# --- Check 3: NFS Exports ---
echo -e "${BOLD}3. NFS Exports${NC}"
CMD_ID=$(aws ssm send-command --instance-ids "$INSTANCE_ID" \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["exportfs -v 2>/dev/null"]' \
  --query 'Command.CommandId' --output text --region "$REGION" 2>/dev/null)
sleep 5
EXPORTS=$(aws ssm get-command-invocation --command-id "$CMD_ID" --instance-id "$INSTANCE_ID" \
  --query 'StandardOutputContent' --output text --region "$REGION" 2>/dev/null || echo "")

if [[ "$EXPORTS" == *"/srv/nfs"* || "$EXPORTS" == *"vol"* ]]; then
  pass "NFS exports configured"
  info "$EXPORTS" | head -3
else
  fail "No NFS exports found (proxy-startup.sh may still be running)"
  info "Wait 60 sec after boot, then retry. Check: journalctl -u knfsd-startup"
  ((FAILURES++))
fi

# --- Check 4: Source NFS Mount ---
echo -e "${BOLD}4. Source NFS Mount${NC}"
CMD_ID=$(aws ssm send-command --instance-ids "$INSTANCE_ID" \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["mount | grep /srv/nfs"]' \
  --query 'Command.CommandId' --output text --region "$REGION" 2>/dev/null)
sleep 5
MOUNTS=$(aws ssm get-command-invocation --command-id "$CMD_ID" --instance-id "$INSTANCE_ID" \
  --query 'StandardOutputContent' --output text --region "$REGION" 2>/dev/null || echo "")

if [[ "$MOUNTS" == *"nfs"* ]]; then
  pass "Source NFS mounted"
  if [[ "$MOUNTS" == *"fsc"* ]]; then
    pass "FS-Cache (fsc) enabled on source mount"
  else
    info "FS-Cache not enabled (L1 RAM cache only)"
  fi
else
  fail "No source NFS mount found"
  ((FAILURES++))
fi

# --- Check 5: Kernel + NFS Threads ---
echo -e "${BOLD}5. System Info${NC}"
CMD_ID=$(aws ssm send-command --instance-ids "$INSTANCE_ID" \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["uname -r","cat /proc/fs/nfsd/threads 2>/dev/null || echo 0","ss -tlnp | grep -c 2049"]' \
  --query 'Command.CommandId' --output text --region "$REGION" 2>/dev/null)
sleep 5
SYSINFO=$(aws ssm get-command-invocation --command-id "$CMD_ID" --instance-id "$INSTANCE_ID" \
  --query 'StandardOutputContent' --output text --region "$REGION" 2>/dev/null || echo "")

KERNEL=$(echo "$SYSINFO" | head -1)
THREADS=$(echo "$SYSINFO" | sed -n '2p')
NFS_LISTEN=$(echo "$SYSINFO" | sed -n '3p')

if [[ "$KERNEL" == *"knfsd"* ]]; then
  pass "Kernel: $KERNEL"
else
  info "Kernel: $KERNEL (expected *-knfsd)"
fi

if [[ "$THREADS" -gt 0 ]] 2>/dev/null; then
  pass "NFS threads: $THREADS"
else
  fail "NFS server not running (0 threads)"
  ((FAILURES++))
fi

if [[ "$NFS_LISTEN" -gt 0 ]] 2>/dev/null; then
  pass "NFS listening on port 2049"
else
  fail "NFS not listening on 2049"
  ((FAILURES++))
fi

# --- Summary ---
echo ""
if [[ $FAILURES -eq 0 ]]; then
  echo -e "${GREEN}${BOLD}All checks passed.${NC} KNFSD is ready for client mounts."
  echo ""
  KNFSD_IP=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" \
    --query 'Reservations[0].Instances[0].PrivateIpAddress' --output text --region "$REGION")
  echo "Mount from client:"
  echo "  sudo mount -t nfs -o vers=3 $KNFSD_IP:/vol1 /mnt/knfsd"
else
  echo -e "${RED}${BOLD}$FAILURES check(s) failed.${NC}"
  echo "See troubleshooting: docs/troubleshooting.md"
fi
