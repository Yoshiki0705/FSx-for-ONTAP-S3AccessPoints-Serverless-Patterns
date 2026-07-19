#!/usr/bin/env bash
# =============================================================================
# generate-eda-data.sh
#
# Generate synthetic EDA regression data for UC6 testing and Workshop demos.
# Based on AWS Workshop Module 06 (Generate EDA Data).
#
# Generates:
#   - 500 EDA job workflows (~2000 log files)
#   - LSF job scheduling logs with resource usage
#   - Cadence ncvlog/ncelab compilation logs
#   - Xcelium simulation logs (PASS/FAIL/UVM_FATAL)
#   - Post-processing coverage analysis logs
#   - regression_summary.csv for Athena/QuickSight
#
# Usage:
#   # Generate to local directory (for DemoMode testing)
#   ./scripts/generate-eda-data.sh --output-dir ./test-data/uc6/generated
#
#   # Generate and upload to FSx for ONTAP via S3 AP
#   ./scripts/generate-eda-data.sh --s3-ap-alias <alias> --prefix eda-regression/
#
#   # Quick mode (50 jobs for rapid testing)
#   ./scripts/generate-eda-data.sh --output-dir ./test-data/uc6/generated --jobs 50
#
# Workshop reference:
#   https://catalog.us-east-1.prod.workshops.aws/workshops/
#   9cd82e0b-8348-456b-932a-818b9e5825a1/en-US/06-generate-data
# =============================================================================
set -euo pipefail

# --- Defaults ---
NUM_JOBS=500
OUTPUT_DIR=""
S3_AP_ALIAS=""
S3_PREFIX="eda-regression/"
FAILURE_RATE=15       # % of jobs that fail
LICENSE_FAIL_RATE=4   # % of jobs with license errors
TIMING_VIOLATION_RATE=8  # % of jobs with timing violations

# --- EDA Tool/Module Data ---
MODULES=(
  "cpu_core" "gpu_shader" "memory_ctrl" "pcie_phy" "usb_phy"
  "ddr5_ctrl" "noc_router" "crypto_engine" "display_pipe" "audio_codec"
  "power_mgmt" "clock_gen" "io_pad_ring" "serdes_tx" "serdes_rx"
  "cache_l1" "cache_l2" "interrupt_ctrl" "dma_engine" "watchdog"
)

CLOCK_DOMAINS=("sys_clk" "mem_clk" "io_clk" "pcie_clk" "usb_clk" "ddr_clk")

LSF_QUEUES=("normal" "high" "regression" "overnight" "express")

LICENSE_FEATURES=(
  "Xcelium_Single" "Xcelium_Multi" "ncvlog" "ncelab"
  "Conformal_LEC" "IUS_Mixed_Signal" "Genus_Synthesis"
)

ERROR_TYPES=(
  "UVM_FATAL" "UVM_ERROR" "TIMING_VIOLATION" "ASSERTION_FAIL"
  "MEMORY_OVERFLOW" "DEADLOCK_DETECTED" "LICENSE_CHECKOUT_FAILED"
)

# --- Parse Arguments ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-dir) OUTPUT_DIR="$2"; shift 2 ;;
    --s3-ap-alias) S3_AP_ALIAS="$2"; shift 2 ;;
    --prefix) S3_PREFIX="$2"; shift 2 ;;
    --jobs) NUM_JOBS="$2"; shift 2 ;;
    --help|-h)
      echo "Usage: $0 [--output-dir DIR | --s3-ap-alias ALIAS] [--prefix PREFIX] [--jobs N]"
      exit 0
      ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

if [[ -z "$OUTPUT_DIR" && -z "$S3_AP_ALIAS" ]]; then
  echo "Error: Specify --output-dir or --s3-ap-alias"
  exit 1
fi

# --- Helper Functions ---
log() { echo "[$(date '+%H:%M:%S')] $*"; }

random_int() {
  local min=$1 max=$2
  echo $(( RANDOM % (max - min + 1) + min ))
}

random_choice() {
  local arr=("$@")
  echo "${arr[RANDOM % ${#arr[@]}]}"
}

