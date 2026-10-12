#!/bin/bash
# Real-environment run: recorded [V1][V2][V3][V4][V5][V6][V7]; not recorded [E13] (status source: docs/verification-record.md)
#
# 01_preflight.sh - read-only checks before anything is created or billed.
#
# Usage:
#   01_preflight.sh [--side owner|recipient|both] [--estimate-cost]
#
#   --side            which account(s) to check (default: both)
#   --estimate-cost   also read price-list rows and the Project cost allocation
#                     tag state, and print a cost range. It only READS and PRINTS:
#                     the commands that enable organization sharing or the cost
#                     allocation tag are shown as text, never run (they are
#                     organization-wide settings that need other credentials).
#
# What is checked (item ids are the verification items the result belongs to):
#   tools and Python/Node versions; required variables; the account behind each
#   profile; SSO token time [E14]; subnets and security groups; the recipient SVM
#   budget; name collisions (including a retained air-gapped vault); that the CLI
#   knows --by-shared; Region availability and the Amazon FSx backup opt-in [E16][E17];
#   organization sharing state [E19]; permissions through a policy simulation
#   [E18]; with --estimate-cost the price rows [E15].
#
# Exit codes: 0 all checks passed (warnings allowed), 2 usage error, 75 a tool is
# missing, 78 the environment is not ready (a required variable is empty, or a
# check failed).
#
# Every AWS call below is a read. Whether each check behaves as described is not
# yet run on real environment.

set -euo pipefail
# shellcheck source-path=SCRIPTDIR
# shellcheck source=lib/common.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

# This script changes nothing, so its results are real observations, not a plan.
lab_apply_on

usage() {
  cat <<'EOF'
Usage: 01_preflight.sh [--side owner|recipient|both] [--estimate-cost]
Read-only checks of the environment. Exit 0 ready, 75 tool missing, 78 not ready.
EOF
}

SIDE=both
ESTIMATE=0
while [ "$#" -gt 0 ]; do
  case $1 in
    --side)
      if [ "$#" -lt 2 ]; then
        die_usage "--side needs owner, recipient or both"
      fi
      SIDE=$2
      shift 2
      ;;
    --estimate-cost)
      ESTIMATE=1
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
  owner | recipient | both) ;;
  *) die_usage "--side must be owner, recipient or both" ;;
esac
DO_OWNER=0
DO_RECIPIENT=0
if [ "$SIDE" != recipient ]; then DO_OWNER=1; fi
if [ "$SIDE" != owner ]; then DO_RECIPIENT=1; fi

section() {
  printf '\n== %s ==\n' "$1"
}

# --------------------------------------------------------------------------
# Small readers
# --------------------------------------------------------------------------

# stack_status_for KIND STACK: print the status ("" when absent); returns 1 when unreadable.
stack_status_for() {
  local kind=$1 stack=$2 json rc
  if json=$(describe_stack "$kind" "$stack"); then
    printf '%s\n' "$(printf '%s' "$json" | jq -r '.Stacks[0].StackStatus // empty')"
    return 0
  else
    rc=$?
  fi
  if [ "$rc" = 4 ]; then
    printf '\n'
    return 0
  fi
  return 1
}

# stack_name_check KIND STACK LABEL: ok when absent or healthy, fail when failed or busy.
# Leaves the status ("" when absent or unreadable) in STACK_STATUS.
STACK_STATUS=""
stack_name_check() {
  local kind=$1 stack=$2 label=$3 status class region=${_LAB_REGION:-$LAB_PRIMARY_REGION}
  STACK_STATUS=""
  if ! status=$(stack_status_for "$kind" "$stack"); then
    check_warn - "$label: the stack $stack could not be read in $region"
    return 0
  fi
  STACK_STATUS=$status
  class=$(stack_status_class "$status")
  case $class in
    absent) check_pass - "$label: no stack named $stack in $region (it will be created)" ;;
    ok) check_pass - "$label: $stack exists in $region ($status); deploying again updates it" ;;
    failed)
      check_fail - "$label: $stack is in $status in $region and cannot be updated"
      stack_recovery_hint "$status" "$stack" "$region" "$([ "$kind" = owner ] && echo "$LAB_OWNER_PROFILE" || echo "$LAB_RECIPIENT_PROFILE")"
      ;;
    *) check_warn - "$label: $stack is $status in $region; wait for it to finish" ;;
  esac
}

