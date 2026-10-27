#!/bin/bash
# Real-environment run: recorded [V1][V2][V4]; not recorded [V3][V5][V6][V7][E13] (status source: docs/verification-record.md)
#
# 04_backup_and_copy.sh - back up the lab volume, then copy the backup into the
# air-gapped vault.
#
# Usage:
#   04_backup_and_copy.sh [--phase backup|copy|all] [--retention-days N]
#                         [--region REGION] [--source-recovery-point-arn ARN]
#                         [--apply [--confirm TOKEN]]
#
#   --phase backup   on-demand backup into the standard vault only. Reversible
#                    (it expires on its own), so no token is needed.
#   --phase copy     copy an existing backup into the air-gapped vault.
#   --phase all      both (default). The token is checked BEFORE the backup starts.
#   --retention-days N   required for copy and all. Must equal the retention the
#                    destination vault was created with (03); the copy is kept for
#                    N days from the creation of its SOURCE backup.
#   --region         limit the copy to one destination Region. The backup is always
#                    taken in the primary Region. Default: every configured Region.
#   --source-recovery-point-arn   pick the source when the standard vault holds
#                    more than one recovery point of the volume.
#   --apply          run. Without it the script prints the plan and exits 10.
#   --confirm TOKEN  copy-<N>d-<vault>@<regions>, printed in the plan. Accepted
#                    only as an argument, never from the environment.
#
# The copy is IRREVERSIBLE: the destination vault cannot be deleted while it holds
# the copy, and the copy cannot be removed before its retention ends.
#
# Region rules: the backup and the copy are both SENT to the primary Region (the
# copy names its destination by the vault ARN); the destination vault and the
# copies there are read in the destination Region. Sending the copy to the source
# Region follows from the shape of the API and is not yet run on real environment.
#
# Before the copy starts, three reads look for an existing copy: the destination
# Region's recovery points of this volume, the copy jobs in progress in the primary
# and destination Regions, and earlier failed jobs (for the idempotency token). If
# any read fails the state is UNKNOWN and nothing is copied.
#
# Exit codes: 0 success, 1 failure or refusal, 2 usage error, 10 plan only.

set -euo pipefail
# shellcheck source-path=SCRIPTDIR
# shellcheck source=lib/common.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

usage() {
  cat <<'EOF'
Usage: 04_backup_and_copy.sh [--phase backup|copy|all] [--retention-days N] [--region R]
                             [--source-recovery-point-arn ARN] [--apply [--confirm TOKEN]]
Backs up the lab volume and copies the backup into the air-gapped vault (irreversible). Without --apply only the plan is shown (exit 10).
EOF
}

PHASE=all
RET=""
REGION_ARG=""
SRC_ARG=""
while [ "$#" -gt 0 ]; do
  case $1 in
    --phase)
      if [ "$#" -lt 2 ]; then
        die_usage "--phase needs backup, copy or all"
      fi
      PHASE=$2
      shift 2
      ;;
    --retention-days)
      if [ "$#" -lt 2 ]; then
        die_usage "--retention-days needs a value (7 to 35)"
      fi
      RET=$2
      shift 2
      ;;
    --region)
      if [ "$#" -lt 2 ]; then
        die_usage "--region needs a value"
      fi
      REGION_ARG=$2
      shift 2
      ;;
    --source-recovery-point-arn)
      if [ "$#" -lt 2 ]; then
        die_usage "--source-recovery-point-arn needs an ARN"
      fi
      SRC_ARG=$2
      shift 2
      ;;
    --apply)
      lab_apply_on
      shift
      ;;
    --confirm)
      if [ "$#" -lt 2 ]; then
        die_usage "--confirm needs a value"
      fi
      lab_confirm_set "$2"
      shift 2
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *) die_usage "unknown argument: $1" ;;
  esac
done
case $PHASE in
  backup | copy | all) ;;
  *) die_usage "--phase must be backup, copy or all" ;;
