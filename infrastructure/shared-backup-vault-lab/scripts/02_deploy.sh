#!/bin/bash
# Real-environment run: recorded [V1][V2][V3][V4][V5][V6][V7]; not recorded [E13] (status source: docs/verification-record.md)
#
# 02_deploy.sh - deploy the base resources through CloudFormation.
#
# Usage:
#   02_deploy.sh --side owner|recipient [--region REGION] [--apply]
#
#   --side owner       owner-base: customer managed key, FSx for ONTAP file system
#                      (one SVM, one volume), standard backup vault, backup role.
#                      Primary Region only.
#   --side recipient   recipient-restore: restore role and restore SVM (on an
#                      existing file system, or on a minimal new one).
#   --region           limit to one Region. Owner: the primary Region. Recipient:
#                      default is every configured Region; the second Region is
#                      skipped with a warning when LAB_SECOND_RECIPIENT_* is empty.
#   --apply            deploy. Without it the script prints the plan and exits 10.
#
# Billing starts when the file system is created. Nothing here is irreversible by
# itself, but the key is retained after teardown (see the IMPACT lines).
#
# Exit codes: 0 success, 1 failure or refusal (failed stack state, failed check,
# failed deploy), 2 usage error, 10 plan only, 75 tool missing.
#
# Not yet run on real environment: the stack outputs, the tag read-back and the
# lifecycle waits follow the documented API shapes only.

set -euo pipefail
# shellcheck source-path=SCRIPTDIR
# shellcheck source=lib/common.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

usage() {
  cat <<'EOF'
Usage: 02_deploy.sh --side owner|recipient [--region REGION] [--apply]
Deploys owner-base or recipient-restore. Without --apply only the plan is shown (exit 10).
EOF
}

SIDE=""
REGION_ARG=""
while [ "$#" -gt 0 ]; do
  case $1 in
    --side)
      if [ "$#" -lt 2 ]; then
        die_usage "--side needs owner or recipient"
      fi
      SIDE=$2
      shift 2
      ;;
    --region)
      if [ "$#" -lt 2 ]; then
        die_usage "--region needs a value"
      fi
      REGION_ARG=$2
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
case $SIDE in
  owner | recipient) ;;
  *) die_usage "--side owner or --side recipient is required" ;;
esac
if [ -n "$REGION_ARG" ]; then
  validate_region_arg "$REGION_ARG"
fi
if [ "$SIDE" = owner ] && [ -n "$REGION_ARG" ] && [ "$REGION_ARG" != "$LAB_PRIMARY_REGION" ]; then
  die_usage "owner-base exists in the primary Region only (LAB_PRIMARY_REGION)"
fi

# stack_guard KIND STACK REGION PROFILE: refuse to deploy over a stack that is in a
# failed or busy state. Prints the recovery commands; never deletes anything.
stack_guard() {
  local kind=$1 stack=$2 region=$3 profile=$4 json rc status class
  if json=$(describe_stack "$kind" "$stack"); then
    status=$(printf '%s' "$json" | jq -r '.Stacks[0].StackStatus // empty')
  else
    rc=$?
    if [ "$rc" = 4 ]; then
      status=""
    else
      die "the state of stack $stack could not be read in $region"
    fi
  fi
  class=$(stack_status_class "$status")
  case $class in
    failed)
      echo "error: stack $stack is in $status in $region and cannot be deployed over." >&2
      stack_recovery_hint "$status" "$stack" "$region" "$profile" >&2
      exit 1
      ;;
    busy) die "stack $stack is $status in $region; wait for the operation to finish" ;;
  esac
  STACK_STATE=$status
}

STACK_STATE=""
FS_ID=""
POLL_ARN=""