# --------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------
section "Tools"
need_cmd aws
if ! aws_version=$(aws --version 2>&1); then
  die "aws --version failed" 75
fi
case $aws_version in
  aws-cli/2.*) check_pass - "AWS CLI version 2 found" ;;
  *) die "AWS CLI version 2 is required (found: ${aws_version%% *})" 75 ;;
esac
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'; then
  die "Python 3.9 or later is required for scripts/lib/lab_helpers.py" 75
fi
check_pass - "jq and Python 3.9 or later found"
if [ "$DO_RECIPIENT" = 1 ]; then
  need_cmd node
  need_cmd npm
  node_min=$(lab_py node-min-major)
  if ! node_version=$(run_external node --version); then
    die "node --version failed" 75
  fi
  node_major=${node_version#v}
  node_major=${node_major%%.*}
  if ! [[ $node_major =~ ^[0-9]+$ ]] || [ "$node_major" -lt "$node_min" ]; then
    die "Node.js $node_min or later is required for the portal tooling (found: $node_version)" 75
  fi
  check_pass - "Node.js $node_version and npm found (portal tooling needs $node_min or later)"
fi

# --------------------------------------------------------------------------
# Variables and values the templates will accept
# --------------------------------------------------------------------------
section "Configuration"
check_pass - "required variables are set"
case $LAB_OWNER_THROUGHPUT_MBPS in
  128 | 256 | 512 | 1024 | 2048 | 4096) ;;
  *) check_fail - "LAB_OWNER_THROUGHPUT_MBPS=$LAB_OWNER_THROUGHPUT_MBPS is not one of 128 256 512 1024 2048 4096" ;;
esac
case $LAB_RECIPIENT_THROUGHPUT_MBPS in
  128 | 256 | 512 | 1024 | 2048 | 4096) ;;
  *) check_fail - "LAB_RECIPIENT_THROUGHPUT_MBPS=$LAB_RECIPIENT_THROUGHPUT_MBPS is not one of 128 256 512 1024 2048 4096" ;;
esac
if [ "$LAB_OWNER_STORAGE_GIB" -lt 1024 ]; then
  check_fail - "LAB_OWNER_STORAGE_GIB=$LAB_OWNER_STORAGE_GIB is below the 1024 GiB minimum"
fi
if [ "$LAB_STANDARD_VAULT_NAME" = "$LAB_LAG_VAULT_NAME" ]; then
  check_fail - "LAB_STANDARD_VAULT_NAME and LAB_LAG_VAULT_NAME must differ"
fi

# --------------------------------------------------------------------------
# Identity and SSO token time
# --------------------------------------------------------------------------
OWNER_OK=0
RECIPIENT_OK=0
OWNER_CALLER_ARN=""
RECIPIENT_CALLER_ARN=""

# sso_check PROFILE: item E14.
sso_check() {
  local profile=$1 left
  if ! left=$(lab_py sso-minutes --profile "$profile" --now "$(now)"); then
    left="unknown:the helper failed"
  fi
  case $left in
    n/a) echo "  SSO token check skipped: $profile is not an SSO profile" ;;
    unknown:*) check_warn E14 "SSO token time for $profile could not be checked (${left#unknown:})" ;;
    *)
      if [ "$left" -lt "$LAB_MIN_SSO_MINUTES" ]; then
        check_fail E14 "SSO token for $profile has $left minutes left (need $LAB_MIN_SSO_MINUTES); run aws sso login"
      else
        check_pass E14 "SSO token for $profile has $left minutes left"
      fi
      ;;
  esac
}

section "Accounts"
if [ "$DO_OWNER" = 1 ]; then
  if out=$(aws_owner sts get-caller-identity); then
    acct=$(printf '%s' "$out" | jq -r '.Account // empty')
    OWNER_CALLER_ARN=$(printf '%s' "$out" | jq -r '.Arn // empty')
    if [ "$acct" = "$LAB_OWNER_ACCOUNT_ID" ]; then
      check_pass - "owner profile resolves to the declared owner account"
      OWNER_OK=1
    else
      check_fail - "owner profile resolves to account ${acct:-unknown}, expected $LAB_OWNER_ACCOUNT_ID"
    fi
  else
    check_fail - "sts get-caller-identity failed for the owner profile (sign in again?)"
  fi
  sso_check "$LAB_OWNER_PROFILE"
