#!/bin/bash
# Real-environment run: recorded [V1][V2][V3][V4][V5][V6][V7]; not recorded [E13] (status source: docs/verification-record.md)
#
# 10_teardown.sh - delete what the lab created, except what cannot or must not be
# deleted yet, and print what remains.
#
# Usage:
#   10_teardown.sh [--apply]
#   10_teardown.sh --apply --delete-key --confirm TOKEN
#
#   --apply        delete. Without it the script prints what it found and exits 10.
#   --delete-key   also schedule the customer managed key for deletion (7 days) and
#                  delete its alias, but only when every condition holds (see step
#                  5). Needs --confirm with the token printed in the plan:
#                  delete-key-alias/<LAB_TAG>-fs. IRREVERSIBLE after the pending
#                  window.
#   (no --region)  the script always handles every configured Region.
#
# Order (each Project tag is read with fsx list-tags-for-resource before a delete):
#   0  read running backup, copy and restore jobs in BOTH Regions. Any running job,
#      or a job list that cannot be read (UNKNOWN), stops the run with exit 1 before
#      any change. Copy jobs are matched by the destination vault NAME or by the
#      volume ARN, never by the destination ARN, because the Region in which a
#      cross-Region copy job is listed is not known.
#   1  revoke the RAM share(s)
#   2  recipient: delete every non-root volume of the restore SVM (counted by
#      membership in the SVM, which must carry Project=<LAB_TAG>), then the
#      recipient stack
#   3  owner: delete the recovery points of the lab volume in the standard vault,
#      the volume (SkipFinalBackup=true), then the owner-base stack. Recovery points
#      are deleted ONLY when the owner-base stack exists, its StandardVault physical
#      id equals LAB_STANDARD_VAULT_NAME and the recovery point ResourceArn equals
#      the stack's VolumeArn. If the stack is absent and a vault with that name
#      still exists, nothing is deleted there: the script prints the remaining
#      resources and exits 1.
#   4  air-gapped vaults, listed in every Region independently of the stacks: a
#      vault that holds recovery points is kept and listed with its delete date; an
#      empty one is deleted through its stack
#   5  with --delete-key only: schedule the key deletion when every air-gapped vault
#      is known to be empty, no file system uses the key and the token matches
#   6  warn about backups of the deleted file system
#
# The script never deletes the portal sandbox: it prints the command.
#
# Exit codes: 0 success, 1 failure or refusal (running or unknown jobs, foreign tag,
# unverifiable standard vault, a step that failed, key deletion refused), 2 usage
# error, 10 plan only.
#
# Every delete, the order that CloudFormation accepts, the final-backup behaviour
# of volume deletion, and whether a pending key deletion affects the expiry of a
# copy in an air-gapped vault are not yet run on real environment.

set -euo pipefail
# shellcheck source-path=SCRIPTDIR
# shellcheck source=lib/common.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

usage() {
  cat <<'EOF'
Usage: 10_teardown.sh [--apply] [--delete-key --confirm TOKEN]
Deletes the lab resources that may be deleted and prints what remains. Without --apply only the findings are shown (exit 10).
EOF
}

DELETE_KEY=0
CONFIRM_GIVEN=0
while [ "$#" -gt 0 ]; do
  case $1 in
    --apply)
      lab_apply_on
      shift
      ;;
    --delete-key)
      DELETE_KEY=1
      shift
      ;;
    --confirm)
      if [ "$#" -lt 2 ]; then
        die_usage "--confirm needs a value"
      fi
      lab_confirm_set "$2"
      CONFIRM_GIVEN=1
      shift 2
      ;;
    --region)
      die_usage "10_teardown.sh has no --region: it always handles every configured Region"
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *) die_usage "unknown argument: $1" ;;
  esac
done
if [ "$CONFIRM_GIVEN" = 1 ] && [ "$DELETE_KEY" != 1 ]; then
  die_usage "--confirm is only used with --delete-key"
fi

PRIMARY=$LAB_PRIMARY_REGION
REGION_LIST=$(lab_regions | tr '\n' ' ' | sed 's/ $//')
BASE_STACK="${LAB_TAG}-owner-base"
KEY_ALIAS="alias/${LAB_TAG}-fs"
TOKEN="delete-key-${KEY_ALIAS}"

# unknown_abort WHAT: a read that failed is never read as "nothing there".
unknown_abort() {
  echo "UNKNOWN: $1. Nothing was changed. Fix the cause (sign in again? permissions?) and run this script again." >&2
  exit 1
}

assert_account owner
assert_account recipient
require_sso_minutes "$LAB_OWNER_PROFILE" "$LAB_MIN_SSO_MINUTES"
require_sso_minutes "$LAB_RECIPIENT_PROFILE" "$LAB_MIN_SSO_MINUTES"