esac
if [ "$PHASE" != backup ]; then
  if [ -z "$RET" ]; then
    die_usage "--retention-days is required for --phase $PHASE (integer 7 to 35)"
  fi
  validate_retention_days "$RET"
elif [ -n "$RET" ]; then
  validate_retention_days "$RET"
fi
if [ -n "$SRC_ARG" ]; then
  validate_arn "--source-recovery-point-arn" "$SRC_ARG" fsx
fi
if [ -n "$REGION_ARG" ]; then
  validate_region_arg "$REGION_ARG"
  REGION_LIST=$REGION_ARG
else
  REGION_LIST=$(lab_regions | tr '\n' ' ' | sed 's/ $//')
fi
# shellcheck disable=SC2086
REGIONS_JOINED=$(lab_join_plus $REGION_LIST)
PRIMARY=$LAB_PRIMARY_REGION

# --------------------------------------------------------------------------
# Readers (every AWS call is a literal call site)
# --------------------------------------------------------------------------

# BASE_JSON: describe-stacks of owner-base in the primary Region, read once.
# base_output KEY: one output of that stack (dies unless there is exactly one value).
BASE_JSON=""
base_output() {
  local value
  if ! value=$(stack_value_one "owner-base output $1" "$BASE_JSON" Outputs "$1"); then exit 1; fi
  printf '%s' "$value"
}

# lag_arn REGION: the ARN of the air-gapped vault of a Region, from its stack output.
lag_arn() {
  local json value
  lab_region_set "$1"
  if ! json=$(aws_owner cloudformation describe-stacks --stack-name "${LAB_TAG}-lag-$1"); then
    die "stack ${LAB_TAG}-lag-$1 could not be read in $1; run 03_deploy_lag_share.sh first"
  fi
  if ! value=$(stack_value_one "air-gapped vault ARN in $1" "$json" Outputs LagVaultArn); then exit 1; fi
  lab_region_set "$PRIMARY"
  printf '%s' "$value"
}

# find_source: set SRC_RP and SRC_CREATED from the standard vault (primary Region).
# Several recovery points of the volume are an error unless --source-recovery-point-arn names one.
SRC_RP=""
SRC_CREATED=""
find_source() {
  local list rows
  lab_region_set "$PRIMARY"
  if ! list=$(aws_owner backup list-recovery-points-by-backup-vault --backup-vault-name "$STD_VAULT" --by-resource-arn "$VOLUME_ARN"); then
    die "recovery points of $STD_VAULT could not be listed: the source state is unknown, nothing was changed"
  fi
  rows=$(printf '%s' "$list" | jq -c --arg pick "$SRC_ARG" \
    '[.RecoveryPoints[]? | select(.Status == "COMPLETED") | select($pick == "" or .RecoveryPointArn == $pick)]')
  SRC_RP=""
  SRC_CREATED=""
  case $(printf '%s' "$rows" | jq -r 'length') in
    0)
      if [ -n "$SRC_ARG" ]; then
        die "$SRC_ARG is not a COMPLETED recovery point of the lab volume in $STD_VAULT"
      fi
      ;;
    1)
      SRC_RP=$(printf '%s' "$rows" | jq -r '.[0].RecoveryPointArn')
      SRC_CREATED=$(printf '%s' "$rows" | jq -r '.[0].CreationDate')
      ;;
    *)
      printf '%s' "$rows" | jq -r '.[] | "  \(.RecoveryPointArn) created \(.CreationDate)"' >&2
      echo "  Pass one of them with --source-recovery-point-arn." >&2
      require_one "source recovery point" "$(printf '%s' "$rows" | jq -c '[.[].RecoveryPointArn]')" >/dev/null
      exit 1
      ;;
  esac
}