fi
if [ "$DO_RECIPIENT" = 1 ]; then
  if out=$(aws_recipient sts get-caller-identity); then
    acct=$(printf '%s' "$out" | jq -r '.Account // empty')
    RECIPIENT_CALLER_ARN=$(printf '%s' "$out" | jq -r '.Arn // empty')
    if [ "$acct" = "$LAB_RECIPIENT_ACCOUNT_ID" ]; then
      check_pass - "recipient profile resolves to the declared recipient account"
      RECIPIENT_OK=1
    else
      check_fail - "recipient profile resolves to account ${acct:-unknown}, expected $LAB_RECIPIENT_ACCOUNT_ID"
    fi
  else
    check_fail - "sts get-caller-identity failed for the recipient profile (sign in again?)"
  fi
  sso_check "$LAB_RECIPIENT_PROFILE"
fi

# --------------------------------------------------------------------------
# Subnet and security group
# --------------------------------------------------------------------------

# owner_network: the owner subnet exists and the security group is in the same VPC.
owner_network() {
  local sub vpc sg_json sg_vpc
  if ! sub=$(aws_owner ec2 describe-subnets --subnet-ids "$LAB_OWNER_SUBNET_ID"); then
    check_fail - "owner subnet $LAB_OWNER_SUBNET_ID could not be read"
    return 0
  fi
  if ! vpc=$(printf '%s' "$sub" | jq -er '.Subnets[0].VpcId'); then
    check_fail - "owner subnet $LAB_OWNER_SUBNET_ID was not found"
    return 0
  fi
  check_pass - "owner subnet $LAB_OWNER_SUBNET_ID exists (VPC $vpc)"
  if [ -n "${LAB_OWNER_SECURITY_GROUP_ID:-}" ]; then
    if ! sg_json=$(aws_owner ec2 describe-security-groups --group-ids "$LAB_OWNER_SECURITY_GROUP_ID"); then
      check_fail - "owner security group $LAB_OWNER_SECURITY_GROUP_ID could not be read"
      return 0
    fi
    sg_vpc=$(printf '%s' "$sg_json" | jq -r '.SecurityGroups[0].VpcId // empty')
    if [ "$sg_vpc" = "$vpc" ]; then
      check_pass - "owner security group is in the same VPC as the subnet"
    else
      check_fail - "owner security group is in VPC ${sg_vpc:-unknown}, but the subnet is in $vpc"
    fi
  else
    check_pass - "no owner security group set: the VPC default group is used"
  fi
}

# --------------------------------------------------------------------------
# Owner checks
# --------------------------------------------------------------------------

# owner_primary: names and settings that exist once, in the primary Region.
owner_primary() {
  local vaults key_out state settings optin base_class
  stack_name_check owner "${LAB_TAG}-owner-base" "owner-base stack"
  base_class=$(stack_status_class "$STACK_STATUS")

  # Existence is read from the list; describe-backup-vault answers AccessDenied
  # for a name that does not exist (observed once), so it cannot tell.
  if vaults=$(aws_owner backup list-backup-vaults); then
    if printf '%s' "$vaults" | jq -e --arg n "$LAB_STANDARD_VAULT_NAME" \
      '[.BackupVaultList[]? | select(.BackupVaultName == $n)] | length > 0' >/dev/null; then
      if [ "$base_class" = ok ]; then
        check_pass - "standard vault $LAB_STANDARD_VAULT_NAME exists (created by the owner-base stack)"
      else
        check_fail - "a backup vault named $LAB_STANDARD_VAULT_NAME already exists and no owner-base stack owns it; set another LAB_STANDARD_VAULT_NAME or LAB_TAG"
      fi
    else
      check_pass - "no backup vault named $LAB_STANDARD_VAULT_NAME yet"
    fi
  else
    check_fail - "backup list-backup-vaults failed in $LAB_PRIMARY_REGION"
  fi

  if key_out=$(aws_owner kms describe-key --key-id "alias/${LAB_TAG}-fs" 2>&1); then
    state=$(printf '%s' "$key_out" | jq -r '.KeyMetadata.KeyState // "unknown"')
    if [ "$base_class" = ok ]; then
      check_pass - "key alias alias/${LAB_TAG}-fs exists (created by the owner-base stack, state $state)"
    else
      check_fail - "key alias alias/${LAB_TAG}-fs already exists (key state $state) and no owner-base stack owns it; the alias is retained after teardown, so use another LAB_TAG (10_teardown.sh --delete-key needs every air-gapped vault to be empty first)"
    fi
  else
    case $key_out in
      *NotFoundException*) check_pass - "no key alias alias/${LAB_TAG}-fs yet" ;;
      *) check_warn - "key alias alias/${LAB_TAG}-fs could not be checked" ;;
    esac
  fi

  if settings=$(aws_owner backup describe-region-settings); then
    optin=$(printf '%s' "$settings" | jq -r '.ResourceTypeOptInPreference | if has("FSx") then (.FSx | tostring) else "missing" end')
    case $optin in
      true) check_pass E17 "the Amazon FSx service opt-in is enabled in $LAB_PRIMARY_REGION" ;;
      false) check_warn E17 "the Amazon FSx service opt-in is disabled in $LAB_PRIMARY_REGION; the effect on an on-demand backup of an explicit ARN is not yet run on real environment" ;;
      *) check_warn E17 "no Amazon FSx entry in the service opt-in settings of $LAB_PRIMARY_REGION; the effect is not yet run on real environment" ;;
    esac
  else
    check_warn E17 "backup describe-region-settings failed in $LAB_PRIMARY_REGION"
  fi
}

