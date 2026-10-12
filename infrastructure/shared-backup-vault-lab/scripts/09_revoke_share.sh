#!/bin/bash
# Real-environment run: not yet done (status source: docs/verification-record.md)
#
# 09_revoke_share.sh - the owner revokes the RAM share, and the script measures how
# long the recipient keeps seeing the shared vault (item V6).
#
# Usage:
#   09_revoke_share.sh [--region REGION] [--apply]
#
#   --region   one Region. Default: every configured Region.
#   --apply    revoke. Without it the script prints the plan and exits 10.
#
# Steps per Region: the owner deletes the ACTIVE share named LAB_SHARE_NAME; the
# script polls the recipient's shared-vault list every second for up to 120
# seconds and records the elapsed wall-clock seconds as an integer (bash SECONDS);
# it then reads the recovery points of the shared vault once and records the error
# code the recipient gets. A share that is still listed after 120 seconds is a
# failure (exit 1): the revoke call itself succeeded, so run 06_verify.sh later to
# see whether it has disappeared.
#
# A revoked share does not remove volumes the recipient already restored. The share
# is also a CloudFormation resource, so the stack and the real state now differ; to
# bring the share back use 03_deploy_lag_share.sh --repair-share (not yet run on
# real environment).
#
# Exit codes: 0 success (or nothing to revoke), 1 failure or refusal (share still
# listed after 120 seconds, state unreadable, several matching shares), 2 usage
# error, 10 plan only.
#
# Not yet run on real environment: the time until the list changes and the error
# codes. Both depend on service behaviour this script only measures.

set -euo pipefail
# shellcheck source-path=SCRIPTDIR
# shellcheck source=lib/common.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

usage() {
  cat <<'EOF'
Usage: 09_revoke_share.sh [--region R] [--apply]
The owner revokes the RAM share and the script measures how long the recipient still sees the vault. Without --apply only the plan is shown (exit 10).
EOF
}

REGION_ARG=""
while [ "$#" -gt 0 ]; do
  case $1 in
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
if [ -n "$REGION_ARG" ]; then
  validate_region_arg "$REGION_ARG"
  REGION_LIST=$REGION_ARG
else
  REGION_LIST=$(lab_regions | tr '\n' ' ' | sed 's/ $//')
fi

# poll_shared_gone: 0 when the recipient's shared list no longer holds the lab vault
# of the owner, 1 while it is listed, 2 when the list cannot be read.
POLL_STATE=""
# shellcheck disable=SC2329,SC2317  # invoked through wait_until
poll_shared_gone() {
  local vaults
  if ! vaults=$(aws_recipient backup list-backup-vaults --by-shared); then
    POLL_STATE=unreadable
    return 2
  fi
  if printf '%s' "$vaults" | jq -e --arg n "$LAB_LAG_VAULT_NAME" --arg o "$LAB_OWNER_ACCOUNT_ID" \
    '[.BackupVaultList[]? | select(.BackupVaultName == $n and ((.BackupVaultArn // "") | contains(":" + $o + ":")))] | length == 0' >/dev/null; then
    POLL_STATE=gone
    return 0
  fi
  POLL_STATE=listed
  return 1
}

assert_account owner
assert_account recipient
require_sso_minutes "$LAB_OWNER_PROFILE" "$LAB_MIN_SSO_MINUTES"

# Pass 1: find the share of every Region. Nothing is changed here.
ACTIONS=""
for region in $REGION_LIST; do
  lab_region_set "$region"
  if ! shares=$(aws_owner ram get-resource-shares --resource-owner SELF --name "$LAB_SHARE_NAME" --resource-share-status ACTIVE); then
    die "ram get-resource-shares failed in $region: the share state is unknown, nothing was changed"
  fi
  rows=$(printf '%s' "$shares" | jq -c '[.resourceShares[]?.resourceShareArn]')
  case $(printf '%s' "$rows" | jq -r 'length') in
    0) check_warn V6 "no ACTIVE share named $LAB_SHARE_NAME in $region: nothing to revoke there (already revoked?)" ;;
    1) ACTIONS="$ACTIONS $region=$(printf '%s' "$rows" | jq -r '.[0]')" ;;
    *)
      printf '%s' "$rows" | jq -r '.[] | "  \(.)"' >&2
      require_one "ACTIVE share named $LAB_SHARE_NAME in $region" "$rows" >/dev/null
      exit 1
      ;;
  esac
done
lab_region_set ""

if [ -n "$ACTIONS" ]; then
  impact_begin
  impact "effect" "the recipient account loses access to the shared air-gapped vault in: $REGION_LIST (the vault leaves its shared-vault list)"
  impact "remains" "volumes the recipient already restored stay; recovery points in the owner's vault are not touched"
  impact "undo" "03_deploy_lag_share.sh --repair-share --apply recreates the share (not yet run on real environment); the recipient accepts a new invitation with 05_accept_share.sh"
  plan_gate "./scripts/09_revoke_share.sh${REGION_ARG:+ --region $REGION_ARG} --apply"
  for entry in $ACTIONS; do
    region=${entry%%=*}
    share_arn=${entry#*=}
    lab_region_set "$region"
    if ! aws_owner ram delete-resource-share --resource-share-arn "$share_arn" >/dev/null; then
      die "ram delete-resource-share failed in $region"
    fi
    record_event revoked V6 "$share_arn"
    started=$SECONDS
    POLL_STATE=""
    wait_until "recipient list in $region" 120 1 poll_shared_gone || true
    elapsed=$((SECONDS - started))
    # What the recipient gets from the API now. The code is recorded, not judged:
    # a missing IAM allow and a revoked share can return the same code.
    if rp_out=$(aws_recipient backup list-recovery-points-by-backup-vault --backup-vault-name "$LAB_LAG_VAULT_NAME" --backup-vault-account-id "$LAB_OWNER_ACCOUNT_ID" 2>&1); then
      api_code="none (the call succeeded)"
    else
      api_code=$(printf '%s' "$rp_out" | sed -n 's/.*An error occurred (\([A-Za-z]*\)).*/\1/p' | head -n 1)
      api_code=${api_code:-unknown}
    fi
    record_event api_code V6 "region=$region code=$api_code"
    if [ "$POLL_STATE" = gone ]; then
      record_event revoke_seconds V6 "region=$region seconds=$elapsed"
      check_pass V6 "the shared vault left the recipient list in $region after $elapsed seconds (wall clock, integer); list-recovery-points then returned: $api_code"
    elif [ "$POLL_STATE" = listed ]; then
      check_fail V6 "the shared vault is still in the recipient list in $region after $elapsed seconds; the revoke call succeeded, so run 06_verify.sh later to see whether it has gone; list-recovery-points returned: $api_code"
    else
      check_fail V6 "the recipient list could not be read in $region while waiting ($elapsed seconds); list-recovery-points returned: $api_code"
    fi
  done
  lab_region_set ""
  echo "Restored volumes in the recipient account were not touched. To bring the share back: 03_deploy_lag_share.sh --repair-share --apply (not yet run on real environment)."
fi

if summary; then
  exit 0
fi
exit 1