random_float() {
  local min=$1 max=$2
  local int_part=$(random_int "$min" "$max")
  local dec_part=$(random_int 0 99)
  echo "${int_part}.${dec_part}"
}

generate_timestamp() {
  local days_ago=$(random_int 0 30)
  local hour=$(random_int 0 23)
  local min=$(random_int 0 59)
  local sec=$(random_int 0 59)
  if [[ "$(uname)" == "Darwin" ]]; then
    date -v-${days_ago}d -v${hour}H -v${min}M -v${sec}S '+%Y-%m-%dT%H:%M:%S'
  else
    date -d "-${days_ago} days ${hour}:${min}:${sec}" '+%Y-%m-%dT%H:%M:%S'
  fi
}

# --- Generate LSF Log ---
generate_lsf_log() {
  local job_id=$1 module=$2 queue=$3 status=$4
  local cpu_time=$(random_int 60 7200)
  local memory_mb=$(random_int 512 32768)
  local wall_time=$(random_int 120 14400)
  local slots=$(random_int 1 16)
  local timestamp=$(generate_timestamp)

  cat <<EOF
Job <${job_id}> was submitted from host <submit-host01>.
Job was executed on host(s) <exec-host$(random_int 1 50)>.
Queue: ${queue}
Module: ${module}
Submitted at: ${timestamp}
Started at: ${timestamp}
Results reported at: ${timestamp}

Resource usage:
    CPU time:   ${cpu_time} sec
    Max Memory: ${memory_mb} MB
    Wall time:  ${wall_time} sec
    Slots:      ${slots}

Exit Status: $([ "$status" = "PASS" ] && echo "0" || echo "1")
EOF
}

# --- Generate Compilation Log ---
generate_compilation_log() {
  local module=$1 status=$2
  local warnings=$(random_int 0 25)
  local errors=$([ "$status" = "PASS" ] && echo "0" || echo "$(random_int 1 5)")
  local files_compiled=$(random_int 10 200)

  cat <<EOF
ncvlog: v24.09-s003: (c) Copyright 1995-2026, Cadence Design Systems, Inc.
File: /designs/${module}/rtl/${module}_top.sv
Compiling module ${module}_top...
Compiling ${files_compiled} source files...
$([ "$warnings" -gt 0 ] && echo "ncvlog: *W,TFIPC: ${warnings} warnings generated" || true)
$([ "$errors" -gt 0 ] && echo "ncvlog: *E,COMPIL: ${errors} errors detected" || true)

ncelab: v24.09-s003
Elaborating module ${module}_top...
$([ "$errors" -gt 0 ] && echo "ncelab: *E,ELBERR: Elaboration errors detected" || echo "ncelab: Elaboration complete.")

Total warnings: ${warnings}
Total errors: ${errors}
EOF
}

# --- Generate Simulation Log ---
generate_simulation_log() {
  local job_id=$1 module=$2 status=$3 error_type=$4
  local sim_time=$(random_int 1000 500000)
  local timestamp=$(generate_timestamp)

  cat <<EOF
xmsim: v24.09-s003: (c) Copyright 1995-2026, Cadence Design Systems, Inc.
Loading snapshot worklib.${module}_top:sv...
xmsim: *W,DSEM2009: Simulation time: ${sim_time} ns

--- UVM Report Summary ---
UVM_INFO:    $(random_int 100 5000)
UVM_WARNING: $(random_int 0 50)
EOF

  if [[ "$status" == "FAIL" ]]; then
    case "$error_type" in
      UVM_FATAL)
        cat <<EOF
UVM_ERROR:   $(random_int 1 10)
UVM_FATAL:   1

UVM_FATAL @ ${sim_time}ns: ${module}_scoreboard [COMPARE_FAIL]
  Expected: 0x$(printf '%08x' $(random_int 0 4294967295))
  Actual:   0x$(printf '%08x' $(random_int 0 4294967295))
  Simulation FAILED
EOF
        ;;
      TIMING_VIOLATION)
        local slack="-$(random_float 0 2)"
        local clock=$(random_choice "${CLOCK_DOMAINS[@]}")
        cat <<EOF