# --------------------------------------------------------------------------
# Reading (no change is made before the gate)
# --------------------------------------------------------------------------

# Stack of the owner base in the primary Region.
lab_region_set "$PRIMARY"
BASE_PRESENT=0
VOLUME_ARN=""
VOLUME_ID=""
FS_ID=""
if BASE_JSON=$(describe_stack owner "$BASE_STACK"); then
  BASE_PRESENT=1
  base_status=$(printf '%s' "$BASE_JSON" | jq -r '.Stacks[0].StackStatus // empty')
  if [ "$(stack_status_class "$base_status")" = busy ]; then
    unknown_abort "stack $BASE_STACK is $base_status (an operation is in progress)"
  fi
  if ! VOLUME_ARN=$(stack_value_one "owner-base VolumeArn" "$BASE_JSON" Outputs VolumeArn); then exit 1; fi
  if ! VOLUME_ID=$(stack_value_one "owner-base VolumeId" "$BASE_JSON" Outputs VolumeId); then exit 1; fi
  if ! FS_ID=$(stack_value_one "owner-base FileSystemId" "$BASE_JSON" Outputs FileSystemId); then exit 1; fi
else
  rc=$?
  if [ "$rc" != 4 ]; then
    unknown_abort "stack $BASE_STACK could not be read in $PRIMARY"
  fi
fi

# Step 0: running jobs.
JOBS_FOUND=""
note_jobs() {
  if [ -n "$3" ]; then
    JOBS_FOUND="$JOBS_FOUND  $1 job(s) in $2: $3"$'\n'
  fi
}
for region in $REGION_LIST; do
  lab_region_set "$region"
  for state in CREATED PENDING RUNNING ABORTING; do
    if ! out=$(aws_owner backup list-backup-jobs --by-backup-vault-name "$LAB_STANDARD_VAULT_NAME" --by-state "$state"); then
      unknown_abort "the $state backup jobs in $region could not be listed"
    fi
    note_jobs backup "$region, $state" "$(printf '%s' "$out" | jq -r '[.BackupJobs[]?.BackupJobId] | join(" ")')"
  done
  # Copy jobs: matched by the destination vault NAME or the volume ARN. The
  # destination ARN is not used as a filter (E24: the Region that lists a
  # cross-Region copy job is not known), so both Regions are read.
  for state in CREATED RUNNING; do
    if ! out=$(aws_owner backup list-copy-jobs --by-state "$state"); then
      unknown_abort "the $state copy jobs in $region could not be listed"
    fi
    note_jobs copy "$region, $state" "$(printf '%s' "$out" | jq -r --arg lag "$LAB_LAG_VAULT_NAME" --arg vol "$VOLUME_ARN" '
      [.CopyJobs[]?
       | select((((.DestinationBackupVaultArn // "") | split(":backup-vault:")[1] // "") == $lag)
                or ($vol != "" and (.ResourceArn // "") == $vol))
       | .CopyJobId] | join(" ")')"
  done
  for status in PENDING RUNNING; do
    if ! out=$(aws_recipient backup list-restore-jobs --by-status "$status"); then
      unknown_abort "the $status restore jobs in $region could not be listed"
    fi
    note_jobs restore "$region, $status" "$(printf '%s' "$out" | jq -r --arg o "$LAB_OWNER_ACCOUNT_ID" '
      [.RestoreJobs[]? | select((.RecoveryPointArn // "") | contains(":" + $o + ":recovery-point:")) | .RestoreJobId]
      | join(" ")')"
  done
done
if [ -n "$JOBS_FOUND" ]; then
  echo "refused: jobs are running; nothing was changed. Wait for them to finish (or stop them yourself), then run this script again:" >&2
  printf '%s' "$JOBS_FOUND" >&2
  exit 1
fi

# Shares of the owner (step 1).
SHARES=""
for region in $REGION_LIST; do
  lab_region_set "$region"
  if ! out=$(aws_owner ram get-resource-shares --resource-owner SELF --name "$LAB_SHARE_NAME" --resource-share-status ACTIVE); then
    unknown_abort "the resource shares in $region could not be listed"
  fi
  for share_arn in $(printf '%s' "$out" | jq -r '.resourceShares[]?.resourceShareArn'); do
    SHARES="$SHARES $region=$share_arn"
  done
done

# tags_state KIND ARN: ok | foreign | notfound | unreadable for the Project tag of an FSx resource.
tags_state() {
  local kind=$1 arn=$2 out
  case $kind in
    owner) out=$(aws_owner fsx list-tags-for-resource --resource-arn "$arn" 2>&1) || out="FAILED:$out" ;;
    recipient) out=$(aws_recipient fsx list-tags-for-resource --resource-arn "$arn" 2>&1) || out="FAILED:$out" ;;
  esac
  case $out in
    FAILED:*NotFound*) echo notfound ;;
    FAILED:*) echo unreadable ;;
    *)
      if tags_have_lab_tag "$out"; then
        echo ok
      else
        echo foreign
      fi
      ;;
  esac
}

# Recipient (step 2): the restore SVM of each Region, its tag, and its non-root volumes.
REC_STACKS=""
REC_VOLUMES=""
for region in $REGION_LIST; do
  lab_region_set "$region"
  stack="${LAB_TAG}-recipient-${region}"
  if rjson=$(describe_stack recipient "$stack"); then
    REC_STACKS="$REC_STACKS $region"
  else
    rc=$?
    if [ "$rc" = 4 ]; then
      continue
    fi
    unknown_abort "stack $stack could not be read in $region"
  fi
  svm_id=$(stack_value "$rjson" Outputs RestoreSvmId)
  if [ -z "$svm_id" ]; then
    echo "  note: stack $stack has no RestoreSvmId output; its volumes cannot be located" >&2
    continue
  fi
  if ! sout=$(aws_recipient fsx describe-storage-virtual-machines --storage-virtual-machine-ids "$svm_id" 2>&1); then
    case $sout in
      *NotFound*) continue ;;
    esac
    unknown_abort "SVM $svm_id could not be read in $region"
  fi
  svm_arn=$(printf '%s' "$sout" | jq -r '.StorageVirtualMachines[0].ResourceARN // empty')
  case $(tags_state recipient "$svm_arn") in
    ok) ;;
    foreign)
      echo "refused: SVM $svm_id in $region does not carry Project=$LAB_TAG, so its volumes are not counted as lab volumes. Nothing was deleted." >&2
      exit 1
      ;;
    *) unknown_abort "the tags of SVM $svm_id in $region could not be read" ;;
  esac
  if ! vout=$(aws_recipient fsx describe-volumes --filters "Name=storage-virtual-machine-id,Values=$svm_id"); then
    unknown_abort "the volumes of SVM $svm_id in $region could not be listed"
  fi
  # The root volume belongs to the SVM and goes with it; every other volume is deleted.
  for vol in $(printf '%s' "$vout" | jq -r '.Volumes[]? | select((.OntapConfiguration.StorageVirtualMachineRoot // false) | not) | .VolumeId'); do
    REC_VOLUMES="$REC_VOLUMES $region=$vol"
  done
