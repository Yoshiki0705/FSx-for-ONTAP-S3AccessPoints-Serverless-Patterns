#!/bin/bash
# Real-environment run: not yet done (status source: docs/verification-record.md)
#
# 03_deploy_lag_share.sh - create the logically air-gapped (LAG) vault and share it.
#
# Usage:
#   03_deploy_lag_share.sh --retention-days N [--region REGION] [--apply --confirm TOKEN]
#   03_deploy_lag_share.sh --repair-share [--region REGION] [--apply]
#
#   --retention-days N   required to create. Integer 7 to 35. It becomes the
#                        vault's minimum AND maximum retention, so it also fixes
#                        how long every copy is kept. IRREVERSIBLE: the range
#                        cannot be changed later (a change replaces the vault),
#                        and the vault cannot be deleted while it holds a copy.
#   --region             one Region. Default: every configured Region, primary
#                        first.
#   --apply              deploy. Without it the script prints the plan and exits 10.
#   --confirm TOKEN      the token printed in the plan: lock-<N>d-<vault>@<regions>.
#                        It is accepted only as an argument, never from the
#                        environment.
#   --repair-share       recreate only the RAM share of an existing vault
#                        (ShareEnabled false, then true). The vault is not touched,
#                        so no token and no --retention-days are needed.
#
# After every deploy the script checks that exactly one ACTIVE share with the
# expected name exists. If the share was deleted outside the stack it says so and
# exits 1.
#
# Exit codes: 0 success, 1 failure or refusal (wrong token, failed stack state,
# retention mismatch, vault not available, share missing), 2 usage error,
# 10 plan only.
#
# Not yet run on real environment: that the template deploys, that the Rules
# assertion is enforced, that the share can be recreated by the ShareEnabled
# switch, and the wording about compliance mode and expiry.

set -euo pipefail
# shellcheck source-path=SCRIPTDIR
# shellcheck source=lib/common.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

usage() {
  cat <<'EOF'
Usage: 03_deploy_lag_share.sh --retention-days N [--region R] [--apply --confirm TOKEN]
       03_deploy_lag_share.sh --repair-share [--region R] [--apply]
Creates the air-gapped vault and the RAM share (irreversible retention). Without --apply only the plan is shown (exit 10).
EOF
}

RET=""
REPAIR=0
REGION_ARG=""
while [ "$#" -gt 0 ]; do
  case $1 in
    --retention-days)
      if [ "$#" -lt 2 ]; then
        die_usage "--retention-days needs a value (7 to 35)"
      fi
      RET=$2
      shift 2
      ;;
    --repair-share)
      REPAIR=1
      shift
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
if [ "$REPAIR" = 1 ]; then
  if [ -n "$RET" ]; then
    die_usage "--repair-share does not take --retention-days (the vault is not touched)"
  fi
else
  if [ -z "$RET" ]; then
    die_usage "--retention-days is required (integer 7 to 35); there is no default because the value cannot be changed later"
  fi
  validate_retention_days "$RET"
fi
if [ -n "$REGION_ARG" ]; then
  validate_region_arg "$REGION_ARG"
  REGION_LIST=$REGION_ARG
else
  REGION_LIST=$(lab_regions | tr '\n' ' ' | sed 's/ $//')
fi
# shellcheck disable=SC2086
REGIONS_JOINED=$(lab_join_plus $REGION_LIST)
TEMPLATE="$LAB_ROOT/cloudformation/owner-lag-share.yaml"

# vault_listed: 0 when the LAG vault name is in the vault list of the current Region,
# 1 when it is not; dies when the list cannot be read (never read as "absent").
vault_listed() {
  local vaults
  if ! vaults=$(aws_owner backup list-backup-vaults); then
    die "backup list-backup-vaults failed in ${_LAB_REGION:-$LAB_PRIMARY_REGION}: the vault state is unknown, nothing was changed"
  fi
  printf '%s' "$vaults" | jq -e --arg n "$LAB_LAG_VAULT_NAME" \
    '[.BackupVaultList[]? | select(.BackupVaultName == $n)] | length > 0' >/dev/null
}

