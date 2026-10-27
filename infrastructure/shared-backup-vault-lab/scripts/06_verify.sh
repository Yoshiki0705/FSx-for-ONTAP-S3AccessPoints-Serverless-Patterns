#!/bin/bash
# Real-environment run: recorded [V1][V2][V4]; not recorded [V3][V5][V6][V7][E13] (status source: docs/verification-record.md)
#
# 06_verify.sh - read-only verification of the sharing result, and (with --cost) a
# read of the cost reported for the lab.
#
# Usage:
#   06_verify.sh [--region REGION]
#   06_verify.sh --cost [--since YYYY-MM-DD]
#
#   --region   one Region. Default: every configured Region.
#   --cost     do not run the checks; read Cost Explorer for both accounts instead.
#   --since    first day of the cost period (with --cost). Default: the date of the
#              first record in lab-run.local.jsonl. Without either the script exits 2.
#
# Checks (each prints the expected shape next to the measured value):
#   V1  the recipient's shared-vault list holds the lab vault, the ARN account is the
#       owner's account, the vault type is the air-gapped type
#   V2  the owner's shared-vault list is empty (the list shows what others share)
#   V4  listing recovery points without --backup-vault-account-id is refused with
#       AccessDeniedException; with it, the call succeeds
#   after the copy: the recovery point ARN has the cross-account form, its restore
#   metadata can be read by the recipient, its delete date is shown
#
# --cost reads Cost Explorer once with a Project tag filter and once without, for
# each account. The values are Cost Explorer values, not an invoice, and may lag.
# The Cost Explorer API is charged per request; the script prints the request count.
# Cost Explorer is a global endpoint: the calls go to us-east-1.
#
# Exit codes: 0 success (warnings allowed), 1 a check failed, 2 usage error
# (including a missing --cost start date).
#
# Not yet run on real environment: the shape of the shared-vault rows, the error
# codes and the Cost Explorer tag filter. A pass here means the call returned what
# is expected; it does not mean the lab works in production.

set -euo pipefail
# shellcheck source-path=SCRIPTDIR
# shellcheck source=lib/common.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

# This script changes nothing, so its results are real observations, not a plan.
lab_apply_on

usage() {
  cat <<'EOF'
Usage: 06_verify.sh [--region R]
       06_verify.sh --cost [--since YYYY-MM-DD]
Read-only checks of the sharing result (V1, V2, V4) or, with --cost, the cost reported by Cost Explorer.
EOF
}

REGION_ARG=""
COST=0
SINCE=""
while [ "$#" -gt 0 ]; do
  case $1 in
    --region)
      if [ "$#" -lt 2 ]; then
        die_usage "--region needs a value"
      fi
      REGION_ARG=$2
      shift 2
      ;;
    --cost)
      COST=1
      shift
      ;;
    --since)
      if [ "$#" -lt 2 ]; then
        die_usage "--since needs a date (YYYY-MM-DD)"
      fi
      SINCE=$2
      shift 2
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *) die_usage "unknown argument: $1" ;;
  esac
done
if [ -n "$SINCE" ] && [ "$COST" != 1 ]; then
  die_usage "--since is only valid with --cost"
fi
if [ "$COST" = 1 ] && [ -n "$REGION_ARG" ]; then
  die_usage "--cost has no Region: Cost Explorer is a global endpoint (calls go to us-east-1)"
fi
if [ -n "$SINCE" ]; then
  validate_since "$SINCE"
fi
if [ -n "$REGION_ARG" ]; then
  validate_region_arg "$REGION_ARG"
  REGION_LIST=$REGION_ARG
else
  REGION_LIST=$(lab_regions | tr '\n' ' ' | sed 's/ $//')
fi

# error_code_of TEXT: the AWS error code in a CLI error text, or "unknown".
error_code_of() {
  local code
  code=$(printf '%s' "$1" | sed -n 's/.*An error occurred (\([A-Za-z]*\)).*/\1/p' | head -n 1)
  printf '%s' "${code:-unknown}"
}