# owner_region REGION: checks that repeat per Region.
owner_region() {
  local region=$1 type_out vaults shares class expiry count rp
  if type_out=$(aws_owner cloudformation describe-type --type RESOURCE --type-name AWS::Backup::LogicallyAirGappedBackupVault 2>&1); then
    check_pass E16 "the air-gapped vault resource type is available in $region"
  else
    case $type_out in
      *TypeNotFoundException*) check_fail E16 "the air-gapped vault resource type was not found in $region" ;;
      *) check_warn E16 "availability of the air-gapped vault type in $region could not be determined" ;;
    esac
  fi

  stack_name_check owner "${LAB_TAG}-lag-${region}" "air-gapped vault stack"
  class=$(stack_status_class "$STACK_STATUS")

  if vaults=$(aws_owner backup list-backup-vaults); then
    if printf '%s' "$vaults" | jq -e --arg n "$LAB_LAG_VAULT_NAME" \
      '[.BackupVaultList[]? | select(.BackupVaultName == $n)] | length > 0' >/dev/null; then
      if [ "$class" = ok ]; then
        check_pass - "air-gapped vault $LAB_LAG_VAULT_NAME exists in $region (created by the stack)"
      else
        count=$(printf '%s' "$vaults" | jq -r --arg n "$LAB_LAG_VAULT_NAME" '[.BackupVaultList[] | select(.BackupVaultName == $n)][0].NumberOfRecoveryPoints // "unknown"')
        expiry="not readable"
        if rp=$(aws_owner backup list-recovery-points-by-backup-vault --backup-vault-name "$LAB_LAG_VAULT_NAME" 2>/dev/null); then
          expiry=$(printf '%s' "$rp" | jq -r '[.RecoveryPoints[]?.CalculatedLifecycle.DeleteAt // empty] | max // "no recovery point"')
        fi
        check_fail - "a retained air-gapped vault named $LAB_LAG_VAULT_NAME exists in $region without a stack (recovery points: $count, latest expiry: $expiry). It cannot be deleted while it holds a recovery point. Set another LAB_TAG (for example ${LAB_TAG}-2): every default name changes"
      fi
    else
      check_pass - "no air-gapped vault named $LAB_LAG_VAULT_NAME in $region yet"
    fi
  else
    check_fail - "backup list-backup-vaults failed in $region"
  fi

  if shares=$(aws_owner ram get-resource-shares --resource-owner SELF --name "$LAB_SHARE_NAME" --resource-share-status ACTIVE); then
    count=$(printf '%s' "$shares" | jq -r --arg n "$LAB_SHARE_NAME" '[.resourceShares[]? | select(.name == $n and .status == "ACTIVE")] | length')
    if [ "$count" = 0 ]; then
      check_pass - "no active resource share named $LAB_SHARE_NAME in $region yet"
    elif [ "$class" = ok ]; then
      check_pass - "resource share $LAB_SHARE_NAME exists in $region (created by the stack)"
    else
      check_fail - "an active resource share named $LAB_SHARE_NAME already exists in $region and no stack owns it; set another LAB_SHARE_NAME or LAB_TAG"
    fi
  else
    check_warn - "ram get-resource-shares failed in $region"
  fi
}

