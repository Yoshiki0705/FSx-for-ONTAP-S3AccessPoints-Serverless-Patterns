#!/bin/bash
# Real-environment run: not yet done (status source: docs/verification-record.md)
#
# 07_portal_config.sh - connect the recipient's portal to the shared vault and check
# the result (items V3, V5 and V6). The portal runs in the recipient account.
#
# Usage:
#   07_portal_config.sh --print
#   07_portal_config.sh --check [--expect arn-missing|arn-present|revoked] [--function-name NAME]
#   07_portal_config.sh --deploy [--stage regions-only|full] [--identifier NAME] [--apply]
#   07_portal_config.sh --ui --expect arn-missing|arn-present|revoked [--provision-user] [--apply]
#
#   --print   Read the shared vault ARNs from the recipient's list of shared vaults (never
#             built by string), read the restore settings from the recipient stack, print
#             them as KEY=value lines on stdout and write $LAB_ROOT/portal.local.env.
#   --check   Read-only. Find the deployed recipient-points function (by --function-name,
#             LAB_PORTAL_FUNCTION_NAME or its exact description; exactly one), read its
#             BACKUP_REGIONS and the AwsBackupRead inline policy, then invoke it twice
#             (listSharedBackupVaults, listRecoveryPoints with the owner account id).
#             With --expect the result is judged; a mismatch fails (exit 1) and prints
#             what was expected and what was measured. revoked requires VaultNotShared:
#             a plain AccessDeniedException is a failure.
#   --deploy  Update (or create) the portal sandbox with the settings above. regions-only
#             sets the Region list only (the state before the vault ARN is added); full
#             also sets the vault ARNs and restore settings from portal.local.env. A new
#             sandbox needs --identifier. Without --apply only the plan is shown (exit 10).
#             The exit status of the sandbox command is never used as the success signal:
#             success means every amplify- stack that changed (compared with a snapshot
#             taken from AWS before the run) reached CREATE_COMPLETE or UPDATE_COMPLETE.
#   --ui      Run the Playwright spec of the portal (solutions/amplify-portal/tests/e2e/
#             shared-vault-lab.spec.ts) for one expected state. Without --apply only the
#             plan is shown (exit 10). --apply installs what is missing locally (npm ci,
#             the chromium browser) and runs the spec. Credentials: PORTAL_USER and
#             PORTAL_PASSWORD from the environment first, then portal-user.local.env;
#             with --provision-user --apply a demo user is created through
#             "make portal-demo-user" and its password is saved to portal-user.local.env
#             (mode 0600) and never printed.
#
# Every child process that can reach AWS (the sandbox command, make, npx) runs in a
# subshell that first calls portal_env (the recipient profile and the primary Region, no
# static keys) and assert_ambient_account (the account those children would act in must
# be the recipient account), from a fixed directory.
#
# Exit codes: 0 success, 1 failure or refusal (also: a mismatch with --expect, no stack
# changed, a failed spec), 2 usage error, 10 plan only or a prerequisite that --apply
# installs, 75 missing tool (node, npm, npx), 78 not used here (01 only).
#
# Not yet run on real environment: the stack name pattern and the update behaviour of the
# sandbox, the browser run of the spec, and the output format of make portal-demo-user.

set -euo pipefail
# shellcheck source-path=SCRIPTDIR
# shellcheck source=lib/common.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

# The values of --expect (also the values of LAB_UI_EXPECT in the spec).
EXPECT_VALUES="arn-missing arn-present revoked"
# The description the recovery-points function is deployed with (amplify backend).
PORTAL_CHECK_DESCRIPTION="Lists AWS Backup recovery points for FSx for ONTAP volumes (read-only)"
ENV_FILE="$LAB_ROOT/portal.local.env"
CRED_FILE="$LAB_ROOT/portal-user.local.env"
RESULT_FILE="$LAB_ROOT/ui-result.local.json"

usage() {
  cat <<'EOF'
Usage: 07_portal_config.sh --print
       07_portal_config.sh --check [--expect arn-missing|arn-present|revoked] [--function-name NAME]
       07_portal_config.sh --deploy [--stage regions-only|full] [--identifier NAME] [--apply]
       07_portal_config.sh --ui --expect arn-missing|arn-present|revoked [--provision-user] [--apply]
Without --apply, --deploy and --ui only print the plan (exit 10).
EOF
}

# --------------------------------------------------------------------------
# Arguments
# --------------------------------------------------------------------------
MODE=""
EXPECT=""
FUNCTION_NAME=""
STAGE=full
IDENTIFIER=""
PROVISION=0
APPLY_ARG=0

set_mode() {
  if [ -n "$MODE" ]; then
    die_usage "only one of --print, --check, --deploy and --ui can be used"
  fi
  MODE=$1
}

validate_expect() {
  case $1 in
    arn-missing | arn-present | revoked) ;;
    *) die_usage "--expect must be one of: $EXPECT_VALUES" ;;
  esac
}

while [ "$#" -gt 0 ]; do
  case $1 in
    --print | --check | --deploy | --ui)
      set_mode "${1#--}"
      shift
      ;;
    --expect)
      if [ "$#" -lt 2 ]; then
        die_usage "--expect needs a value"
      fi
      validate_expect "$2"
      EXPECT=$2
      shift 2
      ;;
    --function-name)
      if [ "$#" -lt 2 ]; then
        die_usage "--function-name needs a value"
      fi
      FUNCTION_NAME=$2
      shift 2
      ;;
    --stage)
      if [ "$#" -lt 2 ]; then
        die_usage "--stage needs regions-only or full"
      fi
      STAGE=$2
      shift 2
      ;;
    --identifier)
      if [ "$#" -lt 2 ]; then
        die_usage "--identifier needs a value"
      fi
      IDENTIFIER=$2
      shift 2
      ;;
    --provision-user)
      PROVISION=1
      shift
      ;;
    --apply)
      APPLY_ARG=1
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

if [ -z "$MODE" ]; then
  usage >&2
  die_usage "one of --print, --check, --deploy or --ui is required"