# --------------------------------------------------------------------------
# --cost
# --------------------------------------------------------------------------

CE_REQUESTS=0
CE_DOC_URL="https://docs.aws.amazon.com/cost-management/latest/userguide/ce-what-is.html"

# cost_read KIND FILTERED: read Cost Explorer for one account, with (1) or without
# (0) the Project tag filter. Sets CE_RESULT (the pages as JSON lines) and returns 0,
# 1 when access is denied, 2 on another failure.
CE_RESULT=""
CE_ERROR=""
cost_read() {
  local kind=$1 filtered=$2 token="" out pages=0
  local period="Start=$CE_START,End=$CE_END"
  local -a args page_args
  args=(--time-period "$period" --granularity DAILY --metrics UnblendedCost --group-by "Type=DIMENSION,Key=SERVICE")
  if [ "$filtered" = 1 ]; then
    args+=(--filter "$CE_FILTER")
  fi
  CE_RESULT=""
  CE_ERROR=""
  while :; do
    page_args=("${args[@]}")
    if [ -n "$token" ]; then
      page_args+=(--next-page-token "$token")
    fi
    CE_REQUESTS=$((CE_REQUESTS + 1))
    pages=$((pages + 1))
    case $kind in
      owner)
        if ! out=$(_LAB_REGION=us-east-1 aws_owner ce get-cost-and-usage ${page_args[@]+"${page_args[@]}"} 2>&1); then
          CE_ERROR=$out
          case $out in
            *AccessDeniedException* | *"not authorized"*) return 1 ;;
          esac
          return 2
        fi
        ;;
      recipient)
        if ! out=$(_LAB_REGION=us-east-1 aws_recipient ce get-cost-and-usage ${page_args[@]+"${page_args[@]}"} 2>&1); then
          CE_ERROR=$out
          case $out in
            *AccessDeniedException* | *"not authorized"*) return 1 ;;
          esac
          return 2
        fi
        ;;
    esac
    if ! printf '%s' "$out" | jq -e 'type == "object"' >/dev/null 2>&1; then
      CE_ERROR="the response was not JSON"
      return 2
    fi
    CE_RESULT="$CE_RESULT$(printf '%s' "$out" | jq -c '.')"$'\n'
    token=$(printf '%s' "$out" | jq -r '.NextPageToken // empty')
    if [ -z "$token" ]; then
      return 0
    fi
    if [ "$pages" -ge 10 ]; then
      CE_ERROR="more than 10 result pages; stopping to limit the per-request charge"
      return 2
    fi
  done
}

# denied_command KIND FILTERED: the full command a reader can re-run with other credentials.
denied_command() {
  local kind=$1 filtered=$2 profile cmd
  if [ "$kind" = owner ]; then
    profile=$LAB_OWNER_PROFILE
  else
    profile=$LAB_RECIPIENT_PROFILE
  fi
  cmd="aws ce get-cost-and-usage --profile $profile --region us-east-1 --output json --time-period Start=$CE_START,End=$CE_END --granularity DAILY --metrics UnblendedCost --group-by Type=DIMENSION,Key=SERVICE"
  if [ "$filtered" = 1 ]; then
    cmd="$cmd --filter '$CE_FILTER'"
  fi
  printf '%s' "$cmd"
}