# inspect_region REGION: read-only checks before any change. Sets STACK_STATE and
# STACK_RETENTION for the Region.
STACK_STATE=""
STACK_RETENTION=""
inspect_region() {
  local region=$1 stack="${LAB_TAG}-lag-$1" json rc class
  lab_region_set "$region"
  STACK_STATE=""
  STACK_RETENTION=""
  if json=$(describe_stack owner "$stack"); then
    STACK_STATE=$(printf '%s' "$json" | jq -r '.Stacks[0].StackStatus // empty')
    STACK_RETENTION=$(stack_value "$json" Parameters RetentionDays)
  else
    rc=$?
    if [ "$rc" != 4 ]; then
      die "the state of stack $stack could not be read in $region; nothing was changed"
    fi
  fi
  class=$(stack_status_class "$STACK_STATE")
  case $class in
    failed)
      echo "error: stack $stack is in $STACK_STATE in $region and cannot be deployed over." >&2
      stack_recovery_hint "$STACK_STATE" "$stack" "$region" "$LAB_OWNER_PROFILE" >&2
      exit 1
      ;;
    busy) die "stack $stack is $STACK_STATE in $region; wait for the operation to finish" ;;
  esac
  if [ "$REPAIR" = 0 ]; then
    if [ "$class" = ok ]; then
      if [ "$STACK_RETENTION" != "$RET" ]; then
        die "stack $stack already exists with RetentionDays=${STACK_RETENTION:-unknown}; --retention-days $RET would replace the vault (the old vault is retained and keeps its recovery points). Nothing was changed."
      fi
    elif vault_listed; then
      echo "error: a retained air-gapped vault named $LAB_LAG_VAULT_NAME exists in $region without the stack $stack." >&2
      echo "  It cannot be deleted while it holds a recovery point. Use another LAB_TAG (for example ${LAB_TAG}-2): every default name changes." >&2
      exit 1
    fi
  else
    if [ "$class" != ok ]; then
      die "--repair-share needs the stack $stack to be deployed (found: ${STACK_STATE:-none}) in $region; nothing was changed"
    fi
    if ! vault_listed; then
      die "--repair-share needs the vault $LAB_LAG_VAULT_NAME in $region, and it is not in the vault list; nothing was changed"
    fi
    if [ -z "$STACK_RETENTION" ]; then
      die "the RetentionDays parameter of $stack could not be read; nothing was changed"
    fi
  fi
}

# deploy_stack REGION SHARE_ENABLED RETENTION: one deploy of the stack.
deploy_stack() {
  local region=$1 enabled=$2 days=$3 stack="${LAB_TAG}-lag-$1" deploy_out
  local -a params
  params=(
    "LabTag=$LAB_TAG"
    "LagVaultName=$LAB_LAG_VAULT_NAME"
    "ShareName=$LAB_SHARE_NAME"
    "RetentionDays=$days"
    "AcknowledgeRetentionDays=$days"
    "RecipientAccountId=$LAB_RECIPIENT_ACCOUNT_ID"
    "AllowExternalPrincipals=$LAB_ALLOW_EXTERNAL_PRINCIPALS"
    "ShareEnabled=$enabled"
  )
  lab_region_set "$region"
  if ! deploy_out=$(aws_owner cloudformation deploy \
    --template-file "$TEMPLATE" \
    --stack-name "$stack" \
    --parameter-overrides "${params[@]}" \
    --tags "Project=$LAB_TAG" "Cleanup=delete-when-done" \
    --no-fail-on-empty-changeset 2>&1); then
    printf '%s\n' "$deploy_out" >&2
    echo "error: cloudformation deploy failed for $stack (ShareEnabled=$enabled)" >&2
    stack_failure_events owner "$stack"
    case $STACK_FAILURE_TEXT in
      *OperationNotPermitted*)
        check_fail E13 "the share was refused (OperationNotPermitted); LAB_ALLOW_EXTERNAL_PRINCIPALS=$LAB_ALLOW_EXTERNAL_PRINCIPALS needs organization sharing to be enabled for false (observed once; not yet run on real environment)"
        ;;
    esac
    exit 1
  fi
  record_event deploy_done - "$stack ShareEnabled=$enabled"
}

# poll_vault: 0 AVAILABLE, 1 still creating, 2 the poll or the vault failed.
VAULT_JSON=""
# shellcheck disable=SC2329,SC2317  # invoked through wait_until
poll_vault() {
  local state
  VAULT_JSON=$(aws_owner backup describe-backup-vault --backup-vault-name "$LAB_LAG_VAULT_NAME") || return 2
  state=$(printf '%s' "$VAULT_JSON" | jq -r '.VaultState // "UNKNOWN"')
  case $state in
    AVAILABLE) return 0 ;;
    CREATING) return 1 ;;
    *) return 2 ;;
  esac
}

