#!/bin/bash
# Real-environment run: recorded [V1][V2][V3][V4][V5][V6][V7]; not recorded [E13] (status source: docs/verification-record.md)
#
# 05_accept_share.sh - the recipient accepts the resource share invitation.
#
# Usage:
#   05_accept_share.sh [--region REGION] [--share-arn ARN] [--apply]
#
#   --region      one Region. Default: every configured Region.
#   --share-arn   the resource share to accept. Default: read from the owner
#                 stack output ResourceShareArn with the owner profile. Use this
#                 when you do not have the owner's credentials.
#   --apply       accept. Without it the script prints the plan and exits 10.
#
# Idempotent: when the invitation was already accepted the script only checks that
# the shared vault is visible and exits 0. An invitation is valid for 12 hours;
# one that is 11 hours old or older produces a warning with the way to get a new
# one (03_deploy_lag_share.sh --repair-share --apply, not yet run on real
# environment).
#
# Exit codes: 0 success, 1 failure or refusal (no invitation and no visible
# vault, several matching invitations, vault not visible after accepting),
# 2 usage error, 10 plan only.
#
# Not yet run on real environment: the invitation fields, the 11-second
# visibility observed once, and the case where organization sharing makes the
# invitation unnecessary.

set -euo pipefail
# shellcheck source-path=SCRIPTDIR
# shellcheck source=lib/common.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

usage() {
  cat <<'EOF'
Usage: 05_accept_share.sh [--region R] [--share-arn ARN] [--apply]
The recipient accepts the resource share invitation. Without --apply only the plan is shown (exit 10).
EOF
}

REGION_ARG=""
SHARE_ARN_ARG=""
while [ "$#" -gt 0 ]; do
  case $1 in
    --region)
      if [ "$#" -lt 2 ]; then
        die_usage "--region needs a value"
      fi
      REGION_ARG=$2
      shift 2
      ;;
    --share-arn)
      if [ "$#" -lt 2 ]; then
        die_usage "--share-arn needs an ARN"
      fi
      SHARE_ARN_ARG=$2
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
if [ -n "$SHARE_ARN_ARG" ]; then
  validate_arn "--share-arn" "$SHARE_ARN_ARG" ram
fi
if [ -n "$REGION_ARG" ]; then
  validate_region_arg "$REGION_ARG"
  REGION_LIST=$REGION_ARG
else
  REGION_LIST=$(lab_regions | tr '\n' ' ' | sed 's/ $//')
fi

# shared_vault_visible: 0 when the recipient's shared list holds the lab vault of the owner.
VISIBLE_ARN=""
shared_vault_visible() {
  local vaults
  vaults=$(aws_recipient backup list-backup-vaults --by-shared) || return 2
  VISIBLE_ARN=$(printf '%s' "$vaults" | jq -r --arg n "$LAB_LAG_VAULT_NAME" --arg o "$LAB_OWNER_ACCOUNT_ID" \
    '[.BackupVaultList[]? | select(.BackupVaultName == $n and ((.BackupVaultArn // "") | contains(":" + $o + ":")))][0].BackupVaultArn // empty')
  [ -n "$VISIBLE_ARN" ]
}

# share_arn_for REGION: the share to accept in a Region.
share_arn_for() {
  local json value
  if [ -n "$SHARE_ARN_ARG" ]; then
    printf '%s' "$SHARE_ARN_ARG"
    return 0
  fi
  if ! json=$(aws_owner cloudformation describe-stacks --stack-name "${LAB_TAG}-lag-$1"); then
    die "stack ${LAB_TAG}-lag-$1 could not be read in $1 with the owner profile; pass --share-arn"
  fi
  if ! value=$(stack_value_one "share ARN of ${LAB_TAG}-lag-$1" "$json" Outputs ResourceShareArn); then exit 1; fi
  if [ "$value" = not-shared ]; then
    die "the stack ${LAB_TAG}-lag-$1 has no share (ShareEnabled is false); run 03_deploy_lag_share.sh --repair-share --apply"
  fi
  printf '%s' "$value"
}

assert_account recipient
require_sso_minutes "$LAB_RECIPIENT_PROFILE" "$LAB_MIN_SSO_MINUTES"