done

# Owner (step 3): the volume tag, and the standard vault scope.
VOLUME_PRESENT=0
if [ "$BASE_PRESENT" = 1 ]; then
  lab_region_set "$PRIMARY"
  case $(tags_state owner "$VOLUME_ARN") in
    ok) VOLUME_PRESENT=1 ;;
    notfound) VOLUME_PRESENT=0 ;;
    foreign)
      echo "refused: volume $VOLUME_ID does not carry Project=$LAB_TAG. Nothing was deleted." >&2
      exit 1
      ;;
    *) unknown_abort "the tags of volume $VOLUME_ID could not be read" ;;
  esac
fi

# STD_SCOPE: ok (the stack's StandardVault is LAB_STANDARD_VAULT_NAME), mismatch,
# foreign (no stack, but a vault of that name exists or cannot be ruled out) or none.
STD_SCOPE=none
OWN_RPS=""
if [ "$BASE_PRESENT" = 1 ]; then
  lab_region_set "$PRIMARY"
  if ! res=$(aws_owner cloudformation describe-stack-resource --stack-name "$BASE_STACK" --logical-resource-id StandardVault); then
    unknown_abort "the StandardVault resource of $BASE_STACK could not be read"
  fi
  physical=$(printf '%s' "$res" | jq -r '.StackResourceDetail.PhysicalResourceId // empty')
  if [ "$physical" = "$LAB_STANDARD_VAULT_NAME" ]; then
    STD_SCOPE=ok
    if ! rps=$(aws_owner backup list-recovery-points-by-backup-vault --backup-vault-name "$LAB_STANDARD_VAULT_NAME" --by-resource-arn "$VOLUME_ARN"); then
      unknown_abort "the recovery points of $LAB_STANDARD_VAULT_NAME could not be listed"
    fi
    # The listing is filtered by resource, and every row is checked again here: only
    # a recovery point of THIS volume is ever deleted.
    OWN_RPS=$(printf '%s' "$rps" | jq -r --arg v "$VOLUME_ARN" '[.RecoveryPoints[]? | select(.ResourceArn == $v) | .RecoveryPointArn] | join(" ")')
  else
    STD_SCOPE=mismatch
  fi