# cost_table: print the per-service totals of CE_RESULT.
cost_table() {
  local rows
  rows=$(printf '%s' "$CE_RESULT" | jq -rs '
    [.[].ResultsByTime[]?.Groups[]?]
    | group_by(.Keys[0])
    | map({service: .[0].Keys[0],
           amount: (map(.Metrics.UnblendedCost.Amount | tonumber) | add),
           unit: (.[0].Metrics.UnblendedCost.Unit // "USD")})
    | .[] | "    \(.service)  \((.amount * 100 | round) / 100) \(.unit)"')
  if [ -z "$rows" ]; then
    echo "    (no rows)"
  else
    printf '%s\n' "$rows"
  fi
}

cost_account() {
  local kind=$1 label=$2 filtered rc
  for filtered in 1 0; do
    if [ "$filtered" = 1 ]; then
      echo "  $label account, filtered by tag Project=$LAB_TAG:"
    else
      echo "  $label account, all services (not filtered; includes anything that is not part of the lab):"
    fi
    rc=0
    cost_read "$kind" "$filtered" || rc=$?
    case $rc in
      0) cost_table ;;
      1)
        check_warn E26 "Cost Explorer denied access for the $label profile; this is not a failure of the lab. Re-run the command below with credentials that may call ce:GetCostAndUsage (for example the management account):"
        denied_command "$kind" "$filtered"
        echo
        return 0
        ;;
      *)
        check_fail E26 "Cost Explorer call failed for the $label profile: $(error_code_of "$CE_ERROR")"
        return 0
        ;;
    esac
  done
  if [ "$rc" = 0 ]; then
    check_pass E26 "Cost Explorer answered for the $label profile (values only; whether the tag filter covers every lab cost is not yet run on real environment)"
  fi
}

run_cost() {
  local dates
  if ! dates=$(lab_py cost-dates ${SINCE:+--since "$SINCE"} --record "$LAB_ROOT/lab-run.local.jsonl" --now "$(now)" 2>&1); then
    die_usage "no start date for --cost: pass --since YYYY-MM-DD or run another lab script first (${dates#error: })"
  fi
  CE_START=$(printf '%s' "$dates" | jq -r '.start')
  CE_END=$(printf '%s' "$dates" | jq -r '.end')
  CE_FILTER=$(jq -cn --arg tag "$LAB_TAG" '{Tags: {Key: "Project", Values: [$tag]}}')
  assert_account owner
  assert_account recipient
  echo "=== Cost (period $CE_START to $CE_END, end date exclusive) ==="
  echo "  These are Cost Explorer values, not an invoice. They may lag: the documentation says Cost Explorer refreshes at least"
  echo "  once every 24 hours and some data can arrive later. Values filtered by tag stay empty or 0 until Project is active as a"
  echo "  cost allocation tag (activation time not confirmed)."
  echo "  The Cost Explorer API is charged per request. This run sends at least 4 requests (2 accounts x 2 reads) and one more"
  echo "  for each extra result page. Documented as USD 0.01 per paginated request ($CE_DOC_URL, read in full 2026-10-11); the"
  echo "  price is not re-checked here, so confirm it before relying on it."
  cost_account owner owner
  cost_account recipient recipient
  echo "  Cost Explorer API requests sent by this run: $CE_REQUESTS (a request that failed may be charged too: not confirmed)."
  echo "  Whether the Project tag filter covers costs without that tag (for example stored copies in the air-gapped vault) is"
  echo "  not yet run on real environment: compare the filtered and unfiltered tables."
}

# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------

# shared_row JSON: the rows of the lab vault in a shared-vault list, as a JSON array.
shared_rows() {
  printf '%s' "$1" | jq -c --arg n "$LAB_LAG_VAULT_NAME" '[.BackupVaultList[]? | select(.BackupVaultName == $n)]'
}

check_v1() {
  local region=$1 shared rows count acct type state recs
  if ! shared=$(aws_recipient backup list-backup-vaults --by-shared); then
    check_fail V1 "[$region] the recipient's shared-vault list could not be read"
    return 0
  fi
  rows=$(shared_rows "$shared")
  count=$(printf '%s' "$rows" | jq -r 'length')
  echo "  [$region] V1 expected: one vault named $LAB_LAG_VAULT_NAME, ARN account = owner account, VaultType = LOGICALLY_AIR_GAPPED_BACKUP_VAULT"
  if [ "$count" != 1 ]; then
    echo "  [$region] V1 measured: rows=$count"
    check_fail V1 "[$region] the recipient's shared-vault list holds $count rows named $LAB_LAG_VAULT_NAME, expected exactly 1"
    return 0
  fi
  acct=$(printf '%s' "$rows" | jq -r '.[0].BackupVaultArn // "" | split(":")[4] // "absent"')
  type=$(printf '%s' "$rows" | jq -r '.[0].VaultType // "absent"')
  state=$(printf '%s' "$rows" | jq -r '.[0].VaultState // "absent"')
  recs=$(printf '%s' "$rows" | jq -r '.[0].NumberOfRecoveryPoints // "absent"')
  echo "  [$region] V1 measured: ARN account=$acct, VaultType=$type, VaultState=$state, NumberOfRecoveryPoints=$recs"
  if [ "$acct" = "$LAB_OWNER_ACCOUNT_ID" ] && [ "$type" = LOGICALLY_AIR_GAPPED_BACKUP_VAULT ]; then
    check_pass V1 "[$region] the shared vault is listed for the recipient with the owner account and the air-gapped type"
  else
    check_fail V1 "[$region] the shared vault row does not match: account=$acct (owner $LAB_OWNER_ACCOUNT_ID), VaultType=$type"
  fi
  # These two fields are observations, not a contract: a difference is a warning.
  if [ "$state" != absent ] || { [ "$recs" != absent ] && [ "$recs" != 0 ]; }; then
    check_warn V1 "[$region] the shared-list row shows VaultState=$state and NumberOfRecoveryPoints=$recs; compare with the reference section of docs/verification-record.md (a difference is not a failure)"
  fi
}

check_v2() {
  local region=$1 shared count
  if ! shared=$(aws_owner backup list-backup-vaults --by-shared); then
    check_fail V2 "[$region] the owner's shared-vault list could not be read"
    return 0
  fi
  count=$(printf '%s' "$shared" | jq -r '[.BackupVaultList[]?] | length')
  echo "  [$region] V2 expected: an empty list (the list shows what other accounts share with the owner) / measured: rows=$count"
  if [ "$count" = 0 ]; then
    check_pass V2 "[$region] the owner's shared-vault list is empty"
  else
    check_fail V2 "[$region] the owner's shared-vault list holds $count rows, expected none"
  fi
}

check_v4() {
  local region=$1 out code rows count first_rp
  echo "  [$region] V4 expected: without --backup-vault-account-id the call is refused with AccessDeniedException; with it, the call succeeds"
  if out=$(aws_recipient backup list-recovery-points-by-backup-vault --backup-vault-name "$LAB_LAG_VAULT_NAME" 2>&1); then
    echo "  [$region] V4 measured: without the account id the call succeeded"
    check_fail V4 "[$region] listing recovery points WITHOUT --backup-vault-account-id succeeded; it was expected to be refused with AccessDeniedException"
  else
    code=$(error_code_of "$out")
    echo "  [$region] V4 measured: without the account id the call returned $code"
    if [ "$code" = AccessDeniedException ]; then
      check_pass V4 "[$region] the call without --backup-vault-account-id was refused with AccessDeniedException"
    else
      check_fail V4 "[$region] the call without --backup-vault-account-id returned $code, expected AccessDeniedException"
    fi
  fi
  if ! out=$(aws_recipient backup list-recovery-points-by-backup-vault --backup-vault-name "$LAB_LAG_VAULT_NAME" --backup-vault-account-id "$LAB_OWNER_ACCOUNT_ID" 2>&1); then
    echo "  [$region] V4 measured: with the account id the call returned $(error_code_of "$out")"
    check_fail V4 "[$region] listing recovery points WITH --backup-vault-account-id failed ($(error_code_of "$out"))"
    return 0
  fi
  rows=$(printf '%s' "$out" | jq -c '[.RecoveryPoints[]?]')
  count=$(printf '%s' "$rows" | jq -r 'length')
  echo "  [$region] V4 measured: with the account id the call succeeded, recovery points=$count"
  check_pass V4 "[$region] the call with --backup-vault-account-id succeeded"
  if [ "$count" = 0 ]; then
    check_warn - "[$region] no recovery point is listed in the shared vault yet (run 04_backup_and_copy.sh and wait for the copy to finish)"
    return 0
  fi
  # Recovery points after the copy: ARN form, restore metadata, delete date.
  local bad
  bad=$(printf '%s' "$rows" | jq -r --arg o "$LAB_OWNER_ACCOUNT_ID" --arg r "$region" \
    '[.[] | select((.RecoveryPointArn // "") | startswith("arn:aws:backup:" + $r + ":" + $o + ":recovery-point:") | not)] | length')
  if [ "$bad" = 0 ]; then
    check_pass V4 "[$region] every recovery point ARN has the form arn:aws:backup:$region:<owner account>:recovery-point:<id>"
  else
    check_fail V4 "[$region] $bad recovery point ARN(s) do not have the expected cross-account form"
  fi
  first_rp=$(printf '%s' "$rows" | jq -r '.[0].RecoveryPointArn')
  if aws_recipient backup get-recovery-point-restore-metadata --backup-vault-name "$LAB_LAG_VAULT_NAME" --recovery-point-arn "$first_rp" --backup-vault-account-id "$LAB_OWNER_ACCOUNT_ID" >/dev/null; then
    check_pass V7 "[$region] the recipient can read the restore metadata of $first_rp"
  else
    check_fail V7 "[$region] the recipient could not read the restore metadata of $first_rp"
  fi
  # BackupSizeInBytes is not checked: it can be 0 for these backups.
  local delete_at
  delete_at=$(printf '%s' "$rows" | jq -r '.[0].CalculatedLifecycle.DeleteAt // empty')
  if [ -z "$delete_at" ]; then
    check_warn E5 "[$region] the recovery point reports no delete date"
  else
    echo "  [$region] delete date measured: $delete_at (expected: creation time of the source backup + the vault retention; compare with the 04 output)"
  fi
}

# fs_hours KIND LABEL FS_ID: how long a lab file system has been billed (display only).
fs_hours() {
  local kind=$1 label=$2 fs_id=$3 out created minutes
  case $kind in
    owner) out=$(aws_owner fsx describe-file-systems --file-system-ids "$fs_id") || out="" ;;
    recipient) out=$(aws_recipient fsx describe-file-systems --file-system-ids "$fs_id") || out="" ;;
  esac
  created=$(printf '%s' "$out" | jq -r '.FileSystems[0].CreationTime // empty' 2>/dev/null || true)
  if [ -z "$created" ]; then
    check_warn - "the $label file system $fs_id could not be read"
    return 0
  fi
  minutes=$(lab_py age-minutes --from "$created" --now "$(now)")
  check_warn - "the $label file system $fs_id has existed for $((minutes / 60)) hours; it is billed until 10_teardown.sh deletes it"
}