# organization_state: item E19. Information only, except when external sharing is off.
organization_state() {
  local org mgmt services err
  if org=$(aws_owner organizations describe-organization 2>&1); then
    mgmt=$(printf '%s' "$org" | jq -r '.Organization.MasterAccountId // empty')
    if [ "$mgmt" = "$LAB_OWNER_ACCOUNT_ID" ]; then
      if services=$(aws_owner organizations list-aws-service-access-for-organization 2>&1); then
        if printf '%s' "$services" | jq -e '[.EnabledServicePrincipals[]? | select(.ServicePrincipal == "ram.amazonaws.com")] | length > 0' >/dev/null; then
          check_pass E19 "the owner account is the management account and sharing with the organization is enabled"
        else
          if [ "$LAB_ALLOW_EXTERNAL_PRINCIPALS" = false ]; then
            check_fail E19 "LAB_ALLOW_EXTERNAL_PRINCIPALS=false needs sharing with the organization, which is not enabled"
          else
            check_pass E19 "the owner account is the management account; sharing with the organization is not enabled (the share goes to the account directly)"
          fi
          echo "  To enable organization sharing, run this with the management account (this lab never runs it):"
          echo "    aws ram enable-sharing-with-aws-organization --profile <management-account-profile>"
        fi
      else
        check_warn E19 "the organization sharing state could not be read"
      fi
    else
      check_warn E19 "the owner account is a member of an organization; whether sharing with the organization is enabled cannot be read from here"
    fi
  else
    err=$org
    case $err in
      *AWSOrganizationsNotInUseException*)
        if [ "$LAB_ALLOW_EXTERNAL_PRINCIPALS" = false ]; then
          check_fail E19 "LAB_ALLOW_EXTERNAL_PRINCIPALS=false needs an organization, and the owner account is not in one"
        else
          check_pass E19 "the owner account is not in an organization: the share goes to the account directly and the recipient accepts an invitation"
        fi
        ;;
      *) check_warn E19 "the organization state could not be read" ;;
    esac
  fi
}

# --------------------------------------------------------------------------
# Recipient checks
# --------------------------------------------------------------------------