else
  lab_region_set "$PRIMARY"
  if vlist=$(aws_owner backup list-backup-vaults); then
    if printf '%s' "$vlist" | jq -e --arg n "$LAB_STANDARD_VAULT_NAME" '[.BackupVaultList[]? | select(.BackupVaultName == $n)] | length > 0' >/dev/null; then
      STD_SCOPE=foreign
    fi
  else
    STD_SCOPE=foreign
  fi
fi

# The standard vault cannot be tied to the lab: no recovery point is deleted from it.
STD_NOTE=""
if [ "$BASE_PRESENT" != 1 ] && [ "$STD_SCOPE" = foreign ]; then
  STD_NOTE="a vault with this name exists but there is no $BASE_STACK stack to prove it is the lab's; its recovery points were not touched. If it is the lab vault, delete its recovery points yourself, then run this script again"
elif [ "$BASE_PRESENT" = 1 ] && [ "$STD_SCOPE" != ok ]; then
  STD_NOTE="the StandardVault of $BASE_STACK is not named $LAB_STANDARD_VAULT_NAME (LAB_STANDARD_VAULT_NAME changed?); its recovery points were not touched"
fi

# Air-gapped vaults (step 4), every Region, independent of the stacks. A record is
# region|listed|recovery points|latest delete date|stack present. Unreadable = UNKNOWN.
LAG_RECORDS=""
LAG_UNKNOWN=0
LAG_RP_TOTAL=0
for region in $REGION_LIST; do
  lab_region_set "$region"
  listed=0
  rp_count=0
  latest="none"
  stack_present=0
  if vlist=$(aws_owner backup list-backup-vaults --by-vault-type LOGICALLY_AIR_GAPPED_BACKUP_VAULT); then
    if printf '%s' "$vlist" | jq -e --arg n "$LAB_LAG_VAULT_NAME" '[.BackupVaultList[]? | select(.BackupVaultName == $n)] | length > 0' >/dev/null; then
      listed=1
      if lrps=$(aws_owner backup list-recovery-points-by-backup-vault --backup-vault-name "$LAB_LAG_VAULT_NAME"); then
        rp_count=$(printf '%s' "$lrps" | jq -r '[.RecoveryPoints[]?] | length')
        latest=$(printf '%s' "$lrps" | jq -r '[.RecoveryPoints[]?.CalculatedLifecycle.DeleteAt // empty] | sort | last // "unknown"')
      else
        LAG_UNKNOWN=1
        rp_count=unknown
        echo "  warning: the recovery points of $LAB_LAG_VAULT_NAME in $region could not be listed (UNKNOWN); the vault is kept and key deletion is refused" >&2
      fi
    fi
  else
    LAG_UNKNOWN=1
    listed=unknown
    echo "  warning: the air-gapped vaults in $region could not be listed (UNKNOWN); key deletion is refused" >&2
  fi
  if describe_stack owner "${LAB_TAG}-lag-${region}" >/dev/null; then
    stack_present=1
  else
    rc=$?
    if [ "$rc" != 4 ]; then
      LAG_UNKNOWN=1
      stack_present=unknown
      echo "  warning: stack ${LAB_TAG}-lag-${region} could not be read (UNKNOWN); it is not deleted and key deletion is refused" >&2
    fi
  fi
  if [ "$rp_count" != unknown ] && [ "$rp_count" -gt 0 ]; then
    LAG_RP_TOTAL=$((LAG_RP_TOTAL + rp_count))
  fi
  LAG_RECORDS="$LAG_RECORDS $region|$listed|$rp_count|$latest|$stack_present"
done

# The key.
lab_region_set "$PRIMARY"
KEY_STATE=unknown
KEY_ARN=""
if kout=$(aws_owner kms describe-key --key-id "$KEY_ALIAS" 2>&1); then
  KEY_ARN=$(printf '%s' "$kout" | jq -r '.KeyMetadata.Arn // empty')
  KEY_STATE=$(printf '%s' "$kout" | jq -r '.KeyMetadata.KeyState // "unknown"')
else
  case $kout in
    *NotFound*) KEY_STATE=absent ;;
  esac
fi
lab_region_set ""

# --------------------------------------------------------------------------
# What was found, the remaining list, and the plan
# --------------------------------------------------------------------------

# lag_field RECORD N: field N (1-based) of a LAG record.
lag_field() {
  printf '%s' "$1" | cut -d'|' -f"$2"
}

LAG_DELETED=" "
KEY_SCHEDULED=0