fi
case $STAGE in
  regions-only | full) ;;
  *) die_usage "--stage must be regions-only or full" ;;
esac
if [ -n "$IDENTIFIER" ] && ! [[ $IDENTIFIER =~ ^[A-Za-z0-9-]{1,40}$ ]]; then
  die_usage "--identifier must be 1-40 characters of letters, digits and -"
fi
if [ -n "$FUNCTION_NAME" ] && ! [[ $FUNCTION_NAME =~ ^[A-Za-z0-9_-]{1,64}$ ]]; then
  die_usage "--function-name is not a Lambda function name"
fi
if [ "$APPLY_ARG" = 1 ] && { [ "$MODE" = print ] || [ "$MODE" = check ]; }; then
  die_usage "--apply is not used with --$MODE (it never changes AWS state)"
fi
if [ "$PROVISION" = 1 ] && [ "$MODE" != ui ]; then
  die_usage "--provision-user is used with --ui only"
fi
if [ -n "$FUNCTION_NAME" ] && [ "$MODE" != check ]; then
  die_usage "--function-name is used with --check only"
fi
if [ "$MODE" = ui ] && [ -z "$EXPECT" ]; then
  die_usage "--ui needs --expect ($EXPECT_VALUES)"
fi
if [ "$MODE" != check ] && [ "$MODE" != ui ] && [ -n "$EXPECT" ]; then
  die_usage "--expect is used with --check and --ui only"
fi

# --------------------------------------------------------------------------
# --print
# --------------------------------------------------------------------------
mode_print() {
  local region found count rows arns="" stack_json rc content tmp role svm fs
  assert_account recipient
  for region in $(lab_regions); do
    lab_region_set "$region"
    if ! found=$(aws_recipient backup list-backup-vaults --by-shared); then
      die "backup list-backup-vaults --by-shared failed in $region"
    fi
    # The ARN comes from the response. The owner account is the fifth ARN field.
    rows=$(printf '%s' "$found" | jq -c --arg n "$LAB_LAG_VAULT_NAME" --arg o "$LAB_OWNER_ACCOUNT_ID" \
      '[.BackupVaultList[]? | select(.BackupVaultName == $n and (((.BackupVaultArn // "") | split(":")[4]) == $o)) | .BackupVaultArn]')
    count=$(printf '%s' "$rows" | jq -r 'length')
    if [ "$count" -gt 1 ]; then
      die "shared vaults named $LAB_LAG_VAULT_NAME owned by $LAB_OWNER_ACCOUNT_ID in $region: expected at most one (rows=$count)"
    fi
    if [ "$count" = 0 ]; then
      if [ "$region" = "$LAB_PRIMARY_REGION" ]; then
        die "the shared vault $LAB_LAG_VAULT_NAME of account $LAB_OWNER_ACCOUNT_ID is not visible in $region: run 05_accept_share.sh first"
      fi
      echo "warning: the shared vault is not visible in $region; its ARN is not added" >&2
      continue
    fi
    arns="${arns:+$arns,}$(printf '%s' "$rows" | jq -r '.[0]')"
  done
  lab_region_set "$LAB_PRIMARY_REGION"
  if stack_json=$(describe_stack recipient "${LAB_TAG}-recipient-${LAB_PRIMARY_REGION}"); then
    :
  else
    rc=$?
    if [ "$rc" = 4 ]; then
      die "stack ${LAB_TAG}-recipient-${LAB_PRIMARY_REGION} does not exist: run 02_deploy.sh --side recipient --apply first"
    fi
    die "stack ${LAB_TAG}-recipient-${LAB_PRIMARY_REGION} could not be read"
  fi
  if ! role=$(stack_value_one "recipient-restore RestoreRoleArn" "$stack_json" Outputs RestoreRoleArn); then exit 1; fi
  if ! svm=$(stack_value_one "recipient-restore RestoreSvmId" "$stack_json" Outputs RestoreSvmId); then exit 1; fi
  if ! fs=$(stack_value_one "recipient-restore FileSystemId" "$stack_json" Outputs FileSystemId); then exit 1; fi
  content=$(printf '%s\n' \
    "# Written by 07_portal_config.sh --print. A local file: do not commit it." \
    "AMPLIFY_PORTAL_BACKUP_REGIONS=${LAB_SECOND_REGION:-}" \
    "AMPLIFY_PORTAL_BACKUP_VAULT_ARNS=$arns" \
    "AMPLIFY_PORTAL_RESTORE_ROLE_ARN=$role" \
    "AMPLIFY_PORTAL_RESTORE_SVM_IDS=$svm" \
    "AMPLIFY_PORTAL_RESTORE_FILE_SYSTEM_IDS=$fs")
  tmp="$ENV_FILE.tmp.$$"
  printf '%s\n' "$content" >"$tmp"
  mv "$tmp" "$ENV_FILE"
  printf '%s\n' "$content"
  echo "wrote $ENV_FILE" >&2
}

# --------------------------------------------------------------------------
# --check
# --------------------------------------------------------------------------
INVOKE_BODY=""
# portal_invoke FUNCTION PAYLOAD: call the function; the response document is left in
# INVOKE_BODY. Returns 1 when the call fails, the function reports an error, or the
# response is not a JSON object.
portal_invoke() {
  local fn=$1 payload=$2 out_file inv
  out_file=$(mktemp)
  if ! inv=$(aws_recipient lambda invoke --function-name "$fn" --cli-binary-format raw-in-base64-out --payload "$payload" "$out_file"); then
    rm -f "$out_file"
    return 1
  fi
  INVOKE_BODY=$(cat "$out_file")
  rm -f "$out_file"
  if [ "$(printf '%s' "$inv" | jq -r '.FunctionError // empty' 2>/dev/null)" != "" ]; then
    return 1
  fi
  printf '%s' "$INVOKE_BODY" | jq -e 'type == "object"' >/dev/null 2>&1
}

