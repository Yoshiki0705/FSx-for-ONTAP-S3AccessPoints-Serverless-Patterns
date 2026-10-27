#!/bin/bash
# Real-environment run: recorded [V1][V2][V4]; not recorded [V3][V5][V6][V7][E13] (status source: docs/verification-record.md)
#
# 08_restore.sh - the recipient restores the shared recovery point as a NEW volume in
# its own file system (item V7).
#
# Usage:
#   08_restore.sh [--region REGION] [--via cli|portal] [--apply]
#
#   --region   Region of the recovery point and of the restore target. Default: the
#              primary Region only (a restore is done one Region at a time). Use the
#              second Region to restore a copy that was made there.
#   --via cli     start the job with the AWS Backup API (default).
#   --via portal  call the deployed portal restore function (startRestore with
#                 acknowledgeIrreversible=true, then describeRestore). The portal
#                 function acts in the primary Region, so --region is not allowed.
#   --apply    restore. Without it the script prints the plan and exits 10.
#
# What it reads first: the recipient stack outputs (restore role, restore SVM, file
# system), the SVM list of the file system, the recovery points of the shared vault
# (read with the owner account id; exactly one must be COMPLETED) and the restore
# metadata of that recovery point. The metadata sent to AWS Backup is built by
# lab_helpers.py restore-metadata: keys start with a lower-case letter, and the
# source file system id, volume id, lifecycle and volume type are not copied.
#
# Waiting: the script follows the job status AND the lifecycle of the volume. Job
# progress is never used to decide that the volume is ready (the volume can be
# CREATED while the job still reports 0 percent). Done = job COMPLETED and volume
# CREATED. A job that ends FAILED or ABORTED is reported with its message.
#
# After the restore the volume is tagged Project=<LAB_TAG>: a restored volume
# carries no tags. A failed tag call fails the run.
#
# Exit codes: 0 success (a warning is possible), 1 failure or refusal (no or several
# recovery points, restore SVM missing, job FAILED or ABORTED, tag call failed),
# 2 usage error, 10 plan only.
#
# Not yet run on real environment: the restore itself, the metadata AWS Backup
# accepts, the dedicated restore role and the portal path.

set -euo pipefail
# shellcheck source-path=SCRIPTDIR
# shellcheck source=lib/common.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

usage() {
  cat <<'EOF'
Usage: 08_restore.sh [--region R] [--via cli|portal] [--apply]
The recipient restores the shared recovery point as a new volume. Without --apply only the plan is shown (exit 10).
EOF
}

REGION_ARG=""
VIA=cli
while [ "$#" -gt 0 ]; do
  case $1 in
    --region)
      if [ "$#" -lt 2 ]; then
        die_usage "--region needs a value"
      fi
      REGION_ARG=$2
      shift 2
      ;;
    --via)
      if [ "$#" -lt 2 ]; then
        die_usage "--via needs cli or portal"
      fi
      VIA=$2
      shift 2
      ;;
    --apply)
      lab_apply_on
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *) die_usage "unknown argument: $1" ;;
  esac
done
case $VIA in
  cli | portal) ;;
  *) die_usage "--via must be cli or portal" ;;
esac
if [ -n "$REGION_ARG" ]; then
  validate_region_arg "$REGION_ARG"
fi
REGION=${REGION_ARG:-$LAB_PRIMARY_REGION}
if [ "$VIA" = portal ] && [ "$REGION" != "$LAB_PRIMARY_REGION" ]; then
  die_usage "--via portal works in the primary Region only (the portal restore function acts in its own Region; not yet run on real environment for other Regions)"
fi
# The description the portal restore function is deployed with (amplify backend).
PORTAL_RESTORE_DESCRIPTION="Starts an AWS Backup restore job to a new FSx for ONTAP volume (approval-gated write)"

# --------------------------------------------------------------------------
# Context
# --------------------------------------------------------------------------
lab_region_set "$REGION"
assert_account recipient
require_sso_minutes "$LAB_RECIPIENT_PROFILE" "$LAB_MIN_SSO_MINUTES"

STACK="${LAB_TAG}-recipient-${REGION}"
if STACK_JSON=$(describe_stack recipient "$STACK"); then
  :
else
  rc=$?
  if [ "$rc" = 4 ]; then
    die "stack $STACK does not exist in $REGION; run 02_deploy.sh --side recipient --apply first"
  fi
  die "stack $STACK could not be read in $REGION"
fi
if ! ROLE_ARN=$(stack_value_one "recipient-restore RestoreRoleArn" "$STACK_JSON" Outputs RestoreRoleArn); then exit 1; fi
if ! SVM_ID=$(stack_value_one "recipient-restore RestoreSvmId" "$STACK_JSON" Outputs RestoreSvmId); then exit 1; fi
if ! FS_ID=$(stack_value_one "recipient-restore FileSystemId" "$STACK_JSON" Outputs FileSystemId); then exit 1; fi