# check_source_key: the source recovery point must be encrypted with the lab key;
# a recovery point of another key is never copied into an air-gapped vault.
check_source_key() {
  local described key
  lab_region_set "$PRIMARY"
  if ! described=$(aws_owner backup describe-recovery-point --backup-vault-name "$STD_VAULT" --recovery-point-arn "$SRC_RP"); then
    die "the source recovery point could not be described: nothing was changed"
  fi
  key=$(printf '%s' "$described" | jq -r '.EncryptionKeyArn // "none"')
  if [ "$key" != "$KEY_ARN" ]; then
    die "the source recovery point is encrypted with $key, not the lab key $KEY_ARN; it will not be copied into an air-gapped vault. Nothing was changed."
  fi
}

# --------------------------------------------------------------------------
# Context
# --------------------------------------------------------------------------
assert_account owner
require_sso_minutes "$LAB_OWNER_PROFILE" "$LAB_MIN_SSO_MINUTES"
lab_region_set "$PRIMARY"
if ! BASE_JSON=$(aws_owner cloudformation describe-stacks --stack-name "${LAB_TAG}-owner-base"); then
  die "stack ${LAB_TAG}-owner-base could not be read; run 02_deploy.sh --side owner --apply first"
fi
VOLUME_ARN=$(base_output VolumeArn)
ROLE_ARN=$(base_output BackupRoleArn)
KEY_ARN=$(base_output KeyArn)
STD_VAULT=$(base_output StandardVaultName)
if [ "$PHASE" != backup ]; then
  # Destination vaults: ARN, state and the retention they were created with.
  DEST_ARNS=""
  for region in $REGION_LIST; do
    arn=$(lag_arn "$region")
    DEST_ARNS="$DEST_ARNS $region=$arn"
    lab_region_set "$region"
    if ! vault=$(aws_owner backup describe-backup-vault --backup-vault-name "$LAB_LAG_VAULT_NAME"); then
      die "air-gapped vault $LAB_LAG_VAULT_NAME could not be read in $region: nothing was changed"
    fi
    if [ "$(printf '%s' "$vault" | jq -r '.VaultState // "UNKNOWN"')" != AVAILABLE ]; then
      die "air-gapped vault $LAB_LAG_VAULT_NAME is not AVAILABLE in $region: nothing was changed"
    fi
    vmin=$(printf '%s' "$vault" | jq -r '.MinRetentionDays // "unknown"')
    vmax=$(printf '%s' "$vault" | jq -r '.MaxRetentionDays // "unknown"')
    if [ "$vmin" != "$RET" ] || [ "$vmax" != "$RET" ]; then
      die "--retention-days $RET differs from the vault's retention in $region (minimum $vmin, maximum $vmax); the vault decides the real expiry. Nothing was changed."
    fi
  done
  lab_region_set "$PRIMARY"
fi
find_source
if [ "$PHASE" = copy ] && [ -z "$SRC_RP" ]; then
  die "no COMPLETED recovery point of the lab volume in $STD_VAULT; run --phase backup --apply first"
fi
if [ -n "$SRC_RP" ] && [ "$PHASE" != backup ]; then
  check_source_key
fi

# --------------------------------------------------------------------------
# Plan
# --------------------------------------------------------------------------
cmd_suffix=""
if [ -n "$REGION_ARG" ]; then
  cmd_suffix=" --region $REGION_ARG"
fi
if [ -n "$SRC_ARG" ]; then
  cmd_suffix="$cmd_suffix --source-recovery-point-arn $SRC_ARG"
fi
TOKEN=""
if [ "$PHASE" != backup ]; then
  TOKEN="copy-${RET}d-${LAB_LAG_VAULT_NAME}@${REGIONS_JOINED}"
fi

impact_begin
if [ "$PHASE" = backup ]; then
  if [ -n "$SRC_RP" ]; then
    impact "source recovery point" "$SRC_RP already exists (created $SRC_CREATED); no new backup is started"
  else
    impact "source recovery point" "a new on-demand backup of $VOLUME_ARN into $STD_VAULT"
  fi
  impact "expires in" "$LAB_SOURCE_BACKUP_RETENTION_DAYS days (the backup removes itself; this phase is reversible and needs no token)"
