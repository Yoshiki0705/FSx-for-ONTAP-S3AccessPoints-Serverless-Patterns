#!/usr/bin/env bash
# Run `ampx sandbox` against the sandbox this checkout is already pointed at.
#
# Usage:
#   ./scripts/sandbox.sh            # watch mode
#   ./scripts/sandbox.sh --once     # deploy once and exit
#   ./scripts/sandbox.sh delete     # delete that sandbox
#
# Why this wrapper exists: `ampx sandbox` with no `--identifier` picks one named
# after the OS user. That is not necessarily the sandbox `amplify_outputs.json`
# points at, and in a VPC where another sandbox already owns the DynamoDB
# gateway endpoint the new one gets as far as creating everything else before
# failing on that route -- a route table holds one route per prefix list.
# Amplify does not roll a failed sandbox back. Measured 2026-09-03: ~25 Lambda
# functions and a Cognito user pool left in CREATE_FAILED, and ~30 minutes to
# delete because VPC Lambdas hold their ENIs.
#
# The identifier is not recorded anywhere on disk, so it is resolved from
# deployed state: the outputs file names a user pool, and CloudFormation says
# which sandbox stack owns that pool.
#
# Override with AMPLIFY_PORTAL_SANDBOX_IDENTIFIER=<name>. That is what to set
# when deliberately standing up a second sandbox -- along with
# AMPLIFY_PORTAL_DDB_GW_ENDPOINT_EXISTS=1, so it reuses the existing route
# instead of trying to own it.
#
# Before ampx starts, the effective config (environment variable, then the literal
# in portal-config.ts) is compared with the deployed sandbox. A value the sandbox
# holds that this deploy would replace with an empty one stops the run and the check
# lists the key names, never the values. portal-config.ts is gitignored per
# worktree, so a worktree holding a fresh copy of the example is enough to do this.
# Set AMPLIFY_PORTAL_ALLOW_CONFIG_BLANKING=1 (exactly 1) when emptying a value is
# intended. AMPLIFY_PORTAL_SKIP_CONFIG_CHECK does not skip this check. It runs once
# at start-up, so a redeploy under --watch is not covered. `delete` skips it.

set -euo pipefail
cd "$(dirname "$0")/.."

PREFLIGHT="../../scripts/portal_preflight.py"

# Check the config before deploying from it.
#
# Offline apart from reading the CLI's configured region, and it only fails on
# combinations that either cannot work or deploy while broken: a region that is not
# the one being deployed into, a state machine ARN still naming the example account,
# a VPC with no subnets or no route tables, an ONTAP connection configured halfway.
#
# A gate rather than a warning. The deploy it prevents is not a fast one to
# discover: a sandbox that fails partway does not roll back, and VPC Lambdas hold
# their ENIs for around 30 minutes on the way out.
if [ "${AMPLIFY_PORTAL_SKIP_CONFIG_CHECK:-}" != "1" ]; then
  if ! python3 "$PREFLIGHT" --check-config; then
    echo "✖ portal-config.ts has a problem that would deploy badly. Fix it, or set" >&2
    echo "  AMPLIFY_PORTAL_SKIP_CONFIG_CHECK=1 to deploy anyway." >&2
    exit 1
  fi
fi

IDENTIFIER="${AMPLIFY_PORTAL_SANDBOX_IDENTIFIER:-}"
SOURCE="AMPLIFY_PORTAL_SANDBOX_IDENTIFIER"

if [ -z "$IDENTIFIER" ]; then
  set +e
  IDENTIFIER=$(python3 "$PREFLIGHT" --print-sandbox-identifier 2>/dev/null)
  STATUS=$?
  set -e
  case "$STATUS" in
    0)
      SOURCE="amplify_outputs.json"
      ;;
    3)
      # Nothing deployed from this checkout, so there is no sandbox to collide
      # with and the CLI's own default is correct.
      IDENTIFIER=""
      echo "ℹ No amplify_outputs.json yet: letting ampx choose the identifier."
      ;;
    *)
      echo "✖ amplify_outputs.json exists but its sandbox could not be identified." >&2
      echo "  Continuing could create a second sandbox beside the one it names," >&2
      echo "  which fails partway and leaves resources behind." >&2
      echo "  Diagnose: python3 $PREFLIGHT --print-sandbox-identifier" >&2
      echo "  Override: AMPLIFY_PORTAL_SANDBOX_IDENTIFIER=<name> $0 $*" >&2
      exit 1
      ;;
  esac
fi

# Compare what this deploy would write with what the sandbox holds. After the
# identifier is settled, because a second sandbox is compared against nothing.
# Not for `delete`: deleting does not apply the config. Not skipped by
# AMPLIFY_PORTAL_SKIP_CONFIG_CHECK, which was set for a different purpose and is
# often set from habit; this check has its own opt-out.
if [ "${1:-}" != "delete" ]; then
  if ! python3 "$PREFLIGHT" --check-config-vs-live ${IDENTIFIER:+--identifier "$IDENTIFIER"}; then
    echo "✖ Stopped before ampx. If keys are listed above, this deploy would replace values" >&2
    echo "  the sandbox holds with empty ones. Run it from the worktree whose" >&2
    echo "  portal-config.ts has the real values, or set AMPLIFY_PORTAL_ALLOW_CONFIG_BLANKING=1" >&2
    echo "  if emptying them is intended." >&2
    exit 1
  fi
fi

if [ -n "$IDENTIFIER" ]; then
  echo "▶ npx ampx sandbox $* --identifier $IDENTIFIER  (identifier from $SOURCE)"
  exec npx ampx sandbox "$@" --identifier "$IDENTIFIER"
fi

exec npx ampx sandbox "$@"