# The restore creates a volume in the restore SVM; it needs that SVM to exist. When
# it is missing, the SVM limit of the file system tells whether it could be created.
if ! FS_JSON=$(aws_recipient fsx describe-file-systems --file-system-ids "$FS_ID"); then
  die "file system $FS_ID could not be read: nothing was started"
fi
if ! SVMS_JSON=$(aws_recipient fsx describe-storage-virtual-machines --filters "Name=file-system-id,Values=$FS_ID"); then
  die "the SVMs of $FS_ID could not be listed: nothing was started"
fi
SLOTS="unknown"
if budget=$(svm_budget "$FS_JSON" "$SVMS_JSON"); then
  SLOTS="${budget% *} of ${budget#* }"
  SLOTS_FULL=0
  if [ "${budget% *}" -ge "${budget#* }" ]; then
    SLOTS_FULL=1
  fi
else
  rc=$?
  SLOTS_FULL=0
  if [ "$rc" != 3 ]; then
    die "the SVM budget of $FS_ID could not be computed"
  fi
fi
SVM_STATE=$(printf '%s' "$SVMS_JSON" | jq -r --arg id "$SVM_ID" \
  '[.StorageVirtualMachines[]? | select(.StorageVirtualMachineId == $id)][0].Lifecycle // "missing"')
if [ "$SVM_STATE" = missing ]; then
  if [ "$SLOTS_FULL" = 1 ]; then
    die "the restore SVM $SVM_ID is not on file system $FS_ID and the file system has no free SVM slot ($SLOTS used): nothing was started"
  fi
  die "the restore SVM $SVM_ID is not on file system $FS_ID (SVM slots used: $SLOTS); run 02_deploy.sh --side recipient --apply: nothing was started"
fi
if [ "$SVM_STATE" != CREATED ]; then
  die "the restore SVM $SVM_ID is $SVM_STATE, not CREATED: nothing was started"
fi

# Volumes already in the SVM: refuse to restore a second volume with the same name.
if ! VOLS_JSON=$(aws_recipient fsx describe-volumes --filters "Name=storage-virtual-machine-id,Values=$SVM_ID"); then
  die "the volumes of $SVM_ID could not be listed: nothing was started"
fi
if printf '%s' "$VOLS_JSON" | jq -e --arg n "$LAB_RESTORE_VOLUME_NAME" \
  '[.Volumes[]? | select(.Name == $n)] | length > 0' >/dev/null; then
  die "a volume named $LAB_RESTORE_VOLUME_NAME already exists in $SVM_ID; delete it or set LAB_RESTORE_VOLUME_NAME: nothing was started"
fi

# The recovery point: exactly one COMPLETED row, read with the owner account id.
if ! RP_LIST=$(aws_recipient backup list-recovery-points-by-backup-vault --backup-vault-name "$LAB_LAG_VAULT_NAME" --backup-vault-account-id "$LAB_OWNER_ACCOUNT_ID"); then
  die "the recovery points of the shared vault could not be listed in $REGION: nothing was started"
fi
RP_ROWS=$(printf '%s' "$RP_LIST" | jq -c '[.RecoveryPoints[]? | select(.Status == "COMPLETED")]')
if [ "$(printf '%s' "$RP_ROWS" | jq -r 'length')" -gt 1 ]; then
  printf '%s' "$RP_ROWS" | jq -r '.[] | "  \(.RecoveryPointArn) created \(.CreationDate)"' >&2
fi
if ! RP_ARN=$(require_one "COMPLETED recovery point of the shared vault in $REGION" "$(printf '%s' "$RP_ROWS" | jq -c '[.[].RecoveryPointArn]')"); then exit 1; fi

if ! META_RAW=$(aws_recipient backup get-recovery-point-restore-metadata --backup-vault-name "$LAB_LAG_VAULT_NAME" --recovery-point-arn "$RP_ARN" --backup-vault-account-id "$LAB_OWNER_ACCOUNT_ID"); then
  die "the restore metadata of $RP_ARN could not be read: nothing was started"
fi
if ! METADATA=$(printf '%s' "$META_RAW" | lab_py restore-metadata --input - --svm-id "$SVM_ID" --name "$LAB_RESTORE_VOLUME_NAME" --junction-path "$LAB_RESTORE_JUNCTION_PATH"); then
  die "the restore metadata could not be built: nothing was started"
fi
ONTAP_JSON=$(printf '%s' "$METADATA" | jq -r '.OntapConfiguration')
SIZE_MB=$(printf '%s' "$ONTAP_JSON" | jq -r '.sizeInMegabytes // empty')
TOKEN=$(lab_py text-digest "$RP_ARN" "$SVM_ID" "$LAB_RESTORE_VOLUME_NAME")