# print_remaining: what is left after this run (or at the point it stopped).
print_remaining() {
  local rec region listed count latest stack files f
  echo "=== REMAINING (not deleted by this run) ==="
  for rec in $LAG_RECORDS; do
    region=$(lag_field "$rec" 1)
    listed=$(lag_field "$rec" 2)
    count=$(lag_field "$rec" 3)
    latest=$(lag_field "$rec" 4)
    stack=$(lag_field "$rec" 5)
    case $LAG_DELETED in
      *" $region "*) continue ;;
    esac
    if [ "$listed" = 1 ] || [ "$listed" = unknown ]; then
      if [ "$count" = 0 ]; then
        echo "  - air-gapped vault $LAB_LAG_VAULT_NAME in $region : empty but not deleted (see the messages above)"
      else
        echo "  - air-gapped vault $LAB_LAG_VAULT_NAME in $region : recovery points=$count, latest delete date=$latest; it cannot be deleted before they expire; storage cost continues (price not confirmed)"
      fi
      if [ "$count" = 0 ] && [ "$stack" = 0 ]; then
        echo "      empty and not managed by a stack: delete it yourself with: aws backup delete-backup-vault --backup-vault-name $LAB_LAG_VAULT_NAME --region $region --profile $LAB_OWNER_PROFILE"
      fi
    fi
  done
  if [ "$KEY_SCHEDULED" = 1 ]; then
    echo "  - customer managed key : deletion is scheduled (7-day pending window); it cannot be used meanwhile"
  elif [ "$KEY_STATE" != absent ]; then
    echo "  - customer managed key $KEY_ALIAS (state $KEY_STATE) : kept so that copies in the air-gapped vault stay valid; key charges continue (price not confirmed); delete with --delete-key after the last copy has expired"
  fi
  if [ -n "${STD_NOTE:-}" ]; then
    echo "  - standard vault $LAB_STANDARD_VAULT_NAME : $STD_NOTE"
  fi
  files=""
  for f in lab.local.env lab-run.local.jsonl portal.local.env portal-user.local.env; do
    if [ -e "$LAB_ROOT/$f" ]; then
      files="$files $f"
    fi
  done
  if [ -n "$files" ]; then
    echo "  - local files in $LAB_ROOT :$files (portal-user.local.env holds a sign-in credential; delete the files you no longer need)"
  fi
  if [ -f "$LAB_PORTAL_DIR/amplify_outputs.json" ]; then
    echo "  - portal sandbox (Cognito, AppSync, Lambda, DynamoDB) : this script does not delete it because it removes the portal users and data; run: make -C $LAB_PORTAL_DIR sandbox-delete"
  fi
  echo "  cost lag : Cost Explorer lags, so check the cost from the next day with ./scripts/06_verify.sh --cost"
}

echo "Found:"
if [ "$BASE_PRESENT" = 1 ]; then
  echo "  owner-base stack        : present ($BASE_STACK)"
else
  echo "  owner-base stack        : absent"
fi
echo "  share(s) to revoke      : $(printf '%s' "$SHARES" | wc -w | tr -d ' ')"
echo "  recipient stack(s)      : $(printf '%s' "$REC_STACKS" | wc -w | tr -d ' ')"
echo "  recipient volume(s)     : $(printf '%s' "$REC_VOLUMES" | wc -w | tr -d ' ') (non-root, counted by membership in the lab SVM)"
echo "  standard-vault recovery points of the lab volume : $(printf '%s' "$OWN_RPS" | wc -w | tr -d ' ') (standard vault scope: $STD_SCOPE)"
echo "  air-gapped recovery points kept : $LAG_RP_TOTAL"

DELETES=$(printf '%s' "$SHARES $REC_VOLUMES $REC_STACKS $OWN_RPS" | wc -w | tr -d ' ')
if [ "$BASE_PRESENT" = 1 ]; then
  DELETES=$((DELETES + 1))
fi
for rec in $LAG_RECORDS; do
  if [ "$(lag_field "$rec" 3)" = 0 ] && [ "$(lag_field "$rec" 5)" = 1 ]; then
    DELETES=$((DELETES + 1))
  fi
done

# refuse_standard_vault: print the remaining resources and stop with exit 1 (the
# air-gapped vaults and the key are not processed after this).
refuse_standard_vault() {
  echo "refused: the standard vault cannot be tied to the lab, so no recovery point is deleted (steps 4 and 5 are not run)." >&2
  print_remaining
  check_fail - "owner side not deleted: $STD_NOTE"
  summary || true
  exit 1
}

if [ "$DELETES" = 0 ] && [ "$DELETE_KEY" != 1 ]; then
  if [ -n "$STD_NOTE" ]; then
    refuse_standard_vault
  fi
  echo "Nothing to delete."
  print_remaining
  exit 0