UVM_ERROR:   $(random_int 1 5)
UVM_FATAL:   0

*** TIMING VIOLATION ***
  Clock domain: ${clock}
  Setup time violation on path: ${module}/reg_q -> ${module}/mux_out
  Required: 1.50 ns
  Actual:   $(random_float 1 3) ns
  Slack:    ${slack} ns
  Simulation FAILED (timing)
EOF
        ;;
      LICENSE_CHECKOUT_FAILED)
        local feature=$(random_choice "${LICENSE_FEATURES[@]}")
        cat <<EOF
xmsim: *F,LICCHK: Cannot checkout license feature '${feature}'
  License server: 27000@license-server01
  All licenses in use. Retry count exhausted.
  Simulation ABORTED (license)
EOF
        ;;
      *)
        cat <<EOF
UVM_ERROR:   $(random_int 1 10)
UVM_FATAL:   0

ERROR: ${error_type} detected in ${module}_top
  Simulation FAILED
EOF
        ;;
    esac
  else
    cat <<EOF
UVM_ERROR:   0
UVM_FATAL:   0

--- Test PASSED ---
Simulation time: ${sim_time} ns
EOF
  fi
}

# --- Generate Coverage Report ---
generate_coverage_log() {
  local module=$1 coverage_pct=$2

  cat <<EOF
Coverage Report: ${module}
================================
Code Coverage:
  Line:       ${coverage_pct}%
  Toggle:     $(random_int 60 99)%
  Branch:     $(random_int 55 95)%
  Condition:  $(random_int 50 90)%
  FSM:        $(random_int 65 99)%

Functional Coverage:
  Overall:    $(random_int 70 99)%
  Sequences:  $(random_int 60 95)%
  Crosses:    $(random_int 50 90)%

Total:        ${coverage_pct}%
Threshold:    80%
Status:       $([ "$coverage_pct" -ge 80 ] && echo "PASS" || echo "BELOW_THRESHOLD")
EOF
}

# --- Main Generation Loop ---
log "Generating ${NUM_JOBS} EDA job workflows..."

if [[ -n "$OUTPUT_DIR" ]]; then
  mkdir -p "$OUTPUT_DIR"/{lsf,compilation,simulation,coverage}
fi

# CSV header for regression_summary
CSV_HEADER="job_id,module_name,status,error_type,timestamp,queue_name,cpu_time_sec,memory_mb,wall_time_sec,coverage_percent,timing_slack,clock_domain,license_feature,error_message"
CSV_DATA="$CSV_HEADER"

for i in $(seq 1 "$NUM_JOBS"); do
  job_id="JOB_$(printf '%05d' $i)"
  module=$(random_choice "${MODULES[@]}")
  queue=$(random_choice "${LSF_QUEUES[@]}")
  timestamp=$(generate_timestamp)
  cpu_time=$(random_int 60 7200)
  memory_mb=$(random_int 512 32768)
  wall_time=$(random_int 120 14400)
  coverage_pct=$(random_int 55 99)
  timing_slack=""
  clock_domain=""
  license_feature=""
  error_message=""

  # Determine status
  fail_roll=$(random_int 1 100)
  if [[ $fail_roll -le $LICENSE_FAIL_RATE ]]; then
    status="FAIL"
    error_type="LICENSE_CHECKOUT_FAILED"
    license_feature=$(random_choice "${LICENSE_FEATURES[@]}")
    error_message="Cannot checkout ${license_feature}"
  elif [[ $fail_roll -le $((LICENSE_FAIL_RATE + TIMING_VIOLATION_RATE)) ]]; then
    status="FAIL"
    error_type="TIMING_VIOLATION"
    timing_slack="-$(random_float 0 2)"
    clock_domain=$(random_choice "${CLOCK_DOMAINS[@]}")
    error_message="Setup violation on ${clock_domain}"
  elif [[ $fail_roll -le $FAILURE_RATE ]]; then
    status="FAIL"
    error_type=$(random_choice "UVM_FATAL" "UVM_ERROR" "ASSERTION_FAIL" "MEMORY_OVERFLOW")
    error_message="${error_type} in ${module}"
  else
    status="PASS"
    error_type=""
  fi

  # Generate log files
  if [[ -n "$OUTPUT_DIR" ]]; then
    generate_lsf_log "$job_id" "$module" "$queue" "$status" \
      > "$OUTPUT_DIR/lsf/${job_id}_lsf.log"
    generate_compilation_log "$module" "$status" \
      > "$OUTPUT_DIR/compilation/${job_id}_compile.log"
    generate_simulation_log "$job_id" "$module" "$status" "$error_type" \
      > "$OUTPUT_DIR/simulation/${job_id}_sim.log"
    generate_coverage_log "$module" "$coverage_pct" \
      > "$OUTPUT_DIR/coverage/${job_id}_coverage.log"
  fi

  # Append to CSV
  CSV_DATA="${CSV_DATA}