# poll_fs KIND / poll_svm KIND ID / poll_volume KIND ID: lifecycle polls for
# wait_until (0 done, 1 not yet, 2 the poll or the resource failed).
# shellcheck disable=SC2329,SC2317  # invoked through wait_until
poll_fs() {
  local kind=$1 out state
  case $kind in
    owner) out=$(aws_owner fsx describe-file-systems --file-system-ids "$FS_ID") || return 2 ;;
    recipient) out=$(aws_recipient fsx describe-file-systems --file-system-ids "$FS_ID") || return 2 ;;
  esac
  state=$(printf '%s' "$out" | jq -r '.FileSystems[0].Lifecycle // "UNKNOWN"')
  POLL_ARN=$(printf '%s' "$out" | jq -r '.FileSystems[0].ResourceARN // empty')
  case $state in
    AVAILABLE) return 0 ;;
    CREATING | UPDATING) return 1 ;;
    *) return 2 ;;
  esac
}

# shellcheck disable=SC2329,SC2317  # invoked through wait_until
poll_svm() {
  local kind=$1 id=$2 out state
  case $kind in
    owner) out=$(aws_owner fsx describe-storage-virtual-machines --storage-virtual-machine-ids "$id") || return 2 ;;
    recipient) out=$(aws_recipient fsx describe-storage-virtual-machines --storage-virtual-machine-ids "$id") || return 2 ;;
  esac
  state=$(printf '%s' "$out" | jq -r '.StorageVirtualMachines[0].Lifecycle // "UNKNOWN"')
  POLL_ARN=$(printf '%s' "$out" | jq -r '.StorageVirtualMachines[0].ResourceARN // empty')
  case $state in
    CREATED) return 0 ;;
    CREATING | PENDING) return 1 ;;
    *) return 2 ;;
  esac
}

# shellcheck disable=SC2329,SC2317  # invoked through wait_until
poll_volume() {
  local id=$1 out state
  out=$(aws_owner fsx describe-volumes --volume-ids "$id") || return 2
  state=$(printf '%s' "$out" | jq -r '.Volumes[0].Lifecycle // "UNKNOWN"')
  POLL_ARN=$(printf '%s' "$out" | jq -r '.Volumes[0].ResourceARN // empty')
  case $state in
    CREATED) return 0 ;;
    CREATING | PENDING) return 1 ;;
    *) return 2 ;;
  esac
}

# tag_check KIND LABEL ARN: item E3. FSx for ONTAP tags are not in the describe responses.
tag_check() {
  local kind=$1 label=$2 arn=$3 out
  case $kind in
    owner) out=$(aws_owner fsx list-tags-for-resource --resource-arn "$arn") || out="" ;;
    recipient) out=$(aws_recipient fsx list-tags-for-resource --resource-arn "$arn") || out="" ;;
  esac
  if [ -z "$out" ]; then
    check_fail E3 "tags of $label could not be read with fsx list-tags-for-resource"
  elif tags_have_lab_tag "$out"; then
    check_pass E3 "$label carries the Project=$LAB_TAG tag"
  else
    check_fail E3 "$label does not carry the Project=$LAB_TAG tag"
  fi
}

# show_outputs JSON: print the stack outputs.
show_outputs() {
  printf '%s' "$1" | jq -r '.Stacks[0].Outputs[]? | "  \(.OutputKey) = \(.OutputValue)"'
}