else
  if [ -n "$SRC_RP" ]; then
    impact "source recovery point" "$SRC_RP (created $SRC_CREATED)"
  else
    impact "source recovery point" "a new on-demand backup of $VOLUME_ARN will be taken first; its ARN is not known until it completes"
  fi
  for entry in $DEST_ARNS; do
    impact "destination vault" "${entry#*=} (Region ${entry%%=*})"
  done
  if [ -n "$SRC_RP" ]; then
    impact "expected earliest deletion" "$(lab_py add-days --from "$SRC_CREATED" --days "$RET") = source creation + $RET days (observed once in a past run; not copy completion; not yet run on real environment)"
  else
    impact "expected earliest deletion" "not known until the backup completes. It will be source creation time + $RET days; about $(lab_py add-days --from "$(now)" --days "$RET") if the backup starts now (today + $RET days, UTC)"
  fi
  impact "cannot delete vault" "the destination vault cannot be deleted while it holds the copy, and the copy cannot be removed before it expires"
  impact "source KMS key" "$KEY_ARN: whether deleting it early affects the copy is untested; this lab keeps it, and 10_teardown.sh will not delete it before the copy expires"
  impact "cost" "air-gapped vault storage price is not confirmed (see the cost section of docs/procedure.md)"
fi
if [ "$PHASE" = backup ]; then
  plan_gate "./scripts/04_backup_and_copy.sh --phase backup${cmd_suffix} --apply"
else
  irreversible_gate "$TOKEN" "./scripts/04_backup_and_copy.sh --phase $PHASE --retention-days ${RET}${cmd_suffix} --apply --confirm $TOKEN"
fi

# --------------------------------------------------------------------------
# Backup
# --------------------------------------------------------------------------
BACKUP_STATE=""
BACKUP_MESSAGE=""
# shellcheck disable=SC2329,SC2317  # invoked through wait_until
poll_backup_job() {
  local out
  out=$(aws_owner backup describe-backup-job --backup-job-id "$BACKUP_JOB_ID") || return 2
  BACKUP_STATE=$(printf '%s' "$out" | jq -r '.State // "UNKNOWN"')
  BACKUP_MESSAGE=$(printf '%s' "$out" | jq -r '.StatusMessage // empty')
  case $BACKUP_STATE in
    CREATED | PENDING | RUNNING | AGGREGATE_RUNNING) return 1 ;;
    *) return 0 ;;
  esac
}

if [ "$PHASE" != copy ]; then
  lab_region_set "$PRIMARY"
  if [ -n "$SRC_RP" ]; then
    check_pass - "a recovery point of the lab volume already exists in $STD_VAULT: no new backup is started"
  else
    backup_token=$(lab_py text-digest "$VOLUME_ARN" "$STD_VAULT" "$(now)")
    if ! start_out=$(aws_owner backup start-backup-job \
      --backup-vault-name "$STD_VAULT" \
      --resource-arn "$VOLUME_ARN" \
      --iam-role-arn "$ROLE_ARN" \
      --lifecycle "DeleteAfterDays=$LAB_SOURCE_BACKUP_RETENTION_DAYS" \
      --idempotency-token "$backup_token"); then
      die "backup start-backup-job failed"
    fi
    if ! BACKUP_JOB_ID=$(require_one "backup job id" "$(printf '%s' "$start_out" | jq -c '.BackupJobId')"); then exit 1; fi
    record_event backup_started - "$BACKUP_JOB_ID"
    if ! wait_until "backup job $BACKUP_JOB_ID" 1800 30 poll_backup_job; then
      die "backup job $BACKUP_JOB_ID did not finish within 30 minutes (nothing was copied)"
    fi
    if [ "$BACKUP_STATE" != COMPLETED ]; then
      check_fail - "backup job $BACKUP_JOB_ID ended in $BACKUP_STATE: ${BACKUP_MESSAGE:-no message}"
      summary || true
      exit 1
    fi
    check_pass - "backup job $BACKUP_JOB_ID COMPLETED"
    find_source
    if [ -z "$SRC_RP" ]; then
      die "the backup completed but no COMPLETED recovery point of the volume is listed in $STD_VAULT"
    fi
    if [ "$PHASE" = all ]; then
      check_source_key
    fi
  fi