${job_id},${module},${status},${error_type},${timestamp},${queue},${cpu_time},${memory_mb},${wall_time},${coverage_pct},${timing_slack},${clock_domain},${license_feature},${error_message}"

  # Progress
  if (( i % 100 == 0 )); then
    log "  Generated ${i}/${NUM_JOBS} jobs..."
  fi
done

# --- Write CSV ---
if [[ -n "$OUTPUT_DIR" ]]; then
  echo "$CSV_DATA" > "$OUTPUT_DIR/regression_summary.csv"
  log "Output written to: $OUTPUT_DIR/"
  log "  - ${NUM_JOBS} LSF logs in lsf/"
  log "  - ${NUM_JOBS} compilation logs in compilation/"
  log "  - ${NUM_JOBS} simulation logs in simulation/"
  log "  - ${NUM_JOBS} coverage logs in coverage/"
  log "  - regression_summary.csv ($(echo "$CSV_DATA" | wc -l) rows)"
fi

# --- Upload to S3 AP (if specified) ---
if [[ -n "$S3_AP_ALIAS" ]]; then
  log "Uploading to S3 AP: s3://${S3_AP_ALIAS}/${S3_PREFIX}"

  TMPDIR=$(mktemp -d)
  echo "$CSV_DATA" > "$TMPDIR/regression_summary.csv"

  aws s3 cp "$TMPDIR/regression_summary.csv" \
    "s3://${S3_AP_ALIAS}/${S3_PREFIX}regression_summary.csv"

  if [[ -n "$OUTPUT_DIR" ]]; then
    aws s3 sync "$OUTPUT_DIR/lsf/" \
      "s3://${S3_AP_ALIAS}/${S3_PREFIX}lsf/" --quiet
    aws s3 sync "$OUTPUT_DIR/simulation/" \
      "s3://${S3_AP_ALIAS}/${S3_PREFIX}simulation/" --quiet
    aws s3 sync "$OUTPUT_DIR/compilation/" \
      "s3://${S3_AP_ALIAS}/${S3_PREFIX}compilation/" --quiet
    aws s3 sync "$OUTPUT_DIR/coverage/" \
      "s3://${S3_AP_ALIAS}/${S3_PREFIX}coverage/" --quiet
  else
    # Generate to tmp and upload
    for i in $(seq 1 "$NUM_JOBS"); do
      job_id="JOB_$(printf '%05d' $i)"
      module=$(random_choice "${MODULES[@]}")
      generate_simulation_log "$job_id" "$module" "PASS" "" \
        > "$TMPDIR/${job_id}_sim.log"
    done
    aws s3 sync "$TMPDIR/" \
      "s3://${S3_AP_ALIAS}/${S3_PREFIX}" --quiet
  fi

  rm -rf "$TMPDIR"
  log "Upload complete."
fi

log "Done. Generated ${NUM_JOBS} EDA job workflows."
log ""
log "Next steps:"
log "  1. Create S3 AP pointing to the FSx for ONTAP volume"
log "  2. Run Glue Crawler or create Athena table manually"
log "  3. Query with: test-data/uc6/sample-queries.sql"
log "  4. Connect to Amazon Quick for AI-powered analytics"