# --------------------------------------------------------------------------
# Owner
# --------------------------------------------------------------------------
deploy_owner() {
  local stack="${LAB_TAG}-owner-base" template="$LAB_ROOT/cloudformation/owner-base.yaml"
  local cmd="./scripts/02_deploy.sh --side owner --apply"
  local -a params
  params=(
    "LabTag=$LAB_TAG"
    "SubnetId=$LAB_OWNER_SUBNET_ID"
    "SecurityGroupId=${LAB_OWNER_SECURITY_GROUP_ID:-}"
    "StorageCapacityGiB=$LAB_OWNER_STORAGE_GIB"
    "ThroughputCapacity=$LAB_OWNER_THROUGHPUT_MBPS"
    "SvmName=$LAB_SVM_NAME"
    "VolumeName=$LAB_VOLUME_NAME"
    "VolumeSizeMB=$LAB_VOLUME_SIZE_MB"
    "StandardVaultName=$LAB_STANDARD_VAULT_NAME"
  )
  lab_region_set "$LAB_PRIMARY_REGION"
  assert_account owner
  require_sso_minutes "$LAB_OWNER_PROFILE" "$LAB_MIN_SSO_MINUTES"
  stack_guard owner "$stack" "$LAB_PRIMARY_REGION" "$LAB_OWNER_PROFILE"

  echo "Stack     : $stack ($LAB_PRIMARY_REGION, owner account)"
  echo "Template  : $template"
  echo "Parameters: ${params[*]}"
  impact_begin
  impact "creates" "customer managed KMS key and alias alias/${LAB_TAG}-fs, an FSx for ONTAP file system (${LAB_OWNER_STORAGE_GIB} GiB, ${LAB_OWNER_THROUGHPUT_MBPS} MBps, SINGLE_AZ_1), one SVM, one volume, standard backup vault ${LAB_STANDARD_VAULT_NAME}, a backup role"
  impact "cost" "billed per hour from the moment the file system exists until 10_teardown.sh deletes it; run 01_preflight.sh --estimate-cost for a dated price-list range (no figure is stated here)"
  impact "remains after teardown" "the KMS key and its alias (DeletionPolicy Retain) stay until 10_teardown.sh --delete-key; the key must stay usable until the last copy in an air-gapped vault expires"
  impact "time" "the file system takes about 15 minutes to become AVAILABLE (observed once; not yet run on real environment)"
  plan_gate "$cmd"

  if ! deploy_out=$(aws_owner cloudformation deploy \
    --template-file "$template" \
    --stack-name "$stack" \
    --capabilities CAPABILITY_IAM \
    --parameter-overrides "${params[@]}" \
    --tags "Project=$LAB_TAG" "Cleanup=delete-when-done" \
    --no-fail-on-empty-changeset 2>&1); then
    printf '%s\n' "$deploy_out" >&2
    echo "error: cloudformation deploy failed for $stack" >&2
    stack_failure_events owner "$stack"
    exit 1
  fi
  record_event deploy_done - "$stack"
  echo "Deployed $stack."
  postcheck_owner "$stack"
}

postcheck_owner() {
  local stack=$1 json key_out key_state vaults
  local svm_id vol_id
  if ! json=$(aws_owner cloudformation describe-stacks --stack-name "$stack"); then
    die "the outputs of $stack could not be read"
  fi
  echo "Outputs:"
  show_outputs "$json"
  if ! FS_ID=$(stack_value_one "owner-base FileSystemId" "$json" Outputs FileSystemId); then exit 1; fi
  if ! svm_id=$(stack_value_one "owner-base SvmId" "$json" Outputs SvmId); then exit 1; fi
  if ! vol_id=$(stack_value_one "owner-base VolumeId" "$json" Outputs VolumeId); then exit 1; fi

  if wait_until "file system $FS_ID" 3600 30 poll_fs owner; then
    check_pass - "file system $FS_ID is AVAILABLE"
    tag_check owner "file system $FS_ID" "$POLL_ARN"
  else
    check_fail - "file system $FS_ID did not reach AVAILABLE"
  fi
  if wait_until "SVM $svm_id" 900 15 poll_svm owner "$svm_id"; then
    check_pass - "SVM $svm_id is CREATED"
    tag_check owner "SVM $svm_id" "$POLL_ARN"
  else
    check_fail - "SVM $svm_id did not reach CREATED"
  fi
  if wait_until "volume $vol_id" 900 15 poll_volume "$vol_id"; then
    check_pass - "volume $vol_id is CREATED"
    tag_check owner "volume $vol_id" "$POLL_ARN"
  else
    check_fail - "volume $vol_id did not reach CREATED"
  fi

  if key_out=$(aws_owner kms describe-key --key-id "alias/${LAB_TAG}-fs"); then
    key_state=$(printf '%s' "$key_out" | jq -r '.KeyMetadata.KeyState // "unknown"')
    if [ "$key_state" = Enabled ]; then
      check_pass - "key alias/${LAB_TAG}-fs is Enabled"
    else
      check_fail - "key alias/${LAB_TAG}-fs is $key_state"
    fi
  else
    check_fail - "key alias/${LAB_TAG}-fs could not be read"
  fi
  if vaults=$(aws_owner backup list-backup-vaults); then
    if printf '%s' "$vaults" | jq -e --arg n "$LAB_STANDARD_VAULT_NAME" \
      '[.BackupVaultList[]? | select(.BackupVaultName == $n)] | length == 1' >/dev/null; then
      check_pass - "standard vault $LAB_STANDARD_VAULT_NAME exists"
    else
      check_fail - "standard vault $LAB_STANDARD_VAULT_NAME is not in the vault list"
    fi
  else
    check_fail - "backup list-backup-vaults failed"
  fi
}