mode_check() {
  local fns names fn_row fn_name role_arn role_name policy_json resources regions_env
  local shared_body shared_err shared_hits shared_arn rp_body rp_err rp_rows
  lab_apply_on
  assert_account recipient
  require_sso_minutes "$LAB_RECIPIENT_PROFILE" "$LAB_MIN_SSO_MINUTES"

  if ! fns=$(aws_recipient lambda list-functions); then
    die "lambda list-functions failed"
  fi
  fn_name=${FUNCTION_NAME:-${LAB_PORTAL_FUNCTION_NAME:-}}
  if [ -n "$fn_name" ]; then
    names=$(printf '%s' "$fns" | jq -c --arg n "$fn_name" '[.Functions[]? | select(.FunctionName == $n) | .FunctionName]')
  else
    names=$(printf '%s' "$fns" | jq -c --arg d "$PORTAL_CHECK_DESCRIPTION" '[.Functions[]? | select(.Description == $d) | .FunctionName]')
  fi
  if [ "$(printf '%s' "$names" | jq -r 'length')" = 0 ]; then
    if [ -n "$fn_name" ]; then
      check_fail - "recovery-points function not found by name: $fn_name (07_portal_config.sh --deploy creates the portal)"
    else
      check_fail - "recovery-points function not found by its description \"$PORTAL_CHECK_DESCRIPTION\": deploy the portal first (07_portal_config.sh --deploy)"
    fi
    summary || true
    exit 1
  fi
  if [ "$(printf '%s' "$names" | jq -r 'length')" -gt 1 ]; then
    printf '%s' "$names" | jq -r '.[] | "  candidate: \(.)"' >&2
    die "more than one function matches (rows=$(printf '%s' "$names" | jq -r 'length')); choose one with --function-name"
  fi
  fn_name=$(printf '%s' "$names" | jq -r '.[0]')
  fn_row=$(printf '%s' "$fns" | jq -c --arg n "$fn_name" '[.Functions[] | select(.FunctionName == $n)][0]')
  echo "Function : $fn_name (Region $LAB_PRIMARY_REGION, expect ${EXPECT:-not set: report only})"

  regions_env=$(printf '%s' "$fn_row" | jq -r '.Environment.Variables.BACKUP_REGIONS // ""')
  if [ -n "${LAB_SECOND_REGION:-}" ]; then
    if printf '%s' "$regions_env" | jq -e --arg r "$LAB_SECOND_REGION" 'index($r) != null' >/dev/null 2>&1; then
      check_pass - "BACKUP_REGIONS of the function includes $LAB_SECOND_REGION"
    else
      check_warn - "BACKUP_REGIONS of the function does not include $LAB_SECOND_REGION (measured: ${regions_env:-empty}); run --deploy --stage regions-only --apply"
    fi
  else
    echo "  BACKUP_REGIONS : ${regions_env:-empty}"
  fi

  # Step 1: what the portal can list (needs no vault ARN in the role policy).
  if ! portal_invoke "$fn_name" "$(json_build action listSharedBackupVaults)"; then
    check_fail V5 "listSharedBackupVaults could not be invoked or returned an error: $(printf '%s' "$INVOKE_BODY" | head -c 300)"
    summary || true
    exit 1
  fi
  shared_body=$INVOKE_BODY
  shared_err=$(printf '%s' "$shared_body" | jq -r '.errorCode // empty')
  shared_hits=$(printf '%s' "$shared_body" | jq -c --arg n "$LAB_LAG_VAULT_NAME" --arg o "$LAB_OWNER_ACCOUNT_ID" \
    '[.backupVaults[]? | select(.backupVaultName == $n and .ownerAccountId == $o)]')
  shared_arn=$(printf '%s' "$shared_hits" | jq -r '.[0].backupVaultArn // empty')

  # Step 2: the inline policy of the function role (the ARNs the portal may read).
  role_arn=$(printf '%s' "$fn_row" | jq -r '.Role // ""')
  role_name=${role_arn##*/}
  resources=""
  if [ -n "$role_name" ] && policy_json=$(aws_recipient iam get-role-policy --role-name "$role_name" --policy-name AwsBackupRead); then
    resources=$(printf '%s' "$policy_json" | jq -c '
      [(.PolicyDocument.Statement // []) | (if type == "array" then . else [.] end)[]
       | select(.Effect == "Allow")
       | select((.Action // []) | (if type == "array" then . else [.] end) | index("backup:ListRecoveryPointsByBackupVault"))
       | (.Resource // []) | (if type == "array" then . else [.] end)[]]')
  else
    check_warn - "the AwsBackupRead inline policy of role ${role_name:-unknown} could not be read; the policy comparison is skipped"
  fi

  # Step 3: the recovery points of the shared vault, read with the owner account id.
  if ! portal_invoke "$fn_name" "$(json_build action listRecoveryPoints backupVaultName "$LAB_LAG_VAULT_NAME" backupVaultAccountId "$LAB_OWNER_ACCOUNT_ID")"; then
    check_fail V3 "listRecoveryPoints could not be invoked or returned an error: $(printf '%s' "$INVOKE_BODY" | head -c 300)"
    summary || true
    exit 1
  fi
  rp_body=$INVOKE_BODY
  rp_err=$(printf '%s' "$rp_body" | jq -r '.errorCode // empty')
  rp_rows=$(printf '%s' "$rp_body" | jq -r '[.recoveryPoints[]?] | length')
  echo "  measured: listSharedBackupVaults errorCode=${shared_err:-none} matching vaults=$(printf '%s' "$shared_hits" | jq -r 'length')"
  echo "  measured: listRecoveryPoints errorCode=${rp_err:-none} rows=$rp_rows"

  if [ -z "$EXPECT" ]; then
    echo "  no --expect given: the state is reported, not judged"
    summary || true
    exit 0
  fi
  judge_check "$shared_err" "$shared_hits" "$shared_arn" "$resources" "$rp_err" "$rp_rows"
  if summary; then
    exit 0
  fi
  exit 1
}

# judge_check SHARED_ERR SHARED_HITS SHARED_ARN POLICY_RESOURCES RP_ERR RP_ROWS
judge_check() {
  local shared_err=$1 hits=$2 arn=$3 resources=$4 rp_err=$5 rp_rows=$6 hit_count
  hit_count=$(printf '%s' "$hits" | jq -r 'length')
  case $EXPECT in
    arn-missing | arn-present)
      if [ -z "$shared_err" ] && [ "$hit_count" -ge 1 ]; then
        check_pass V5 "listSharedBackupVaults succeeded and lists $LAB_LAG_VAULT_NAME owned by $LAB_OWNER_ACCOUNT_ID"
      else
        check_fail V5 "expected listSharedBackupVaults to succeed and list $LAB_LAG_VAULT_NAME owned by $LAB_OWNER_ACCOUNT_ID; measured errorCode=${shared_err:-none}, matching vaults=$hit_count"
      fi
      ;;
  esac
  case $EXPECT in
    arn-missing)
      if [ "$rp_err" = AccessDeniedException ]; then
        check_pass V3 "arn-missing: listRecoveryPoints with the owner account id was denied (AccessDeniedException), as expected before the vault ARN is added"
      else
        check_fail V3 "arn-missing: expected AccessDeniedException from listRecoveryPoints; measured errorCode=${rp_err:-none}, rows=$rp_rows"
      fi
      if [ -n "$arn" ] && [ -n "$resources" ]; then
        if printf '%s' "$resources" | jq -e --arg a "$arn" 'index($a) == null' >/dev/null; then
          check_pass V3 "arn-missing: the role policy does not list the shared vault ARN"
        else
          check_fail V3 "arn-missing: expected the shared vault ARN to be absent from the role policy; measured: present"
        fi
      fi
      ;;
    arn-present)
      if [ -z "$rp_err" ] && [ "$rp_rows" -ge 1 ]; then
        check_pass V3 "arn-present: listRecoveryPoints returned $rp_rows row(s) for the shared vault"
      else
        check_fail V3 "arn-present: expected at least one recovery point and no errorCode; measured errorCode=${rp_err:-none}, rows=$rp_rows"
      fi
      if [ -n "$arn" ] && [ -n "$resources" ]; then
        if printf '%s' "$resources" | jq -e --arg a "$arn" 'index($a) != null' >/dev/null; then
          check_pass V3 "arn-present: the role policy lists the shared vault ARN"
        else
          check_fail V3 "arn-present: expected the shared vault ARN in the role policy; measured: absent"
        fi
      fi
      ;;
    revoked)
      record_event api_code V6 "listRecoveryPoints errorCode=${rp_err:-none} listSharedBackupVaults errorCode=${shared_err:-none}"
      if [ -z "$shared_err" ] && [ "$hit_count" = 0 ]; then
        check_pass V6 "revoked: listSharedBackupVaults no longer lists $LAB_LAG_VAULT_NAME"
      else
        check_fail V6 "revoked: expected listSharedBackupVaults to succeed without $LAB_LAG_VAULT_NAME; measured errorCode=${shared_err:-none}, matching vaults=$hit_count"
      fi
      if [ "$rp_err" = VaultNotShared ]; then
        check_pass V6 "revoked: listRecoveryPoints returned VaultNotShared"
      else
        check_fail V6 "revoked: expected VaultNotShared from listRecoveryPoints (a plain AccessDeniedException is not enough); measured errorCode=${rp_err:-none}, rows=$rp_rows"
      fi
      ;;
  esac
}

# --------------------------------------------------------------------------
# --deploy
# --------------------------------------------------------------------------

# check_env_file: in the parent, reject an unexpected key in portal.local.env before the
# deploy starts. deploy_env reads the same file inside a subshell, so its own guard cannot
# stop the parent.
check_env_file() {
  local line key
  while IFS= read -r line || [ -n "$line" ]; do
    case $line in
      '' | '#'*) continue ;;
    esac
    key=${line%%=*}
    case $key in
      AMPLIFY_PORTAL_BACKUP_REGIONS | AMPLIFY_PORTAL_BACKUP_VAULT_ARNS | AMPLIFY_PORTAL_RESTORE_ROLE_ARN | \
        AMPLIFY_PORTAL_RESTORE_SVM_IDS | AMPLIFY_PORTAL_RESTORE_FILE_SYSTEM_IDS) ;;
      *) die "unexpected key in portal.local.env: $key" ;;
    esac
  done <"$ENV_FILE"
}