fi

# --------------------------------------------------------------------------
# Copy
# --------------------------------------------------------------------------
COPY_STATE=""
COPY_MESSAGE=""
COPY_DEST_RP=""
# shellcheck disable=SC2329,SC2317  # invoked through wait_until
poll_copy_job() {
  local out
  out=$(aws_owner backup describe-copy-job --copy-job-id "$COPY_JOB_ID") || return 2
  COPY_STATE=$(printf '%s' "$out" | jq -r '.CopyJob.State // "UNKNOWN"')
  COPY_MESSAGE=$(printf '%s' "$out" | jq -r '.CopyJob.StatusMessage // empty')
  COPY_DEST_RP=$(printf '%s' "$out" | jq -r '.CopyJob.DestinationRecoveryPointArn // empty')
  case $COPY_STATE in
    CREATED | RUNNING) return 1 ;;
    *) return 0 ;;
  esac
}

# unknown_abort WHAT: the state is not known, so nothing is copied.
unknown_abort() {
  die "UNKNOWN: $1; copy state cannot be established, so no copy was started" 1
}

# existing_copy_state REGION DEST_ARN: sets COPY_FOUND (1 when a copy exists),
# FAILED_COUNT; dies as UNKNOWN when any of the reads fails.
COPY_FOUND=0
FAILED_COUNT=0
existing_copy_state() {
  local region=$1 dest=$2 rps primary_jobs dest_jobs state jobs busy
  COPY_FOUND=0
  FAILED_COUNT=0
  # (a) recovery points of this volume already in the destination vault
  lab_region_set "$region"
  if ! rps=$(aws_owner backup list-recovery-points-by-backup-vault --backup-vault-name "$LAB_LAG_VAULT_NAME" --by-resource-arn "$VOLUME_ARN"); then
    unknown_abort "the recovery points of $LAB_LAG_VAULT_NAME in $region could not be listed"
  fi
  if [ "$(printf '%s' "$rps" | jq -r '[.RecoveryPoints[]?] | length')" != 0 ]; then
    COPY_FOUND=1
  fi
  # (b) copy jobs in progress, read in the source Region and in the destination Region
  busy=""
  for state in CREATED RUNNING; do
    lab_region_set "$PRIMARY"
    if ! primary_jobs=$(aws_owner backup list-copy-jobs --by-state "$state"); then
      unknown_abort "the $state copy jobs in $PRIMARY could not be listed"
    fi
    busy="$busy $(printf '%s' "$primary_jobs" | jq -r --arg d "$dest" '[.CopyJobs[]? | select(.DestinationBackupVaultArn == $d) | .CopyJobId] | join(" ")')"
    if [ "$region" != "$PRIMARY" ]; then
      lab_region_set "$region"
      if ! dest_jobs=$(aws_owner backup list-copy-jobs --by-state "$state"); then
        unknown_abort "the $state copy jobs in $region could not be listed"
      fi
      busy="$busy $(printf '%s' "$dest_jobs" | jq -r --arg d "$dest" '[.CopyJobs[]? | select(.DestinationBackupVaultArn == $d) | .CopyJobId] | join(" ")')"
    fi
  done
  busy=$(printf '%s' "$busy" | tr -s ' ' | sed 's/^ //;s/ $//')
  if [ -n "$busy" ]; then
    die "a copy job into $LAB_LAG_VAULT_NAME is already in progress ($busy); wait for it, then run this again (it will find the finished copy and skip)"
  fi
  # (c) earlier jobs of this source and destination, for the idempotency token
  lab_region_set "$PRIMARY"
  if ! jobs=$(aws_owner backup list-copy-jobs --by-source-recovery-point-arn "$SRC_RP"); then
    unknown_abort "the earlier copy jobs of the source recovery point could not be listed"
  fi
  FAILED_COUNT=$(printf '%s' "$jobs" | jq -r --arg d "$dest" \
    '[.CopyJobs[]? | select(.DestinationBackupVaultArn == $d and (.State == "FAILED" or .State == "PARTIAL"))] | length')
}

