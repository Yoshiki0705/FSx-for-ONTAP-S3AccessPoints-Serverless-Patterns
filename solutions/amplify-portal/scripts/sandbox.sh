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

set -euo pipefail
cd "$(dirname "$0")/.."

PREFLIGHT="../../scripts/portal_preflight.py"

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

if [ -n "$IDENTIFIER" ]; then
  echo "▶ npx ampx sandbox $* --identifier $IDENTIFIER  (identifier from $SOURCE)"
  exec npx ampx sandbox "$@" --identifier "$IDENTIFIER"
fi

exec npx ampx sandbox "$@"