# deploy_env: runs in the subshell of the sandbox command. The reader's own values of the
# settings are cleared first, so the stage decides what the portal gets.
deploy_env() {
  local line key val
  unset AMPLIFY_PORTAL_BACKUP_REGIONS AMPLIFY_PORTAL_BACKUP_VAULT_ARNS \
    AMPLIFY_PORTAL_RESTORE_ROLE_ARN AMPLIFY_PORTAL_RESTORE_SVM_IDS AMPLIFY_PORTAL_RESTORE_FILE_SYSTEM_IDS
  if [ "$STAGE" = regions-only ]; then
    if [ -n "${LAB_SECOND_REGION:-}" ]; then
      export AMPLIFY_PORTAL_BACKUP_REGIONS=$LAB_SECOND_REGION
    fi
  else
    while IFS= read -r line || [ -n "$line" ]; do
      case $line in
        '' | '#'*) continue ;;
      esac
      key=${line%%=*}
      val=${line#*=}
      case $key in
        AMPLIFY_PORTAL_BACKUP_REGIONS | AMPLIFY_PORTAL_BACKUP_VAULT_ARNS | AMPLIFY_PORTAL_RESTORE_ROLE_ARN | \
          AMPLIFY_PORTAL_RESTORE_SVM_IDS | AMPLIFY_PORTAL_RESTORE_FILE_SYSTEM_IDS)
          if [ -n "$val" ]; then
            export "$key=$val"
          fi
          ;;
        *) die "unexpected key in portal.local.env: $key" ;;
      esac
    done <"$ENV_FILE"
  fi
  if [ -n "$IDENTIFIER" ]; then
    export AMPLIFY_PORTAL_SANDBOX_IDENTIFIER=$IDENTIFIER
  fi
}