fi

impact_begin
impact "deletes" "the RAM share(s), $(printf '%s' "$REC_VOLUMES" | wc -w | tr -d ' ') restored volume(s) and the recipient stack(s), the lab volume of the owner and $(printf '%s' "$OWN_RPS" | wc -w | tr -d ' ') of its standard-vault recovery point(s), the owner-base stack (SVM, file system, standard vault, role), and the stack of every EMPTY air-gapped vault"
impact "irreversible" "volumes are deleted with SkipFinalBackup=true: no final backup is taken, and deleted recovery points cannot be brought back"
impact "remains" "air-gapped vault(s) that hold recovery points (until their delete date), the key and alias (unless --delete-key), the local files, and the portal sandbox"
impact "cost continues" "air-gapped vault storage until the copy expires, and the key; neither price is confirmed here"
if [ "$DELETE_KEY" = 1 ]; then
  impact "schedules" "deletion of the key behind $KEY_ALIAS with a 7-day pending window, and removal of the alias (only when every condition of step 5 holds)"
  impact "while pending" "the key cannot be used for cryptographic operations"
  impact "unknown" "the effect of a pending key deletion on the expiry of copies in air-gapped vaults is not tested"
  irreversible_gate "$TOKEN" "./scripts/10_teardown.sh --apply --delete-key --confirm $TOKEN"
else
  plan_gate "./scripts/10_teardown.sh --apply"
fi

# --------------------------------------------------------------------------
# Waiting helpers
# --------------------------------------------------------------------------

# poll_share_gone: 0 when no ACTIVE share of the lab remains in the current Region.
# shellcheck disable=SC2329,SC2317  # invoked through wait_until
poll_share_gone() {
  local out
  out=$(aws_owner ram get-resource-shares --resource-owner SELF --name "$LAB_SHARE_NAME" --resource-share-status ACTIVE) || return 2
  [ "$(printf '%s' "$out" | jq -r '[.resourceShares[]?] | length')" = 0 ] || return 1
}

# poll_volume_gone KIND VOLUME_ID: 0 once describe-volumes answers VolumeNotFound.
# A volume that is still described is not gone; the describe is read directly
# (not a tag search, which can keep returning a deleted resource).
# shellcheck disable=SC2329,SC2317  # invoked through wait_until
poll_volume_gone() {
  local kind=$1 id=$2 out
  case $kind in
    owner) out=$(aws_owner fsx describe-volumes --volume-ids "$id" 2>&1) || out="FAILED:$out" ;;
    recipient) out=$(aws_recipient fsx describe-volumes --volume-ids "$id" 2>&1) || out="FAILED:$out" ;;
  esac
  case $out in
    FAILED:*VolumeNotFound*) return 0 ;;
    FAILED:*) return 2 ;;
  esac
  return 1
}

# poll_stack_gone KIND STACK: 0 when the stack no longer exists, 2 on DELETE_FAILED.
# shellcheck disable=SC2329,SC2317  # invoked through wait_until
poll_stack_gone() {
  local kind=$1 stack=$2 json rc status
  if json=$(describe_stack "$kind" "$stack"); then
    status=$(printf '%s' "$json" | jq -r '.Stacks[0].StackStatus // empty')
    if [ "$status" = DELETE_FAILED ]; then
      return 2
    fi
    return 1
  else
    rc=$?
  fi
  if [ "$rc" = 4 ]; then
    return 0
  fi
  return 2
}

# poll_rps_gone: 0 when no recovery point of the lab volume remains in the standard vault.
# shellcheck disable=SC2329,SC2317  # invoked through wait_until
poll_rps_gone() {
  local out
  out=$(aws_owner backup list-recovery-points-by-backup-vault --backup-vault-name "$LAB_STANDARD_VAULT_NAME" --by-resource-arn "$VOLUME_ARN") || return 2
  [ "$(printf '%s' "$out" | jq -r --arg v "$VOLUME_ARN" '[.RecoveryPoints[]? | select(.ResourceArn == $v)] | length')" = 0 ] || return 1
}

# delete_stack KIND STACK LABEL: delete a stack and wait for it to be gone. Returns 0
# when it is gone, 1 when the delete call failed, 2 when it was not gone after the
# wait. DS_MSG holds the sentence for the caller's check (a failed delete is
# reported, not hidden).
DS_MSG=""
delete_stack() {
  local kind=$1 stack=$2 label=$3
  case $kind in
    owner)
      if ! aws_owner cloudformation delete-stack --stack-name "$stack" >/dev/null; then
        DS_MSG="cloudformation delete-stack failed for $stack ($label)"
        return 1
      fi
      ;;
    recipient)
      if ! aws_recipient cloudformation delete-stack --stack-name "$stack" >/dev/null; then
        DS_MSG="cloudformation delete-stack failed for $stack ($label)"
        return 1
      fi
      ;;
  esac
  if wait_until "stack $stack" 2700 30 poll_stack_gone "$kind" "$stack"; then
    DS_MSG="stack $stack was deleted ($label)"
    return 0
  fi
  DS_MSG="stack $stack was not deleted ($label); its failed resources follow"
  stack_failure_events "$kind" "$stack"
  return 2
}

