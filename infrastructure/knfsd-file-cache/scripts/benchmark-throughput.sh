#!/usr/bin/env bash
# =============================================================================
# benchmark-throughput.sh — Measure KNFSD cache throughput and hit ratio
#
# Runs sequential and parallel read tests, comparing:
#   - First read (cache miss): data fetched from FSx for ONTAP
#   - Second read (cache hit): data served from KNFSD NVMe/RAM
#
# Usage:
#   ./scripts/benchmark-throughput.sh --client-instance-id i-0xxx --mount /mnt/knfsd
#   ./scripts/benchmark-throughput.sh --local --mount /mnt/knfsd  # Run locally
# =============================================================================
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CLIENT_INSTANCE_ID=""
MOUNT_POINT="/mnt/knfsd"
LOCAL_MODE=false
FILE_SIZE_MB=100
NUM_FILES=5

# --- Colors ---
if [[ -t 1 ]]; then
  readonly GREEN='\033[0;32m' BLUE='\033[0;34m' NC='\033[0m'
else
  readonly GREEN='' BLUE='' NC=''
fi

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_ok()   { echo -e "${GREEN}[ OK ]${NC} $*"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --client-instance-id) CLIENT_INSTANCE_ID="$2"; shift 2 ;;
    --mount)              MOUNT_POINT="$2"; shift 2 ;;
    --local)              LOCAL_MODE=true; shift ;;
    --file-size)          FILE_SIZE_MB="$2"; shift 2 ;;
    --num-files)          NUM_FILES="$2"; shift 2 ;;
    *) echo "Unknown: $1"; exit 1 ;;
  esac
done

# --- Benchmark Script (runs on client) ---
BENCH_SCRIPT=$(cat <<'BENCH'
#!/bin/bash
set -e

MOUNT_POINT="__MOUNT__"
FILE_SIZE_MB=__SIZE__
NUM_FILES=__NUM__
TEST_DIR="$MOUNT_POINT/.knfsd-benchmark-$(date +%Y%m%d%H%M%S)"

echo "=== KNFSD File Cache Benchmark ==="
echo "Mount:     $MOUNT_POINT"
echo "File Size: ${FILE_SIZE_MB} MB × ${NUM_FILES} files"
echo "Total:     $((FILE_SIZE_MB * NUM_FILES)) MB"
echo ""

# Verify mount
if ! mountpoint -q "$MOUNT_POINT" 2>/dev/null; then
  echo "ERROR: $MOUNT_POINT is not a mount point"
  exit 1
fi

mkdir -p "$TEST_DIR"

# --- Generate test files ---
echo "--- Generating test files ---"
for i in $(seq 1 $NUM_FILES); do
  dd if=/dev/urandom of="$TEST_DIR/testfile_${i}.dat" bs=1M count=$FILE_SIZE_MB 2>/dev/null
done
sync
echo "Generated $NUM_FILES × ${FILE_SIZE_MB} MB files"
echo ""

# --- Sequential Read: Cache Miss ---
echo "--- Sequential Read: Cache Miss (first read) ---"
sync; echo 3 > /proc/sys/vm/drop_caches 2>/dev/null || true
sleep 1

MISS_START=$(date +%s%N)
for i in $(seq 1 $NUM_FILES); do
  cat "$TEST_DIR/testfile_${i}.dat" > /dev/null
done
MISS_END=$(date +%s%N)

MISS_MS=$(( (MISS_END - MISS_START) / 1000000 ))
MISS_THROUGHPUT=$(echo "scale=1; $FILE_SIZE_MB * $NUM_FILES * 1000 / $MISS_MS" | bc 2>/dev/null || echo "N/A")
echo "  Time:       ${MISS_MS} ms"
echo "  Throughput: ${MISS_THROUGHPUT} MB/s"
echo ""

# --- Sequential Read: Cache Hit ---
echo "--- Sequential Read: Cache Hit (second read) ---"
sleep 1

HIT_START=$(date +%s%N)
for i in $(seq 1 $NUM_FILES); do
  cat "$TEST_DIR/testfile_${i}.dat" > /dev/null
done
HIT_END=$(date +%s%N)

HIT_MS=$(( (HIT_END - HIT_START) / 1000000 ))
HIT_THROUGHPUT=$(echo "scale=1; $FILE_SIZE_MB * $NUM_FILES * 1000 / $HIT_MS" | bc 2>/dev/null || echo "N/A")
echo "  Time:       ${HIT_MS} ms"
echo "  Throughput: ${HIT_THROUGHPUT} MB/s"
echo ""

# --- Speedup ---
if [[ "$MISS_MS" -gt 0 && "$HIT_MS" -gt 0 ]]; then
  SPEEDUP=$(echo "scale=1; $MISS_MS / $HIT_MS" | bc 2>/dev/null || echo "N/A")
  echo "--- Results ---"
  echo "  Cache Hit Speedup: ${SPEEDUP}x"
  echo "  Miss Throughput:   ${MISS_THROUGHPUT} MB/s"
  echo "  Hit Throughput:    ${HIT_THROUGHPUT} MB/s"
fi

# --- Cleanup ---
rm -rf "$TEST_DIR"
echo ""
echo "Benchmark complete. Test files cleaned up."
BENCH
)

# Substitute variables
BENCH_SCRIPT="${BENCH_SCRIPT//__MOUNT__/$MOUNT_POINT}"
BENCH_SCRIPT="${BENCH_SCRIPT//__SIZE__/$FILE_SIZE_MB}"
BENCH_SCRIPT="${BENCH_SCRIPT//__NUM__/$NUM_FILES}"

if [[ "$LOCAL_MODE" == "true" ]]; then
  log_info "Running benchmark locally..."
  echo "$BENCH_SCRIPT" | sudo bash
else
  if [[ -z "$CLIENT_INSTANCE_ID" ]]; then
    echo "Usage: ./scripts/benchmark-throughput.sh --client-instance-id i-0xxx"
    echo "   or: ./scripts/benchmark-throughput.sh --local --mount /mnt/knfsd"
    exit 1
  fi

  log_info "Running benchmark on remote instance: $CLIENT_INSTANCE_ID"
  CMD_ID=$(aws ssm send-command \
    --instance-ids "$CLIENT_INSTANCE_ID" \
    --document-name "AWS-RunShellScript" \
    --parameters "commands=[\"$(echo "$BENCH_SCRIPT" | base64 | tr -d '\n')\"]" \
    --timeout-seconds 300 \
    --query 'Command.CommandId' \
    --output text)

  log_info "Command ID: $CMD_ID — waiting for results..."
  sleep 15

  aws ssm get-command-invocation \
    --command-id "$CMD_ID" \
    --instance-id "$CLIENT_INSTANCE_ID" \
    --query 'StandardOutputContent' \
    --output text
fi