# recipient_region REGION: file system, SVM budget and name collisions for one Region.
recipient_region() {
  local region=$1 fs_id subnet sg tp fs svms sub_json vpc sg_json sg_vpc budget count limit rc names base_class
  if [ "$region" = "$LAB_PRIMARY_REGION" ]; then
    fs_id=${LAB_RECIPIENT_EXISTING_FS_ID:-}
    subnet=${LAB_RECIPIENT_SUBNET_ID:-}
    sg=${LAB_RECIPIENT_SECURITY_GROUP_ID:-}
  else
    fs_id=${LAB_SECOND_RECIPIENT_EXISTING_FS_ID:-}
    subnet=${LAB_SECOND_RECIPIENT_SUBNET_ID:-}
    sg=${LAB_SECOND_RECIPIENT_SECURITY_GROUP_ID:-}
    if [ -z "$fs_id" ] && [ -z "$subnet" ]; then
      check_warn - "no second-Region recipient configuration (LAB_SECOND_RECIPIENT_*): restoring a copy in $region is not prepared"
      return 0
    fi
  fi
  tp=$LAB_RECIPIENT_THROUGHPUT_MBPS

  stack_name_check recipient "${LAB_TAG}-recipient-${region}" "recipient stack"
  base_class=$(stack_status_class "$STACK_STATUS")

  if [ -n "$fs_id" ]; then
    if ! fs=$(aws_recipient fsx describe-file-systems --file-system-ids "$fs_id"); then
      check_fail - "recipient file system $fs_id could not be read in $region"
      return 0
    fi
    if [ "$(printf '%s' "$fs" | jq -r '.FileSystems[0].Lifecycle // "missing"')" = AVAILABLE ]; then
      check_pass - "recipient file system $fs_id is AVAILABLE in $region"
    else
      check_fail - "recipient file system $fs_id is not AVAILABLE in $region"
    fi
    if ! svms=$(aws_recipient fsx describe-storage-virtual-machines --filters "Name=file-system-id,Values=$fs_id"); then
      check_fail - "storage virtual machines of $fs_id could not be listed in $region"
      return 0
    fi
    names=$(printf '%s' "$svms" | jq -r '[.StorageVirtualMachines[]?.Name] | join(" ")')
    if budget=$(svm_budget "$fs" "$svms"); then
      count=${budget% *}
      limit=${budget#* }
      if [ "$base_class" = ok ]; then
        check_pass - "recipient file system $fs_id holds $count of $limit SVMs (the restore SVM is already deployed)"
      elif [ "$count" -ge "$limit" ]; then
        check_fail - "recipient file system $fs_id already holds $count of $limit SVMs: no free slot for the restore SVM"
      elif [ "$count" -ge $((limit - 1)) ]; then
        check_warn - "recipient file system $fs_id holds $count of $limit SVMs: the restore SVM of this lab fills the last slot"
      else
        check_pass - "recipient file system $fs_id holds $count of $limit SVMs: a slot is free"
      fi
    else
      rc=$?
      if [ "$rc" = 3 ]; then
        check_fail - "this file system configuration is not in the documented SVM limit table; set LAB_RECIPIENT_SVM_LIMIT"
      else
        check_fail - "the SVM budget of $fs_id could not be computed"
      fi
    fi
    case " $names " in
      *" $LAB_RESTORE_SVM_NAME "*)
        if [ "$base_class" != ok ]; then
          check_fail - "an SVM named $LAB_RESTORE_SVM_NAME already exists on $fs_id; set another LAB_RESTORE_SVM_NAME"
        fi
        ;;
    esac
  else
    if ! sub_json=$(aws_recipient ec2 describe-subnets --subnet-ids "$subnet"); then
      check_fail - "recipient subnet $subnet could not be read in $region"
      return 0
    fi
    if ! vpc=$(printf '%s' "$sub_json" | jq -er '.Subnets[0].VpcId'); then
      check_fail - "recipient subnet $subnet was not found in $region"
      return 0
    fi
    check_pass - "recipient subnet $subnet exists in $region (VPC $vpc)"
    if [ -n "$sg" ]; then
      if sg_json=$(aws_recipient ec2 describe-security-groups --group-ids "$sg"); then
        sg_vpc=$(printf '%s' "$sg_json" | jq -r '.SecurityGroups[0].VpcId // empty')
        if [ "$sg_vpc" = "$vpc" ]; then
          check_pass - "recipient security group is in the same VPC as the subnet"
        else
          check_fail - "recipient security group is in VPC ${sg_vpc:-unknown}, but the subnet is in $vpc"
        fi
      else
        check_fail - "recipient security group $sg could not be read in $region"
      fi
    fi
    if [ -n "${LAB_RECIPIENT_SVM_LIMIT:-}" ]; then
      limit=$LAB_RECIPIENT_SVM_LIMIT
    elif ! limit=$(lab_py svm-limit --throughput "$tp" 2>/dev/null); then
      check_fail - "throughput $tp MBps is not in the documented SVM limit table; set LAB_RECIPIENT_SVM_LIMIT"
      return 0
    fi
    check_pass - "a new minimal recipient file system ($tp MBps) allows $limit SVMs; the lab uses one"
  fi
}

# --------------------------------------------------------------------------
# Permissions (policy simulation) - item E18
# --------------------------------------------------------------------------

# iam_get_role KIND ROLE_NAME / iam_simulate KIND POLICY_SOURCE_ARN ACTIONS...
iam_get_role() {
  case $1 in
    owner) aws_owner iam get-role --role-name "$2" ;;
    recipient) aws_recipient iam get-role --role-name "$2" ;;
    *) die_usage "iam_get_role: expected owner or recipient" ;;
  esac
}

iam_simulate() {
  local kind=$1 source_arn=$2
  shift 2
  case $kind in
    owner) aws_owner iam simulate-principal-policy --policy-source-arn "$source_arn" --action-names "$@" ;;
    recipient) aws_recipient iam simulate-principal-policy --policy-source-arn "$source_arn" --action-names "$@" ;;
    *) die_usage "iam_simulate: expected owner or recipient" ;;
  esac
}