# --------------------------------------------------------------------------
# Step 1: revoke the shares
# --------------------------------------------------------------------------
for entry in $SHARES; do
  region=${entry%%=*}
  share_arn=${entry#*=}
  lab_region_set "$region"
  if ! aws_owner ram delete-resource-share --resource-share-arn "$share_arn" >/dev/null; then
    die "ram delete-resource-share failed in $region: stopping before any other change"
  fi
  record_event share_revoked - "$share_arn"
  if wait_until "share removal in $region" 300 5 poll_share_gone; then
    check_pass - "the resource share in $region is gone"
  else
    check_warn - "the resource share in $region is still listed as ACTIVE; continuing (the deletion is asynchronous)"
  fi
done

# --------------------------------------------------------------------------
# Step 2: the recipient
# --------------------------------------------------------------------------
for entry in $REC_VOLUMES; do
  region=${entry%%=*}
  vol=${entry#*=}
  lab_region_set "$region"
  if ! aws_recipient fsx delete-volume --volume-id "$vol" --ontap-configuration SkipFinalBackup=true >/dev/null; then
    check_fail - "deleting volume $vol in $region failed"
    continue
  fi
  if wait_until "volume $vol" 1800 30 poll_volume_gone recipient "$vol"; then
    check_pass - "restored volume $vol in $region was deleted"
  else
    check_fail - "restored volume $vol in $region is still there after the wait"
  fi
done
for region in $REC_STACKS; do
  lab_region_set "$region"
  if [ "$(lab_failed_count)" != 0 ]; then
    check_warn - "the recipient stack in $region is not deleted because an earlier step failed"
    continue
  fi
  if delete_stack recipient "${LAB_TAG}-recipient-${region}" "recipient restore SVM and role"; then
    check_pass - "$DS_MSG"
  else
    check_fail - "$DS_MSG"
  fi
done

# --------------------------------------------------------------------------
# Step 3: the owner
# --------------------------------------------------------------------------
lab_region_set "$PRIMARY"
if [ -n "$STD_NOTE" ]; then
  refuse_standard_vault
fi
if [ "$BASE_PRESENT" = 1 ]; then
  rp_failed=0
  for rp in $OWN_RPS; do
    if ! aws_owner backup delete-recovery-point --backup-vault-name "$LAB_STANDARD_VAULT_NAME" --recovery-point-arn "$rp" >/dev/null; then
      check_fail - "deleting recovery point $rp failed"
      rp_failed=1
    fi
  done
  if [ -n "$OWN_RPS" ] && [ "$rp_failed" = 0 ]; then
    if wait_until "recovery points of the lab volume" 900 15 poll_rps_gone; then
      check_pass - "the recovery points of the lab volume were deleted from $LAB_STANDARD_VAULT_NAME"
    else
      check_fail - "recovery points of the lab volume are still in $LAB_STANDARD_VAULT_NAME after the wait"
    fi
  fi
  if [ "$VOLUME_PRESENT" = 1 ]; then
    if aws_owner fsx delete-volume --volume-id "$VOLUME_ID" --ontap-configuration SkipFinalBackup=true >/dev/null; then
      if wait_until "volume $VOLUME_ID" 1800 30 poll_volume_gone owner "$VOLUME_ID"; then
        check_pass - "volume $VOLUME_ID was deleted"
      else
        check_fail - "volume $VOLUME_ID is still there after the wait"
      fi
    else
      check_fail - "deleting volume $VOLUME_ID failed"
    fi
  fi
  if [ "$(lab_failed_count)" = 0 ]; then
    if delete_stack owner "$BASE_STACK" "file system, SVM, standard vault and role"; then
      check_pass E12 "$DS_MSG (the volume was deleted through the API first)"
    else
      check_fail E12 "$DS_MSG"
    fi
  else
    check_warn - "$BASE_STACK is not deleted because an earlier step failed"
  fi
fi

# --------------------------------------------------------------------------
# Step 4: air-gapped vaults
# --------------------------------------------------------------------------
for rec in $LAG_RECORDS; do
  region=$(lag_field "$rec" 1)
  listed=$(lag_field "$rec" 2)
  count=$(lag_field "$rec" 3)
  stack=$(lag_field "$rec" 5)
  lab_region_set "$region"
  if [ "$listed" = unknown ] || [ "$count" = unknown ] || [ "$stack" = unknown ]; then
    check_warn - "the air-gapped vault state in $region is UNKNOWN: nothing was deleted there"
    continue
  fi
  if [ "$listed" = 1 ] && [ "$count" -gt 0 ]; then
    check_pass - "air-gapped vault $LAB_LAG_VAULT_NAME in $region holds $count recovery point(s): kept (delete date $(lag_field "$rec" 4))"
    continue
  fi
  if [ "$stack" = 1 ]; then
    if delete_stack owner "${LAB_TAG}-lag-${region}" "empty air-gapped vault and its share"; then
      LAG_DELETED="$LAG_DELETED$region "
      check_pass E11 "$DS_MSG after the share was revoked"
    else
      check_fail E11 "$DS_MSG"
    fi
  elif [ "$listed" = 1 ]; then
    check_warn - "air-gapped vault $LAB_LAG_VAULT_NAME in $region is empty but has no stack: delete it yourself (the command is in the remaining list)"
  fi
done

# --------------------------------------------------------------------------
# Step 5: the key
# --------------------------------------------------------------------------
lab_region_set "$PRIMARY"
if [ "$DELETE_KEY" != 1 ]; then
  echo "The key $KEY_ALIAS is kept until the last copy in the air-gapped vault has expired; then run this script again with --delete-key."
else
  reasons=""
  if [ "$LAG_UNKNOWN" = 1 ]; then
    reasons="$reasons; the state of an air-gapped vault is UNKNOWN"
  fi
  if [ "$LAG_RP_TOTAL" -gt 0 ]; then
    reasons="$reasons; air-gapped vaults still hold $LAG_RP_TOTAL recovery point(s)"
  fi
  if describe_stack owner "$BASE_STACK" >/dev/null; then
    reasons="$reasons; stack $BASE_STACK still exists"
  else
    rc=$?
    if [ "$rc" != 4 ]; then
      reasons="$reasons; stack $BASE_STACK could not be read"
    fi
  fi
  case $KEY_STATE in
    absent) echo "The key $KEY_ALIAS does not exist: nothing to schedule." ;;
    Enabled | Disabled) ;;
    *) reasons="$reasons; the key state is $KEY_STATE" ;;
  esac
  if [ "$KEY_STATE" = Enabled ] || [ "$KEY_STATE" = Disabled ]; then
    if fs_out=$(aws_owner fsx describe-file-systems); then
      if printf '%s' "$fs_out" | jq -e --arg k "$KEY_ARN" \
        '[.FileSystems[]? | (.KmsKeyId // "") as $id | select($id != "" and ($id == $k or ($k | endswith("/" + $id))))] | length > 0' >/dev/null; then
        reasons="$reasons; a file system still uses the key"
      fi
    else
      reasons="$reasons; the file systems could not be listed"
    fi
    if [ -z "$reasons" ]; then
      if aws_owner kms schedule-key-deletion --key-id "$KEY_ARN" --pending-window-in-days 7 >/dev/null; then
        KEY_SCHEDULED=1
        check_pass - "deletion of the key behind $KEY_ALIAS is scheduled (7-day pending window)"
        if ! aws_owner kms delete-alias --alias-name "$KEY_ALIAS" >/dev/null; then
          check_warn - "the alias $KEY_ALIAS could not be deleted; delete it yourself"
        fi
      else
        check_fail - "kms schedule-key-deletion failed"
      fi
    else
      check_fail - "key deletion refused${reasons}"
    fi
  elif [ -n "$reasons" ]; then
    check_fail - "key deletion refused${reasons}"
  fi
fi

# --------------------------------------------------------------------------
# Step 6: leftover backups of the deleted file system
# --------------------------------------------------------------------------
if [ -n "$FS_ID" ]; then
  lab_region_set "$PRIMARY"
  if bk=$(aws_owner fsx describe-backups --filters "Name=file-system-id,Values=$FS_ID"); then
    n=$(printf '%s' "$bk" | jq -r '[.Backups[]?] | length')
    if [ "$n" -gt 0 ]; then
      check_warn E12 "$n backup(s) of the deleted file system $FS_ID remain (volume deletion may create a final backup; not confirmed): they are billed until you delete them"
    else
      check_pass E12 "no backup of the deleted file system $FS_ID remains"
    fi
  else
    check_warn E12 "the backups of file system $FS_ID could not be listed"
  fi
fi
lab_region_set ""

print_remaining
if summary; then
  exit 0
fi
exit 1