if [ "$PHASE" != backup ]; then
  for entry in $DEST_ARNS; do
    region=${entry%%=*}
    dest=${entry#*=}
    existing_copy_state "$region" "$dest"
    if [ "$COPY_FOUND" = 1 ]; then
      check_pass - "the vault $LAB_LAG_VAULT_NAME in $region already holds a recovery point of this volume: no second copy is started"
      continue
    fi
    copy_token=$(lab_py text-digest "$SRC_RP" "$dest" "$RET")
    if [ "$FAILED_COUNT" != 0 ]; then
      copy_token="${copy_token}-r${FAILED_COUNT}"
    fi
    lab_region_set "$PRIMARY"
    if ! copy_out=$(aws_owner backup start-copy-job \
      --recovery-point-arn "$SRC_RP" \
      --source-backup-vault-name "$STD_VAULT" \
      --destination-backup-vault-arn "$dest" \
      --iam-role-arn "$ROLE_ARN" \
      --lifecycle "DeleteAfterDays=$RET" \
      --idempotency-token "$copy_token"); then
      die "backup start-copy-job failed for the destination in $region"
    fi
    if ! COPY_JOB_ID=$(require_one "copy job id" "$(printf '%s' "$copy_out" | jq -c '.CopyJobId')"); then exit 1; fi
    record_event copy_started E7 "$COPY_JOB_ID token=$copy_token"
    if ! wait_until "copy job $COPY_JOB_ID" 3600 60 poll_copy_job; then
      die "copy job $COPY_JOB_ID did not finish within 60 minutes; check it with: aws backup describe-copy-job --copy-job-id $COPY_JOB_ID --region $PRIMARY"
    fi
    if [ "$COPY_STATE" != COMPLETED ]; then
      check_fail E4 "copy job $COPY_JOB_ID into $region ended in $COPY_STATE: ${COPY_MESSAGE:-no message}"
      continue
    fi
    check_pass E4 "copy job $COPY_JOB_ID into $region COMPLETED"
    if [ -n "$COPY_MESSAGE" ]; then
      check_warn E10 "copy job $COPY_JOB_ID completed with a status message ('Completed with issues'?): $COPY_MESSAGE"
    else
      check_pass E10 "copy job $COPY_JOB_ID completed without a status message"
    fi
    if [ -n "$COPY_DEST_RP" ]; then
      lab_region_set "$region"
      if dest_rp=$(aws_owner backup describe-recovery-point --backup-vault-name "$LAB_LAG_VAULT_NAME" --recovery-point-arn "$COPY_DEST_RP"); then
        delete_at=$(printf '%s' "$dest_rp" | jq -r '.CalculatedLifecycle.DeleteAt // empty')
        expected=$(lab_py add-days --from "$SRC_CREATED" --days "$RET")
        if [ -z "$delete_at" ]; then
          check_warn E5 "the copy in $region reports no delete date"
        elif [ "$(lab_py add-days --from "$delete_at" --days 0)" = "$expected" ]; then
          check_pass E5 "the copy in $region will be deleted at $expected (source creation + $RET days)"
        else
          check_warn E5 "the copy in $region will be deleted at $delete_at, not at $expected (source creation + $RET days)"
        fi
      else
        check_warn E5 "the copy in $region could not be described to confirm its delete date"
      fi
    fi
  done
fi
lab_region_set ""
if summary; then
  exit 0
fi
exit 1