# amplify_snapshot: [{name, stamp, status}] of the amplify- stacks, read from AWS. The
# stamp is LastUpdatedTime, or CreationTime for a stack never updated. No local clock.
amplify_snapshot() {
  local out
  if ! out=$(aws_recipient cloudformation describe-stacks); then
    return 1
  fi
  printf '%s' "$out" | jq -c '
    [.Stacks[]? | select(.StackName | startswith("amplify-"))
     | {name: .StackName, stamp: ((.LastUpdatedTime // .CreationTime // "") | tostring), status: .StackStatus}]
    | sort_by(.name)'
}

# changed_stacks BEFORE AFTER: stacks of AFTER that are new or have another stamp.
changed_stacks() {
  jq -cn --argjson b "$1" --argjson a "$2" '
    [$a[] | . as $s | select(([$b[] | select(.name == $s.name and .stamp == $s.stamp)] | length) == 0)]'
}

AFTER_SNAPSHOT="[]"
CHANGED="[]"
BEFORE_SNAPSHOT="[]"
# shellcheck disable=SC2329  # invoked through wait_until
poll_stacks() {
  AFTER_SNAPSHOT=$(amplify_snapshot) || return 2
  CHANGED=$(changed_stacks "$BEFORE_SNAPSHOT" "$AFTER_SNAPSHOT")
  if printf '%s' "$CHANGED" | jq -e 'any(.[]; .status | endswith("IN_PROGRESS"))' >/dev/null; then
    return 1
  fi
  return 0
}

# failure_reasons STACK...: up to five FAILED event reasons over all the stacks.
failure_reasons() {
  local left=5 name out lines taken
  for name in "$@"; do
    if [ "$left" -le 0 ]; then
      break
    fi
    if ! out=$(aws_recipient cloudformation describe-stack-events --stack-name "$name"); then
      echo "  (the events of $name could not be read)"
      continue
    fi
    lines=$(printf '%s' "$out" | jq -r --argjson n "$left" '
      [.StackEvents[]? | select((.ResourceStatus // "") | test("FAILED"))][0:$n][]
      | "  \(.StackName // "-") \(.LogicalResourceId): \(.ResourceStatusReason // "no reason given")"')
    if [ -n "$lines" ]; then
      printf '%s\n' "$lines"
      taken=$(printf '%s\n' "$lines" | grep -c . || true)
      left=$((left - taken))
    fi
  done
}

# resolve_identifier: the sandbox identifier, refusing a disagreement with the deployed one.
resolve_identifier() {
  local outputs="$LAB_PORTAL_DIR/amplify_outputs.json" deployed rc
  : "${IDENTIFIER:=${LAB_PORTAL_SANDBOX_ID:-${AMPLIFY_PORTAL_SANDBOX_IDENTIFIER:-}}}"
  if [ ! -f "$outputs" ]; then
    if [ -z "$IDENTIFIER" ]; then
      die_usage "--identifier is required for a new sandbox (no amplify_outputs.json in $LAB_PORTAL_DIR)"
    fi
    return 0
  fi
  if [ -z "$IDENTIFIER" ]; then
    return 0
  fi
  rc=0
  deployed=$( (portal_env; assert_ambient_account; run_external python3 "$LAB_REPO_ROOT/scripts/portal_preflight.py" --print-sandbox-identifier) ) || rc=$?
  if [ "$rc" -ne 0 ] || [ -z "$deployed" ]; then
    die "amplify_outputs.json exists but its sandbox could not be identified (exit $rc); nothing was started"
  fi
  if [ "$deployed" != "$IDENTIFIER" ]; then
    die_usage "--identifier $IDENTIFIER disagrees with the deployed sandbox $deployed: a second sandbox would be created beside it; use --identifier $deployed or a fresh checkout"
  fi
}

mode_deploy() {
  local need_ci=0 need_config=0 failed_names reasons status_text n sandbox_rc=0
  need_cmd node
  need_cmd npm
  if [ ! -d "$LAB_PORTAL_DIR" ]; then
    die "portal directory not found: $LAB_PORTAL_DIR (set LAB_PORTAL_DIR)"
  fi
  assert_account recipient
  require_sso_minutes "$LAB_RECIPIENT_PROFILE" "$LAB_MIN_SSO_MINUTES"
  resolve_identifier
  if [ "$STAGE" = full ] && [ ! -f "$ENV_FILE" ]; then
    echo "portal.local.env does not exist: run ./scripts/07_portal_config.sh --print first, then repeat this command."
    exit 10
  fi
  if [ "$STAGE" = full ]; then
    # Validate the env file in the parent: deploy_env reads it inside the sandbox
    # subshell, where a die would end only that subshell and let the deploy proceed.
    check_env_file
  fi
  if [ ! -x "$LAB_PORTAL_DIR/node_modules/.bin/ampx" ]; then
    need_ci=1
  fi
  if [ ! -f "$LAB_PORTAL_DIR/amplify/portal-config.ts" ]; then
    need_config=1
  fi

  echo "Portal   : $LAB_PORTAL_DIR (stage $STAGE${IDENTIFIER:+, sandbox identifier $IDENTIFIER})"
  if [ "$need_config" = 1 ]; then
    echo "Missing  : amplify/portal-config.ts. Planned: cp amplify/portal-config.example.ts amplify/portal-config.ts (in $LAB_PORTAL_DIR)"
  fi
  if [ "$need_ci" = 1 ]; then
    echo "Missing  : node_modules/.bin/ampx. Planned: npm ci (in $LAB_PORTAL_DIR)"
  fi
  impact_begin
  impact "changes" "the Amplify sandbox of the portal in account $LAB_RECIPIENT_ACCOUNT_ID, Region $LAB_PRIMARY_REGION (stage $STAGE)"
  impact "sets" "$(if [ "$STAGE" = full ]; then echo 'Region list, vault ARNs and restore settings from portal.local.env'; else echo "the Region list only (${LAB_SECOND_REGION:-no second Region}); no vault ARN"; fi)"
  impact "exit status" "the sandbox command's exit status is not used; success is judged from the amplify- stacks that changed"
  impact "remove later" "make sandbox-delete in $LAB_PORTAL_DIR (10_teardown.sh lists it and never runs it)"
  plan_gate "./scripts/07_portal_config.sh --deploy --stage $STAGE${IDENTIFIER:+ --identifier $IDENTIFIER} --apply"

  # The account the children would act in is checked before anything is installed or changed.
  if ! ( portal_env; assert_ambient_account ); then
    exit 1
  fi
  if [ "$need_ci" = 1 ]; then
    ( portal_env; assert_ambient_account; cd "$LAB_PORTAL_DIR" && run_external npm ci ) || die "npm ci failed in $LAB_PORTAL_DIR: nothing was deployed"
  fi
  if [ "$need_config" = 1 ]; then
    cp "$LAB_PORTAL_DIR/amplify/portal-config.example.ts" "$LAB_PORTAL_DIR/amplify/portal-config.ts"
  fi
  if ! BEFORE_SNAPSHOT=$(amplify_snapshot); then
    die "cloudformation describe-stacks failed: the stacks before the deploy are unknown, nothing was started"
  fi
  record_event deploy_start - "stage=$STAGE stacks_before=$(printf '%s' "$BEFORE_SNAPSHOT" | jq -r 'length')"
  ( portal_env; assert_ambient_account; deploy_env; cd "$LAB_PORTAL_DIR" && run_external ./scripts/sandbox.sh --once ) || sandbox_rc=$?

  if ! wait_until "stacks of the sandbox" 900 30 poll_stacks; then
    check_fail - "the amplify- stacks could not be read or stayed IN_PROGRESS after the sandbox command (sandbox command exit $sandbox_rc)"
    summary || true
    exit 1
  fi
  n=$(printf '%s' "$CHANGED" | jq -r 'length')
  printf '%s' "$CHANGED" | jq -r '.[] | "  changed: \(.name) \(.status)"'
  if [ "$n" = 0 ]; then
    check_fail - "no amplify- stack was created or updated (sandbox command exit $sandbox_rc): the deploy did not take effect; check the sandbox output above"
  else
    failed_names=$(printf '%s' "$CHANGED" | jq -r '[.[] | select(.status != "CREATE_COMPLETE" and .status != "UPDATE_COMPLETE") | .name] | .[]')
    if [ -n "$failed_names" ]; then
      status_text=$(printf '%s' "$CHANGED" | jq -r '[.[] | select(.status != "CREATE_COMPLETE" and .status != "UPDATE_COMPLETE") | "\(.name)=\(.status)"] | join(", ")')
      check_fail - "stacks that changed did not reach CREATE_COMPLETE or UPDATE_COMPLETE: $status_text (sandbox command exit $sandbox_rc)"
      # shellcheck disable=SC2046  # one argument per stack name (names hold no spaces)
      reasons=$(failure_reasons $(printf '%s\n' "$failed_names"))
      if [ -n "$reasons" ]; then
        echo "  failure events (up to 5):"
        printf '%s\n' "$reasons"
      fi
      echo "  See docs/agent/portal-cdk-quality-gates.md (the AwsCliLayer row) and the existing-sandbox chapter of the runbook."
      echo "  A refused replacement of an existing sandbox is one possible cause; this script does not determine the cause."
    else
      check_pass - "$n amplify- stack(s) changed and reached CREATE_COMPLETE or UPDATE_COMPLETE"
      if [ "$sandbox_rc" -ne 0 ]; then
        check_warn - "the sandbox command exited $sandbox_rc although the stacks reached a complete state"
      fi
    fi
  fi
  if summary; then
    echo "Next: ./scripts/07_portal_config.sh --check --expect $(if [ "$STAGE" = full ]; then echo arn-present; else echo arn-missing; fi)"
    exit 0
  fi
  exit 1
}

# --------------------------------------------------------------------------
# --ui
# --------------------------------------------------------------------------
UI_USER=""
UI_PASSWORD=""
CRED_SOURCE=none

# resolve_credentials: environment first, then portal-user.local.env.
resolve_credentials() {
  local line file_user="" file_password="" perm
  if [ -n "${PORTAL_USER:-}" ] && [ -n "${PORTAL_PASSWORD:-}" ]; then
    UI_USER=$PORTAL_USER
    UI_PASSWORD=$PORTAL_PASSWORD
    CRED_SOURCE=environment
    return 0
  fi
  if [ -f "$CRED_FILE" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
      case $line in
        PORTAL_USER=*) file_user=${line#PORTAL_USER=} ;;
        PORTAL_PASSWORD=*) file_password=${line#PORTAL_PASSWORD=} ;;
      esac
    done <"$CRED_FILE"
    if [ -n "$file_user" ] && [ -n "$file_password" ]; then
      perm=$(find "$CRED_FILE" -maxdepth 0 \( -perm -g=r -o -perm -g=w -o -perm -g=x -o -perm -o=r -o -perm -o=w -o -perm -o=x \) -print)
      if [ -n "$perm" ]; then
        check_warn - "portal-user.local.env is readable or writable by group or others: run chmod 600 on it"
      fi
      UI_USER=$file_user
      UI_PASSWORD=$file_password
      CRED_SOURCE="file"
      return 0
    fi
  fi
  if [ "$PROVISION" = 1 ]; then
    CRED_SOURCE=provision
    return 0
  fi
  {
    echo "error: no portal credentials. Use one of:"
    echo "  (a) export PORTAL_USER and PORTAL_PASSWORD of a user in the storage-admin group"
    echo "  (b) ./scripts/07_portal_config.sh --ui --expect $EXPECT --provision-user --apply"
  } >&2
  exit 1
}

# write_cred_file USER PASSWORD: mode 0600, written by shell builtins only (the value is
# never an argument of another process).
write_cred_file() {
  ( umask 077; rm -f "$CRED_FILE"; printf 'PORTAL_USER=%s\nPORTAL_PASSWORD=%s\n' "$1" "$2" >"$CRED_FILE" )
  chmod 600 "$CRED_FILE"
}

# provision_user: create the demo user through make in the repository root, capture the
# output in a variable, read the single password line, save it, never print it.
provision_user() {
  local username=${PORTAL_USER:-lab-ui@example.com} make_args out rc=0 pw_rc=0 pool region
  if [ ! -f "$LAB_REPO_ROOT/Makefile" ] || ! grep -q '^portal-demo-user:' "$LAB_REPO_ROOT/Makefile"; then
    die "$LAB_REPO_ROOT/Makefile has no portal-demo-user target; run this lab from a full checkout of the repository"
  fi
  make_args="--username $username --groups storage-admin,internal"
  if [ -n "${LAB_PORTAL_SANDBOX_ID:-}" ]; then
    make_args="$make_args --expected-sandbox $LAB_PORTAL_SANDBOX_ID"
  fi
  out=$( (portal_env; assert_ambient_account; run_external make -C "$LAB_REPO_ROOT" portal-demo-user "ARGS=$make_args") ) || rc=$?
  if [ "$rc" -ne 0 ]; then
    printf '%s\n' "$out" | grep -v '^  password  ' >&2 || true
    die "make portal-demo-user failed (exit $rc)"
  fi
  UI_PASSWORD=$(printf '%s\n' "$out" | lab_py provision-password) || pw_rc=$?
  out=""
  case $pw_rc in
    0)
      UI_USER=$username
      write_cred_file "$UI_USER" "$UI_PASSWORD"
      CRED_SOURCE="file"
      echo "  demo user $username created; its password was saved to portal-user.local.env (mode 0600, not printed)"
      ;;
    3)
      pool=$(jq -r '.auth.user_pool_id // empty' "$LAB_PORTAL_DIR/amplify_outputs.json" 2>/dev/null || true)
      region=$(jq -r '.auth.aws_region // empty' "$LAB_PORTAL_DIR/amplify_outputs.json" 2>/dev/null || true)
      {
        echo "error: the user $username already exists and its password is unknown to this lab."
        echo "  Delete the user, then repeat this command (a new password is generated and saved):"
        echo "    aws cognito-idp admin-delete-user --user-pool-id ${pool:-<user pool id>} --username $username --region ${region:-$LAB_PRIMARY_REGION} --profile $LAB_RECIPIENT_PROFILE"
        echo "    ./scripts/07_portal_config.sh --ui --expect $EXPECT --provision-user --apply"
        echo "  Or export PORTAL_USER and PORTAL_PASSWORD of that user."
      } >&2
      exit 1
      ;;
    *)
      die "the output of make portal-demo-user held no password line and no 'already exists' notice; its print format may have changed (nothing was saved)"
      ;;
  esac
}

# redact_secret: stdin to stdout with every occurrence of $REDACT_VALUE (read from the
# environment, not from an argument) replaced.
redact_secret() {
  jq -Rs '. as $t | ($ENV.REDACT_VALUE // "") as $p | if $p == "" then $t else ($t | split($p) | join("<redacted>")) end' | jq -j '.'
}

mode_ui() {
  local need_ci=0 need_chromium=0 need_config=0 chromium_path="" ui_rc=0 stats expected unexpected skipped flaky
  local err_file verdict msg
  lab_set_variant ui
  need_cmd node
  need_cmd npm
  need_cmd npx
  if [ ! -d "$LAB_PORTAL_DIR" ]; then
    die "portal directory not found: $LAB_PORTAL_DIR (set LAB_PORTAL_DIR)"
  fi
  if [ ! -f "$LAB_PORTAL_DIR/amplify_outputs.json" ]; then
    die "no amplify_outputs.json in $LAB_PORTAL_DIR: deploy the portal first (07_portal_config.sh --deploy)"
  fi
  assert_account recipient
  if [ ! -d "$LAB_PORTAL_DIR/node_modules/@playwright/test" ]; then
    need_ci=1
    need_chromium=1
  else
    if chromium_path=$( cd "$LAB_PORTAL_DIR" && run_external node -e "console.log(require('@playwright/test').chromium.executablePath())" 2>/dev/null ) && [ -n "$chromium_path" ] && [ -e "$chromium_path" ]; then
      :
    else
      need_chromium=1
    fi
  fi
  if [ ! -f "$LAB_PORTAL_DIR/amplify/portal-config.ts" ]; then
    need_config=1
  fi
  resolve_credentials

  echo "Portal   : $LAB_PORTAL_DIR (expect $EXPECT, credentials: $CRED_SOURCE)"
  if [ "$need_ci" = 1 ]; then
    echo "Missing  : node_modules/@playwright/test. Planned: npm ci (in $LAB_PORTAL_DIR)"
  fi
  if [ "$need_chromium" = 1 ]; then
    echo "Missing  : the chromium browser. Planned: npx playwright install chromium (in $LAB_PORTAL_DIR)"
  fi
  if [ "$need_config" = 1 ]; then
    echo "Missing  : amplify/portal-config.ts. Planned: cp amplify/portal-config.example.ts amplify/portal-config.ts (in $LAB_PORTAL_DIR)"
  fi
  if [ "$CRED_SOURCE" = provision ]; then
    echo "Missing  : portal credentials. Planned: make -C $LAB_REPO_ROOT portal-demo-user (a demo user in the storage-admin group; the password goes to portal-user.local.env, mode 0600)"
  fi
  impact_begin
  impact "runs" "the Playwright spec shared-vault-lab for $EXPECT against ${PORTAL_URL:-the local dev server}; it never clicks the restore confirm button"
  impact "installs" "only into $LAB_PORTAL_DIR (node_modules, the chromium browser); no AWS state changes"
  impact "creates" "$(if [ "$CRED_SOURCE" = provision ]; then echo 'a demo user in the portal user pool of the recipient account'; else echo 'nothing in AWS'; fi)"
  plan_gate "./scripts/07_portal_config.sh --ui --expect $EXPECT$(if [ "$PROVISION" = 1 ]; then echo ' --provision-user'; fi) --apply"

  if [ "$CRED_SOURCE" = provision ]; then
    require_sso_minutes "$LAB_RECIPIENT_PROFILE" "$LAB_MIN_SSO_MINUTES"
  fi
  if [ "$need_ci" = 1 ]; then
    ( portal_env; assert_ambient_account; cd "$LAB_PORTAL_DIR" && run_external npm ci ) || die "npm ci failed in $LAB_PORTAL_DIR"
  fi
  if [ "$need_chromium" = 1 ]; then
    ( portal_env; assert_ambient_account; cd "$LAB_PORTAL_DIR" && run_external npx playwright install chromium ) || die "npx playwright install chromium failed in $LAB_PORTAL_DIR"
  fi
  if [ "$need_config" = 1 ]; then
    cp "$LAB_PORTAL_DIR/amplify/portal-config.example.ts" "$LAB_PORTAL_DIR/amplify/portal-config.ts"
  fi
  if [ "$CRED_SOURCE" = provision ]; then
    provision_user
  fi
  if ! ( portal_env; assert_ambient_account ); then
    exit 1
  fi

  err_file=$(mktemp)
  rm -f "$RESULT_FILE"
  (
    portal_env
    assert_ambient_account
    export PORTAL_USER="$UI_USER" PORTAL_PASSWORD="$UI_PASSWORD" LAB_UI_EXPECT="$EXPECT"
    export LAB_LAG_VAULT_NAME LAB_OWNER_ACCOUNT_ID
    export LAB_SECOND_REGION="${LAB_SECOND_REGION:-}" PORTAL_URL="${PORTAL_URL:-}"
    if [ -n "${LAB_CAPTURE_DIR:-}" ]; then
      export LAB_CAPTURE_DIR
    fi
    if [ -z "${PORTAL_URL:-}" ]; then
      unset CI
    fi
    # The file filter is a regex over the whole path. It ends in .spec.ts so a checkout path
    # that happens to contain "shared-vault-lab" cannot select the other specs as well.
    cd "$LAB_PORTAL_DIR" && run_external npx playwright test 'shared-vault-lab\.spec\.ts$' --reporter=json >"$RESULT_FILE" 2>"$err_file"
  ) || ui_rc=$?
  # The run may print an error that quotes the filled-in value: remove it from both outputs.
  (
    export REDACT_VALUE="$UI_PASSWORD"
    if [ -f "$RESULT_FILE" ]; then
      if redact_secret <"$RESULT_FILE" >"$RESULT_FILE.redacted"; then
        mv "$RESULT_FILE.redacted" "$RESULT_FILE"
      else
        rm -f "$RESULT_FILE" "$RESULT_FILE.redacted"
      fi
    fi
    if ! redact_secret <"$err_file" >&2; then
      echo "(the error output of the run was dropped: it could not be redacted)" >&2
    fi
  ) || true
  rm -f "$err_file"

  stats=""
  if [ -s "$RESULT_FILE" ]; then
    stats=$(jq -c '.stats | select(type == "object") | {expected: (.expected // 0), unexpected: (.unexpected // 0), skipped: (.skipped // 0), flaky: (.flaky // 0)}' "$RESULT_FILE" 2>/dev/null || true)
  fi
  if [ -z "$stats" ]; then
    check_fail E25 "the Playwright report could not be read (npx exit $ui_rc): the spec was not confirmed to run"
    summary || true
    exit 1
  fi
  expected=$(printf '%s' "$stats" | jq -r '.expected')
  unexpected=$(printf '%s' "$stats" | jq -r '.unexpected')
  skipped=$(printf '%s' "$stats" | jq -r '.skipped')
  flaky=$(printf '%s' "$stats" | jq -r '.flaky')
  jq -r '[.. | objects | select(has("specs")) | .specs[] | "  - \(.title): \(if .ok then "passed" else "not passed" end)"] | .[]' "$RESULT_FILE" 2>/dev/null || true
  echo "  measured: expected=$expected unexpected=$unexpected skipped=$skipped flaky=$flaky (npx exit $ui_rc)"
  verdict=pass
  if [ "$expected" -lt 1 ] || [ "$unexpected" -ne 0 ] || [ "$skipped" -ne 0 ]; then
    verdict=fail
  fi
  if [ "$ui_rc" -ne 0 ] && [ "$verdict" = pass ]; then
    check_fail E25 "npx exited $ui_rc although the report shows no failure: the run is not trusted"
  else
    check_pass E25 "the Playwright report was read (expected=$expected unexpected=$unexpected skipped=$skipped flaky=$flaky)"
  fi
  if [ "$verdict" = pass ]; then
    msg="$EXPECT: the spec ran $expected test(s) with no failure and no skip"
    case $EXPECT in
      arn-missing) check_pass V3 "$msg" ;;
      arn-present)
        check_pass V3 "$msg"
        check_pass V5 "$msg"
        ;;
      *) check_pass V6 "$msg" ;;
    esac
    check_pass E20 "$msg"
  else
    msg="$EXPECT: expected at least one passing test, no failure and no skip; measured expected=$expected unexpected=$unexpected skipped=$skipped (a skipped test is not a pass)"
    case $EXPECT in
      arn-missing) check_fail V3 "$msg" ;;
      arn-present)
        check_fail V3 "$msg"
        check_fail V5 "$msg"
        ;;
      *) check_fail V6 "$msg" ;;
    esac
    check_fail E20 "$msg"
  fi
  if [ "$flaky" -ge 1 ]; then
    check_warn E20 "$flaky test(s) passed only on retry: the run is not stable"
  fi
  if summary; then
    exit 0
  fi
  exit 1
}

# --------------------------------------------------------------------------
# Dispatch
# --------------------------------------------------------------------------
case $MODE in
  print) mode_print ;;
  check) mode_check ;;
  deploy) mode_deploy ;;
  ui) mode_ui ;;
esac