# running_cost REGION: the lab file systems of one Region (display only).
running_cost() {
  local region=$1 json fs_id existing
  if [ "$region" = "$LAB_PRIMARY_REGION" ]; then
    if json=$(describe_stack owner "${LAB_TAG}-owner-base"); then
      fs_id=$(stack_value "$json" Outputs FileSystemId)
      if [ -n "$fs_id" ]; then
        fs_hours owner owner "$fs_id"
      fi
    fi
  fi
  if [ "$region" = "$LAB_PRIMARY_REGION" ]; then
    existing=${LAB_RECIPIENT_EXISTING_FS_ID:-}
  else
    existing=${LAB_SECOND_RECIPIENT_EXISTING_FS_ID:-}
  fi
  # A file system the lab did not create is not billed to the lab.
  if [ -z "$existing" ] && json=$(describe_stack recipient "${LAB_TAG}-recipient-${region}"); then
    fs_id=$(stack_value "$json" Outputs FileSystemId)
    if [ -n "$fs_id" ]; then
      fs_hours recipient recipient "$fs_id"
    fi
  fi
}

if [ "$COST" = 1 ]; then
  run_cost
  if summary; then
    exit 0
  fi
  exit 1
fi

assert_account owner
assert_account recipient
for region in $REGION_LIST; do
  lab_region_set "$region"
  echo "Region $region"
  check_v1 "$region"
  check_v2 "$region"
  check_v4 "$region"
  running_cost "$region"
done
lab_region_set ""
if summary; then
  exit 0
fi
exit 1
