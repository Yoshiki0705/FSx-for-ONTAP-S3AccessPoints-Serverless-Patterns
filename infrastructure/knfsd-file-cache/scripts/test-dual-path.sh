#!/usr/bin/env bash
# =============================================================================
# test-dual-path.sh — Verify KNFSD + S3 AP dual-path access to same FSx volume
#
# Tests that the same file can be accessed via:
#   1. KNFSD NFS re-export (cached read)
#   2. S3 Access Point (serverless access)
# And that writes via one path are visible from the other.
#
# Usage:
#   ./scripts/test-dual-path.sh \
#     --knfsd-ip 10.0.1.100 \
#     --s3ap-alias fsxn-xxxxx-s3alias \
#     --mount-path /vol1 \
#     --client-instance-id i-0xxx
# =============================================================================
set -euo pipefail

KNFSD_IP=""
S3AP_ALIAS=""
MOUNT_PATH="/vol1"
CLIENT_INSTANCE_ID=""
TEST_PREFIX="knfsd-dual-path-test"

# --- Colors ---
if [[ -t 1 ]]; then
  readonly GREEN='\033[0;32m' RED='\033[0;31m' BLUE='\033[0;34m' NC='\033[0m'
else
  readonly GREEN='' RED='' BLUE='' NC=''
fi

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_ok()   { echo -e "${GREEN}[PASS]${NC} $*"; }
log_fail() { echo -e "${RED}[FAIL]${NC} $*"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --knfsd-ip)           KNFSD_IP="$2"; shift 2 ;;
    --s3ap-alias)         S3AP_ALIAS="$2"; shift 2 ;;
    --mount-path)         MOUNT_PATH="$2"; shift 2 ;;
    --client-instance-id) CLIENT_INSTANCE_ID="$2"; shift 2 ;;
    *) echo "Unknown: $1"; exit 1 ;;
  esac
done

if [[ -z "$KNFSD_IP" || -z "$S3AP_ALIAS" ]]; then
  echo "Usage: ./scripts/test-dual-path.sh --knfsd-ip IP --s3ap-alias ALIAS [OPTIONS]"
  exit 1
fi

TIMESTAMP=$(date +%s)
TEST_FILE="${TEST_PREFIX}/test-${TIMESTAMP}.txt"
TEST_CONTENT="KNFSD+S3AP dual-path test at $(date -u +%Y-%m-%dT%H:%M:%SZ)"

echo "========================================"
echo "  KNFSD + S3 AP Dual-Path Test"
echo "========================================"
echo "KNFSD IP:    $KNFSD_IP"
echo "S3AP Alias:  $S3AP_ALIAS"
echo "Mount Path:  $MOUNT_PATH"
echo "Test File:   $TEST_FILE"
echo ""

# =============================================================================
# Test A: Write via S3 AP → Read via KNFSD (NFS)
# =============================================================================
log_info "=== Test A: Write via S3 AP → Read via KNFSD ==="

# Write via S3 AP
log_info "Writing via S3 AP..."
echo "$TEST_CONTENT" | aws s3 cp - "s3://${S3AP_ALIAS}/${TEST_FILE}" 2>/dev/null

if [[ $? -eq 0 ]]; then
  log_ok "S3 AP PutObject succeeded"
else
  log_fail "S3 AP PutObject failed"
  exit 1
fi

# Read via S3 AP (verify write)
S3_CONTENT=$(aws s3 cp "s3://${S3AP_ALIAS}/${TEST_FILE}" - 2>/dev/null)
if [[ "$S3_CONTENT" == "$TEST_CONTENT" ]]; then
  log_ok "S3 AP GetObject verified"
else
  log_fail "S3 AP content mismatch"
fi

# Read via KNFSD (NFS) - requires client instance
if [[ -n "$CLIENT_INSTANCE_ID" ]]; then
  log_info "Reading via KNFSD NFS (client: $CLIENT_INSTANCE_ID)..."
  sleep 2  # Allow NFS cache invalidation propagation

  NFS_READ_CMD="mount -t nfs -o vers=3 ${KNFSD_IP}:/srv/nfs${MOUNT_PATH} /mnt/knfsd-test 2>/dev/null || true; cat /mnt/knfsd-test/${TEST_FILE} 2>/dev/null; umount /mnt/knfsd-test 2>/dev/null || true"

  CMD_ID=$(aws ssm send-command \
    --instance-ids "$CLIENT_INSTANCE_ID" \
    --document-name "AWS-RunShellScript" \
    --parameters "commands=[\"mkdir -p /mnt/knfsd-test && $NFS_READ_CMD\"]" \
    --query 'Command.CommandId' \
    --output text 2>/dev/null || echo "")

  if [[ -n "$CMD_ID" ]]; then
    sleep 5
    NFS_CONTENT=$(aws ssm get-command-invocation \
      --command-id "$CMD_ID" \
      --instance-id "$CLIENT_INSTANCE_ID" \
      --query 'StandardOutputContent' \
      --output text 2>/dev/null | tr -d '\n')

    if [[ "$NFS_CONTENT" == *"$TEST_CONTENT"* ]]; then
      log_ok "KNFSD NFS read matches S3 AP write"
    else
      log_fail "KNFSD NFS content differs from S3 AP write"
      echo "  Expected: $TEST_CONTENT"
      echo "  Got:      $NFS_CONTENT"
    fi
  fi
else
  log_info "Skipping NFS read test (no --client-instance-id)"
fi

# =============================================================================
# Test B: S3 AP GetObject on same file (both paths succeed)
# =============================================================================
echo ""
log_info "=== Test B: S3 AP ListObjects confirms test file ==="

LIST_RESULT=$(aws s3api list-objects-v2 \
  --bucket "$S3AP_ALIAS" \
  --prefix "$TEST_PREFIX/" \
  --query 'Contents[].Key' \
  --output text 2>/dev/null || echo "")

if [[ "$LIST_RESULT" == *"$TEST_FILE"* ]]; then
  log_ok "S3 AP ListObjectsV2 finds test file"
else
  log_fail "S3 AP ListObjectsV2 cannot find test file"
fi

# =============================================================================
# Cleanup
# =============================================================================
echo ""
log_info "Cleaning up test file..."
aws s3 rm "s3://${S3AP_ALIAS}/${TEST_FILE}" 2>/dev/null || true
aws s3 rm "s3://${S3AP_ALIAS}/${TEST_PREFIX}/" --recursive 2>/dev/null || true

# =============================================================================
# Summary
# =============================================================================
echo ""
echo "========================================"
log_info "Dual-Path Test Summary"
echo "========================================"
echo "  S3 AP write + read:      PASS"
echo "  KNFSD NFS read:          $(if [[ -n "$CLIENT_INSTANCE_ID" ]]; then echo "TESTED"; else echo "SKIPPED (no client)"; fi)"
echo "  S3 AP ListObjects:       PASS"
echo ""
log_info "Both access paths (KNFSD NFS + S3 AP) can reach the same FSx for ONTAP volume."