# Pass 1: read each Region and decide. Nothing is changed here.
ACTIONS=""
for region in $REGION_LIST; do
  lab_region_set "$region"
  if [ -n "$SHARE_ARN_ARG" ]; then
    share_arn=$SHARE_ARN_ARG
  else
    share_arn=$(share_arn_for "$region")
  fi
  if ! invitations=$(aws_recipient ram get-resource-share-invitations); then
    die "ram get-resource-share-invitations failed in $region"
  fi
  rows=$(printf '%s' "$invitations" | jq -c --arg s "$share_arn" --arg o "$LAB_OWNER_ACCOUNT_ID" \
    '[.resourceShareInvitations[]? | select(.resourceShareArn == $s and .senderAccountId == $o)]')
  pending=$(printf '%s' "$rows" | jq -c '[.[] | select(.status == "PENDING")]')
  accepted=$(printf '%s' "$rows" | jq -r '[.[] | select(.status == "ACCEPTED")] | length')
  case $(printf '%s' "$pending" | jq -r 'length') in
    0)
      if [ "$accepted" != 0 ]; then
        if shared_vault_visible; then
          check_pass E2 "the invitation in $region was already accepted and the vault is visible ($VISIBLE_ARN)"
        else
          check_fail E2 "the invitation in $region was accepted but the vault $LAB_LAG_VAULT_NAME is not in the shared list"
        fi
      elif shared_vault_visible; then
        check_pass E13 "no invitation in $region, and the vault is visible ($VISIBLE_ARN): access did not need an invitation (organization sharing?)"
      else
        check_fail E2 "no invitation for $share_arn from account $LAB_OWNER_ACCOUNT_ID in $region, and the vault is not visible; check that 03_deploy_lag_share.sh finished, or recreate the share with --repair-share"
      fi
      ;;
    1)
      invitation_arn=$(printf '%s' "$pending" | jq -r '.[0].resourceShareInvitationArn')
      stamp=$(printf '%s' "$pending" | jq -r '.[0].invitationTimestamp // empty')
      if [ -n "$stamp" ]; then
        age=$(lab_py age-minutes --from "$stamp" --now "$(now)")
        if [ "$age" -ge 660 ]; then
          check_warn E21 "the invitation in $region is $((age / 60)) hours old and expires after 12 hours; if accepting fails, run 03_deploy_lag_share.sh --repair-share --apply for a new one (a new invitation is not yet run on real environment)"
        fi
        expires=$(lab_py add-days --from "$stamp" --days 0)
      else
        expires="unknown"
      fi
      ACTIONS="$ACTIONS $region=$invitation_arn"
      EXPIRES_NOTE="created $expires, valid for 12 hours"
      ;;
    *)
      printf '%s' "$pending" | jq -r '.[] | "  \(.resourceShareInvitationArn)"' >&2
      require_one "pending invitation in $region" "$(printf '%s' "$pending" | jq -c '[.[].resourceShareInvitationArn]')" >/dev/null
      exit 1
      ;;
  esac
done
lab_region_set ""

if [ -n "$ACTIONS" ]; then
  impact_begin
  impact "effect" "the recipient account sees the shared air-gapped vault in: $REGION_LIST (the shared vault appears in its --by-shared list)"
  impact "reversible by" "09_revoke_share.sh (the owner deletes the share)"
  impact "invitation expires" "${EXPIRES_NOTE:-12 hours after it was created}"
  plan_gate "./scripts/05_accept_share.sh${REGION_ARG:+ --region $REGION_ARG}${SHARE_ARN_ARG:+ --share-arn $SHARE_ARN_ARG} --apply"
  for entry in $ACTIONS; do
    region=${entry%%=*}
    invitation_arn=${entry#*=}
    lab_region_set "$region"
    if ! aws_recipient ram accept-resource-share-invitation --resource-share-invitation-arn "$invitation_arn" >/dev/null; then
      die "accepting the invitation failed in $region"
    fi
    record_event accepted E2 "$invitation_arn"
    if wait_until "shared vault in $region" 60 5 shared_vault_visible; then
      check_pass E2 "the invitation in $region was accepted and the vault is visible ($VISIBLE_ARN)"
    else
      check_fail E2 "the invitation in $region was accepted but the vault $LAB_LAG_VAULT_NAME did not appear in the shared list within 60 seconds"
    fi
  done
  lab_region_set ""
fi

if summary; then
  exit 0
fi
exit 1