# Portal path: find the deployed restore function (by name, or by exact description).
PORTAL_FN=""
if [ "$VIA" = portal ]; then
  if [ -n "${LAB_PORTAL_RESTORE_FUNCTION_NAME:-}" ]; then
    PORTAL_FN=$LAB_PORTAL_RESTORE_FUNCTION_NAME
  else
    if ! FN_LIST=$(aws_recipient lambda list-functions); then
      die "lambda list-functions failed: nothing was started"
    fi
    names=$(printf '%s' "$FN_LIST" | jq -c --arg d "$PORTAL_RESTORE_DESCRIPTION" '[.Functions[]? | select(.Description == $d) | .FunctionName]')
    if ! PORTAL_FN=$(require_one "portal restore function (matched by its description)" "$names"); then
      echo "  Set LAB_PORTAL_RESTORE_FUNCTION_NAME to choose one." >&2
      exit 1
    fi
  fi
fi

# --------------------------------------------------------------------------
# Plan
# --------------------------------------------------------------------------
echo "Recovery point : $RP_ARN"
echo "Target         : SVM $SVM_ID on file system $FS_ID in $REGION (volume $LAB_RESTORE_VOLUME_NAME, junction $LAB_RESTORE_JUNCTION_PATH)"
echo "Via            : $VIA${PORTAL_FN:+ ($PORTAL_FN)}"
impact_begin
impact "creates" "a NEW volume $LAB_RESTORE_VOLUME_NAME in SVM $SVM_ID (${SIZE_MB:-unknown size} MB as recorded in the recovery point); nothing existing is overwritten"
impact "uses" "the existing restore SVM (SVM slots used on $FS_ID: $SLOTS; a restore adds a volume, not an SVM) and the storage of $FS_ID"
impact "cost" "the volume uses storage on $FS_ID until 10_teardown.sh deletes it; the price is not confirmed here (see the cost section of docs/procedure.md)"
impact "remains after revoke" "the restored volume stays after 09_revoke_share.sh: it is a copy owned by the recipient"
plan_gate "./scripts/08_restore.sh${REGION_ARG:+ --region $REGION_ARG} --via $VIA --apply"

# --------------------------------------------------------------------------
# Start
# --------------------------------------------------------------------------
# portal_invoke PAYLOAD: call the portal function; sets PORTAL_BODY (the response
# document). Returns 1 when the call fails or the function reports an error.
PORTAL_BODY=""
portal_invoke() {
  local payload=$1 out_file inv
  out_file=$(mktemp)
  if ! inv=$(aws_recipient lambda invoke --function-name "$PORTAL_FN" --cli-binary-format raw-in-base64-out --payload "$payload" "$out_file"); then
    rm -f "$out_file"
    return 1
  fi
  PORTAL_BODY=$(cat "$out_file")
  rm -f "$out_file"
  if [ "$(printf '%s' "$inv" | jq -r '.FunctionError // empty' 2>/dev/null)" != "" ]; then
    return 1
  fi
  printf '%s' "$PORTAL_BODY" | jq -e 'type == "object"' >/dev/null 2>&1
}

JOB_ID=""
started=$SECONDS
if [ "$VIA" = cli ]; then
  if ! START_OUT=$(aws_recipient backup start-restore-job \
    --recovery-point-arn "$RP_ARN" \
    --iam-role-arn "$ROLE_ARN" \
    --resource-type FSx \
    --idempotency-token "$TOKEN" \
    --metadata "$METADATA"); then
    die "backup start-restore-job failed"
  fi
  if ! JOB_ID=$(require_one "restore job id" "$(printf '%s' "$START_OUT" | jq -c '.RestoreJobId')"); then exit 1; fi
else
  START_PAYLOAD=$(json_build action startRestore recoveryPointArn "$RP_ARN" name "$LAB_RESTORE_VOLUME_NAME" \
    storageVirtualMachineId "$SVM_ID" fileSystemId "$FS_ID" junctionPath "$LAB_RESTORE_JUNCTION_PATH" \
    sizeInMegabytes "${SIZE_MB:-}" acknowledgeIrreversible:json true idempotencyToken "$TOKEN")
  if ! portal_invoke "$START_PAYLOAD"; then
    die "the portal restore function failed: $(printf '%s' "$PORTAL_BODY" | head -c 300)"
  fi
  PORTAL_ERROR=$(printf '%s' "$PORTAL_BODY" | jq -r '.error // empty')
  if [ -n "$PORTAL_ERROR" ]; then
    die "the portal restore function refused: $PORTAL_ERROR"
  fi
  if ! JOB_ID=$(require_one "restore job id" "$(printf '%s' "$PORTAL_BODY" | jq -c '.restoreJobId')"); then exit 1; fi