# permission_check KIND CALLER_ARN: simulate the actions of required-actions.json.
permission_check() {
  local kind=$1 caller=$2 principal role_name role_json group strict line out denied
  local actions_file="$LAB_ROOT/scripts/lib/required-actions.json"
  case $caller in
    arn:*:sts::*:assumed-role/*)
      role_name=${caller#*:assumed-role/}
      role_name=${role_name%%/*}
      if ! role_json=$(iam_get_role "$kind" "$role_name" 2>/dev/null); then
        check_warn E18 "the $kind permissions cannot be pre-checked: iam get-role was refused or failed"
        return 0
      fi
      principal=$(printf '%s' "$role_json" | jq -r '.Role.Arn // empty')
      ;;
    arn:*:iam::*:user/*) principal=$caller ;;
    *)
      check_warn E18 "the $kind permissions cannot be pre-checked for this kind of principal"
      return 0
      ;;
  esac
  if [ -z "$principal" ]; then
    check_warn E18 "the $kind permissions cannot be pre-checked: no role ARN was returned"
    return 0
  fi
  for group in "operator-$kind" "cloudformation-provisioning-$kind" operator-optional; do
    strict=1
    if [ "$group" = operator-optional ]; then
      strict=0
    fi
    denied=""
    # 40 actions per call; action names contain no glob characters.
    while IFS= read -r line; do
      [ -n "$line" ] || continue
      set -f
      # shellcheck disable=SC2086
      if ! out=$(iam_simulate "$kind" "$principal" $line 2>/dev/null); then
        set +f
        check_warn E18 "the $kind permissions of group $group cannot be pre-checked: simulate-principal-policy failed or was refused"
        denied=""
        break
      fi
      set +f
      # An action that is missing from the answer counts as not allowed.
      denied="$denied $(printf '%s' "$out" | jq -r --arg req "$line" '
        [.EvaluationResults[]? | select(.EvalDecision == "allowed") | .EvalActionName] as $ok
        | [($req | split(" "))[] | select(. as $a | $ok | index($a) | not)] | join(" ")')"
    done < <(jq -r --arg g "$group" '.[$g] as $a | [range(0; ($a | length); 40)] | map($a[.:.+40] | join(" ")) | .[]' "$actions_file")
    denied=$(printf '%s' "$denied" | tr -s ' ' | sed 's/^ //')
    # iam:PassRole is usually limited to the lab roles. The simulation is run without
    # a resource, so a correctly scoped policy shows up as not allowed: warn only.
    case " $denied " in
      *" iam:PassRole "*)
        check_warn E18 "iam:PassRole shows as not allowed for the $kind principal; it is simulated without a resource, so a policy limited to the lab role ARN looks denied. Check it by hand."
        denied=$(printf '%s' " $denied " | sed 's/ iam:PassRole / /' | tr -s ' ' | sed 's/^ //;s/ $//')
        ;;
    esac
    if [ -n "$denied" ]; then
      if [ "$strict" = 1 ]; then
        check_fail E18 "the $kind principal is not allowed to call (group $group): $denied"
      else
        check_warn E18 "optional actions the $kind principal is not allowed to call (group $group): $denied"
      fi
    else
      check_pass E18 "simulation: the $kind principal is allowed every action of group $group"
    fi
  done
  echo "  A simulation that passes does not guarantee the real call works (service control policies are not known to be included)."
}

# --------------------------------------------------------------------------
# Cost estimate (--estimate-cost) - item E15; reads and prints only
# --------------------------------------------------------------------------
estimate_cost() {
  local prices rows low high tags status
  section "Cost estimate (read only)"
  if prices=$(_LAB_REGION=us-east-1 aws_owner pricing get-products --service-code AmazonFSx \
    --filters "Type=TERM_MATCH,Field=regionCode,Value=$LAB_PRIMARY_REGION" --format-version aws_v1); then
    # The attribute names of Amazon FSx price rows are not confirmed, so rows are selected
    # by any attribute value that mentions ONTAP, and the range is shown as a range.
    rows=$(printf '%s' "$prices" | jq -r '
      [.PriceList[]? | fromjson
       | select([.product.attributes[]?] | map(tostring | ascii_downcase) | any(contains("ontap")))
       | [.terms.OnDemand[]?.priceDimensions[]? | .pricePerUnit.USD // empty | tonumber]
       | .[]] | length') || rows=0
    if [ "$rows" = 0 ]; then
      check_warn E15 "no price rows mention ONTAP for $LAB_PRIMARY_REGION: the attribute names used for the filter are not confirmed, so no estimate is shown"
    else
      low=$(printf '%s' "$prices" | jq -r '[.PriceList[]? | fromjson | select([.product.attributes[]?] | map(tostring | ascii_downcase) | any(contains("ontap"))) | .terms.OnDemand[]?.priceDimensions[]? | .pricePerUnit.USD // empty | tonumber | select(. > 0)] | min')
      high=$(printf '%s' "$prices" | jq -r '[.PriceList[]? | fromjson | select([.product.attributes[]?] | map(tostring | ascii_downcase) | any(contains("ontap"))) | .terms.OnDemand[]?.priceDimensions[]? | .pricePerUnit.USD // empty | tonumber | select(. > 0)] | max')
      check_pass E15 "price rows read on $(now): $rows USD values from $low to $high per unit (units differ per row; the mapping of rows to this lab's resources is uncertain)"
    fi
  else
    check_warn E15 "pricing get-products failed (the price list endpoint is in us-east-1; permission pricing:GetProducts is needed)"
  fi
  if tags=$(aws_owner ce list-cost-allocation-tags --tag-keys Project); then
    status=$(printf '%s' "$tags" | jq -r '[.CostAllocationTags[]? | select(.TagKey == "Project")][0].Status // "none"')
    if [ "$status" = Active ]; then
      check_pass E15 "the Project cost allocation tag is active"
    else
      check_warn E15 "the Project cost allocation tag is not active ($status): 06_verify.sh --cost cannot filter by it"
      echo "  To activate it, run this with credentials of the payer account (this lab never runs it):"
      echo "    aws ce update-cost-allocation-tags-status --cost-allocation-tags-status TagKey=Project,Status=Active --profile <payer-account-profile>"
    fi
  else
    check_warn E15 "ce list-cost-allocation-tags failed (the payer account's credentials may be needed)"
  fi
}

# --------------------------------------------------------------------------
# Run
# --------------------------------------------------------------------------
if [ "$DO_OWNER" = 1 ] && [ "$OWNER_OK" = 1 ]; then
  section "Owner account"
  owner_network
  lab_region_set "$LAB_PRIMARY_REGION"
  owner_primary
  for region in $(lab_regions); do
    lab_region_set "$region"
    owner_region "$region"
  done
  lab_region_set "$LAB_PRIMARY_REGION"
  organization_state
fi

if [ "$DO_RECIPIENT" = 1 ] && [ "$RECIPIENT_OK" = 1 ]; then
  section "Recipient account"
  for region in $(lab_regions); do
    lab_region_set "$region"
    recipient_region "$region"
  done
  lab_region_set "$LAB_PRIMARY_REGION"
  if by_shared_out=$(aws_recipient backup list-backup-vaults --by-shared 2>&1); then
    check_pass - "the AWS CLI accepts --by-shared (shared vaults visible to the recipient: $(printf '%s' "$by_shared_out" | jq -r '[.BackupVaultList[]?] | length'))"
  else
    case $by_shared_out in
      *"Unknown options"* | *"Unknown option"*) check_fail - "this AWS CLI does not know --by-shared; update the AWS CLI" ;;
      *) check_warn - "backup list-backup-vaults --by-shared failed for another reason" ;;
    esac
  fi
fi

section "Permissions"
if [ "$DO_OWNER" = 1 ] && [ "$OWNER_OK" = 1 ]; then
  lab_region_set "$LAB_PRIMARY_REGION"
  permission_check owner "$OWNER_CALLER_ARN"
fi
if [ "$DO_RECIPIENT" = 1 ] && [ "$RECIPIENT_OK" = 1 ]; then
  lab_region_set "$LAB_PRIMARY_REGION"
  permission_check recipient "$RECIPIENT_CALLER_ARN"
fi

if [ "$ESTIMATE" = 1 ] && [ "$OWNER_OK" = 1 ]; then
  lab_region_set "$LAB_PRIMARY_REGION"
  estimate_cost
fi

section "Result"
if summary; then
  exit 0
fi
exit 78