# --------------------------------------------------------------------------
# Recipient
# --------------------------------------------------------------------------

# recipient_config REGION: sets R_FS R_SUBNET R_SG; returns 1 when the Region has no
# recipient configuration.
recipient_config() {
  local region=$1
  if [ "$region" = "$LAB_PRIMARY_REGION" ]; then
    R_FS=${LAB_RECIPIENT_EXISTING_FS_ID:-}
    R_SUBNET=${LAB_RECIPIENT_SUBNET_ID:-}
    R_SG=${LAB_RECIPIENT_SECURITY_GROUP_ID:-}
  else
    R_FS=${LAB_SECOND_RECIPIENT_EXISTING_FS_ID:-}
    R_SUBNET=${LAB_SECOND_RECIPIENT_SUBNET_ID:-}
    R_SG=${LAB_SECOND_RECIPIENT_SECURITY_GROUP_ID:-}
    if [ -z "$R_FS" ] && [ -z "$R_SUBNET" ]; then
      return 1
    fi
  fi
  return 0
}

# recipient_svm_budget REGION: refuse when the existing file system has no free SVM slot.
recipient_svm_budget() {
  local fs svms budget count limit rc
  if [ -z "$R_FS" ]; then
    return 0
  fi
  if ! fs=$(aws_recipient fsx describe-file-systems --file-system-ids "$R_FS"); then
    die "file system $R_FS could not be read"
  fi
  if ! svms=$(aws_recipient fsx describe-storage-virtual-machines --filters "Name=file-system-id,Values=$R_FS"); then
    die "the SVMs of $R_FS could not be listed"
  fi
  if budget=$(svm_budget "$fs" "$svms"); then
    count=${budget% *}
    limit=${budget#* }
    if [ "$STACK_STATE" = "" ] && [ "$count" -ge "$limit" ]; then
      die "file system $R_FS already holds $count of $limit SVMs: no free slot for the restore SVM"
    fi
    echo "SVM slots on $R_FS: $count of $limit used"
  else
    rc=$?
    if [ "$rc" = 3 ]; then
      die "this file system configuration is not in the documented SVM limit table; set LAB_RECIPIENT_SVM_LIMIT"
    fi
    die "the SVM budget of $R_FS could not be computed"
  fi
}

deploy_recipient_region() {
  local region=$1 json svm_id fs_id stack template
  stack="${LAB_TAG}-recipient-${region}"
  template="$LAB_ROOT/cloudformation/recipient-restore.yaml"
  local -a params
  lab_region_set "$region"
  if ! recipient_config "$region"; then
    check_warn - "no recipient configuration for $region (LAB_SECOND_RECIPIENT_*): skipped"
    return 0
  fi
  params=(
    "LabTag=$LAB_TAG"
    "ExistingFileSystemId=$R_FS"
    "SubnetId=$R_SUBNET"
    "SecurityGroupId=$R_SG"
    "ThroughputCapacity=$LAB_RECIPIENT_THROUGHPUT_MBPS"
    "RestoreSvmName=$LAB_RESTORE_SVM_NAME"
  )
  stack_guard recipient "$stack" "$region" "$LAB_RECIPIENT_PROFILE"
  recipient_svm_budget "$region"

  echo "Stack     : $stack ($region, recipient account)"
  echo "Template  : $template"
  echo "Parameters: ${params[*]}"
  impact_begin
  if [ -n "$R_FS" ]; then
    impact "creates" "a restore role and the SVM ${LAB_RESTORE_SVM_NAME} on the existing file system ${R_FS}"
    impact "cost" "no new file system is created; the cost of one more SVM is not confirmed"
  else
    impact "creates" "a restore role, a new minimal file system (1024 GiB, ${LAB_RECIPIENT_THROUGHPUT_MBPS} MBps, SINGLE_AZ_1) and the SVM ${LAB_RESTORE_SVM_NAME}"
    impact "cost" "billed per hour from the moment the file system exists until 10_teardown.sh deletes it; run 01_preflight.sh --estimate-cost for a dated price-list range (no figure is stated here)"
  fi
  impact "remains after teardown" "nothing is retained by this stack; a restored volume stays until you delete it"
  impact "time" "a new file system takes about 15 minutes to become AVAILABLE (observed once; not yet run on real environment)"
  PENDING_RECIPIENT=1
  if [ "$_LAB_APPLY" != "1" ]; then
    return 0
  fi

  if ! deploy_out=$(aws_recipient cloudformation deploy \
    --template-file "$template" \
    --stack-name "$stack" \
    --capabilities CAPABILITY_IAM \
    --parameter-overrides "${params[@]}" \
    --tags "Project=$LAB_TAG" "Cleanup=delete-when-done" \
    --no-fail-on-empty-changeset 2>&1); then
    printf '%s\n' "$deploy_out" >&2
    echo "error: cloudformation deploy failed for $stack" >&2
    stack_failure_events recipient "$stack"
    exit 1
  fi
  record_event deploy_done - "$stack"
  echo "Deployed $stack."
  if ! json=$(aws_recipient cloudformation describe-stacks --stack-name "$stack"); then
    die "the outputs of $stack could not be read"
  fi
  echo "Outputs:"
  show_outputs "$json"
  if ! svm_id=$(stack_value_one "recipient-restore RestoreSvmId" "$json" Outputs RestoreSvmId); then exit 1; fi
  if ! fs_id=$(stack_value_one "recipient-restore FileSystemId" "$json" Outputs FileSystemId); then exit 1; fi
  FS_ID=$fs_id
  if wait_until "file system $FS_ID" 3600 30 poll_fs recipient; then
    check_pass - "file system $FS_ID is AVAILABLE in $region"
  else
    check_fail - "file system $FS_ID did not reach AVAILABLE in $region"
  fi
  if wait_until "SVM $svm_id" 900 15 poll_svm recipient "$svm_id"; then
    check_pass - "restore SVM $svm_id is CREATED in $region"
    tag_check recipient "restore SVM $svm_id" "$POLL_ARN"
  else
    check_fail - "restore SVM $svm_id did not reach CREATED in $region"
  fi
}

PENDING_RECIPIENT=0
if [ "$SIDE" = owner ]; then
  deploy_owner
else
  assert_account recipient
  require_sso_minutes "$LAB_RECIPIENT_PROFILE" "$LAB_MIN_SSO_MINUTES"
  if [ -n "$REGION_ARG" ]; then
    deploy_recipient_region "$REGION_ARG"
  else
    for region in $(lab_regions); do
      deploy_recipient_region "$region"
    done
  fi
  lab_region_set ""
  if [ "$PENDING_RECIPIENT" = 1 ] && [ "$_LAB_APPLY" != "1" ]; then
    plan_exit "./scripts/02_deploy.sh --side recipient${REGION_ARG:+ --region $REGION_ARG} --apply"
  fi
fi
lab_region_set ""
if summary; then
  exit 0
fi
exit 1