fi
record_event restore_started V7 "$JOB_ID via=$VIA"

# --------------------------------------------------------------------------
# Wait: the job status AND the volume lifecycle. Progress is not a readiness signal.
# --------------------------------------------------------------------------
JOB_STATUS=""
JOB_MESSAGE=""
VOL_STATE="none"
VOL_ARN=""
# shellcheck disable=SC2329,SC2317  # invoked through wait_until
poll_restore() {
  local job vols payload
  if [ "$VIA" = cli ]; then
    job=$(aws_recipient backup describe-restore-job --restore-job-id "$JOB_ID") || return 2
    JOB_STATUS=$(printf '%s' "$job" | jq -r '.Status // "UNKNOWN"')
    JOB_MESSAGE=$(printf '%s' "$job" | jq -r '.StatusMessage // empty')
  else
    payload=$(json_build action describeRestore restoreJobId "$JOB_ID")
    portal_invoke "$payload" || return 2
    JOB_STATUS=$(printf '%s' "$PORTAL_BODY" | jq -r '.restoreJob.status // "UNKNOWN"')
    JOB_MESSAGE=$(printf '%s' "$PORTAL_BODY" | jq -r '.restoreJob.statusMessage // empty')
  fi
  vols=$(aws_recipient fsx describe-volumes --filters "Name=storage-virtual-machine-id,Values=$SVM_ID") || return 2
  VOL_STATE=$(printf '%s' "$vols" | jq -r --arg n "$LAB_RESTORE_VOLUME_NAME" \
    '[.Volumes[]? | select(.Name == $n)][0].Lifecycle // "none"')
  VOL_ARN=$(printf '%s' "$vols" | jq -r --arg n "$LAB_RESTORE_VOLUME_NAME" \
    '[.Volumes[]? | select(.Name == $n)][0].ResourceARN // empty')
  case $JOB_STATUS in
    FAILED | ABORTED) return 0 ;;
  esac
  case $VOL_STATE in
    FAILED | MISCONFIGURED) return 0 ;;
  esac
  if [ "$JOB_STATUS" = COMPLETED ] && [ "$VOL_STATE" = CREATED ]; then
    return 0
  fi
  return 1
}

WAITED=0
if wait_until "restore job $JOB_ID" 5400 90 poll_restore; then
  WAITED=1
fi
elapsed=$((SECONDS - started))

if [ "$JOB_STATUS" = FAILED ] || [ "$JOB_STATUS" = ABORTED ]; then
  check_fail V7 "restore job $JOB_ID ended $JOB_STATUS after $elapsed seconds: ${JOB_MESSAGE:-no message}"
elif [ "$VOL_STATE" = FAILED ] || [ "$VOL_STATE" = MISCONFIGURED ]; then
  check_fail V7 "the restored volume is $VOL_STATE (job status $JOB_STATUS): ${JOB_MESSAGE:-no message}"
elif [ "$WAITED" = 1 ]; then
  record_event restore_seconds V7 "job=$JOB_ID seconds=$elapsed"
  check_pass V7 "restore job $JOB_ID COMPLETED and the volume is CREATED after $elapsed seconds (via $VIA)"
  check_pass E8 "the restore role of the recipient stack was accepted by the restore job"
  check_pass E9 "the restore metadata built by lab_helpers.py was accepted (via $VIA)"
  if [ "$REGION" != "$LAB_PRIMARY_REGION" ]; then
    check_pass E6 "a recovery point in $REGION was restored into a recipient file system in $REGION"
  fi
elif [ "$VOL_STATE" = CREATED ]; then
  check_warn V7 "the volume is CREATED but restore job $JOB_ID did not report COMPLETED within the wait (job status $JOB_STATUS): not treated as done"
else
  check_fail V7 "restore job $JOB_ID did not finish within the wait (job status $JOB_STATUS, volume $VOL_STATE)"
fi

# Tag the restored volume: a restored volume carries no tags, and 10_teardown.sh
# identifies it by its SVM. A failed tag call fails the run.
if [ "$VOL_STATE" = CREATED ] && [ -n "$VOL_ARN" ]; then
  if aws_recipient fsx tag-resource --resource-arn "$VOL_ARN" --tags "Key=Project,Value=$LAB_TAG" >/dev/null; then
    check_pass - "the restored volume carries Project=$LAB_TAG"
  else
    check_fail - "tagging the restored volume $VOL_ARN failed; 10_teardown.sh still finds it by its SVM, but the run is marked failed"
  fi
fi
lab_region_set ""
if summary; then
  exit 0
fi
exit 1