# share_check REGION: exactly one ACTIVE share with the expected name (item E2).
share_check() {
  local region=$1 shares rows arn
  if ! shares=$(aws_owner ram get-resource-shares --resource-owner SELF --name "$LAB_SHARE_NAME" --resource-share-status ACTIVE); then
    check_fail E2 "ram get-resource-shares failed in $region"
    return 0
  fi
  rows=$(printf '%s' "$shares" | jq -c --arg n "$LAB_SHARE_NAME" '[.resourceShares[]? | select(.name == $n and .status == "ACTIVE")]')
  case $(printf '%s' "$rows" | jq -r 'length') in
    0)
      check_fail E2 "no ACTIVE resource share named $LAB_SHARE_NAME in $region: the share may have been deleted outside the stack. Run 03_deploy_lag_share.sh --repair-share --apply to recreate it."
      ;;
    1)
      arn=$(printf '%s' "$rows" | jq -r '.[0].resourceShareArn // "unknown"')
      check_pass E2 "resource share $LAB_SHARE_NAME is ACTIVE in $region ($arn), shared with the recipient account configured in LAB_RECIPIENT_ACCOUNT_ID"
      ;;
    *)
      check_fail E2 "more than one ACTIVE resource share is named $LAB_SHARE_NAME in $region (duplicate shares)"
      ;;
  esac
}

# postcheck REGION [RETENTION]: vault state, retention range, share.
postcheck() {
  local region=$1 days=${2:-} min max
  lab_region_set "$region"
  if wait_until "air-gapped vault $LAB_LAG_VAULT_NAME" 900 15 poll_vault; then
    min=$(printf '%s' "$VAULT_JSON" | jq -r '.MinRetentionDays // "unknown"')
    max=$(printf '%s' "$VAULT_JSON" | jq -r '.MaxRetentionDays // "unknown"')
    check_pass E1 "vault $LAB_LAG_VAULT_NAME is AVAILABLE in $region (minimum $min days, maximum $max days)"
    if [ -n "$days" ] && { [ "$min" != "$days" ] || [ "$max" != "$days" ]; }; then
      check_fail E1 "vault retention is $min to $max days, expected $days to $days"
    fi
    if [ "$LAB_ALLOW_EXTERNAL_PRINCIPALS" = false ]; then
      check_pass E13 "AllowExternalPrincipals=false was accepted in $region"
    fi
  else
    check_fail E1 "vault $LAB_LAG_VAULT_NAME did not become AVAILABLE in $region within 15 minutes (nothing was deleted)"
  fi
  share_check "$region"
}

cmd_suffix=""
if [ -n "$REGION_ARG" ]; then
  cmd_suffix=" --region $REGION_ARG"
fi

assert_account owner
require_sso_minutes "$LAB_OWNER_PROFILE" "$LAB_MIN_SSO_MINUTES"

if [ "$REPAIR" = 1 ]; then
  for region in $REGION_LIST; do
    inspect_region "$region"
  done
  impact_begin
  impact "effect" "the RAM share $LAB_SHARE_NAME is deleted and created again in: $REGION_LIST; the recipient loses access until the new invitation is accepted (05_accept_share.sh)"
  impact "vault" "the air-gapped vault and its recovery points are not touched"
  impact "undo" "none needed; if the share is still missing afterwards, run this again (not yet run on real environment)"
  plan_gate "./scripts/03_deploy_lag_share.sh --repair-share${cmd_suffix} --apply"
  for region in $REGION_LIST; do
    inspect_region "$region"
    days=$STACK_RETENTION
    deploy_stack "$region" false "$days"
    deploy_stack "$region" true "$days"
    check_pass E21 "the share was switched off and on in $region"
    postcheck "$region"
  done
else
  for region in $REGION_LIST; do
    inspect_region "$region"
  done
  TOKEN="lock-${RET}d-${LAB_LAG_VAULT_NAME}@${REGIONS_JOINED}"
  impact_begin
  impact "creates" "air-gapped vault $LAB_LAG_VAULT_NAME and RAM share $LAB_SHARE_NAME in: $REGION_LIST"
  impact "irreversible" "retention is $RET days (minimum = maximum), compliance mode as documented for logically air-gapped vaults; it cannot be changed after the vault is created, and a change replaces the vault"
  impact "until" "while the vault holds a recovery point it cannot be deleted; a copy is kept for $RET days from the creation of its source backup (observed once; not yet run on real environment)"
  impact "shares to" "account $LAB_RECIPIENT_ACCOUNT_ID (allow external principals: $LAB_ALLOW_EXTERNAL_PRINCIPALS)"
  impact "cost" "air-gapped vault storage price is not confirmed (see the cost section of docs/procedure.md)"
  irreversible_gate "$TOKEN" "./scripts/03_deploy_lag_share.sh --retention-days ${RET}${cmd_suffix} --apply --confirm $TOKEN"
  for region in $REGION_LIST; do
    inspect_region "$region"
    deploy_stack "$region" true "$RET"
    postcheck "$region" "$RET"
  done
fi
lab_region_set ""
if summary; then
  exit 0
fi
exit 1
