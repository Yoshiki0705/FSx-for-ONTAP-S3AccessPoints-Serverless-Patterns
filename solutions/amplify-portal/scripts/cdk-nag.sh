#!/usr/bin/env bash
#
# Run cdk-nag against the portal backend without deploying anything.
#
# Why this script exists
# ----------------------
# The command the docs used to give was `CDK_NAG=1 npx ampx generate outputs`. That reads
# the outputs of an already-deployed stack; it never synthesises the backend, so cdk-nag
# never runs and the command reports nothing. Following it and seeing no findings said
# nothing about whether there were any.
#
# `ampx` has no synth-only command, and the AWS CDK CLI is not a dependency here. What is
# left is to execute `amplify/backend.ts` as the CDK app it is: CDK synthesises on exit
# when `CDK_OUTDIR` is set, and Amplify's backend reads its identity from three CDK
# context keys, which `CDK_CONTEXT_JSON` supplies.
#
# Nothing is deployed and no AWS credentials are used. The values below only have to be
# well-formed -- they name the stack in the report, and the identifiers in an unrelated
# sandbox are the reason for the default.
#
# Reading the result
# ------------------
# A non-zero exit is expected today. Amplify-managed resources produce findings that are
# not user-configurable, so cdk-nag is not a gate; see docs/iac-governance-patterns.md.
# What matters is the count and where it moved, which is why the summary groups by stack.
#
# Two properties of the acknowledgment API, both measured, both worth knowing before
# reading the numbers:
#
#   A coarse id suppresses nothing. cdk-nag reports each finding under a granular name
#   like `AwsSolutions-IAM5[Resource::<arn>]`, and `AwsSolutions-IAM5` matches none of
#   them.
#
#   `Validations.acknowledge` rejects an id containing more than one `::`. A granular id
#   carries one; an ARN of the form `arn:aws:s3:::bucket/*` contributes another, and
#   those findings cannot be acknowledged through this API at all.
#
set -euo pipefail

cd "$(dirname "$0")/.."

OUTDIR=${CDK_NAG_OUTDIR:-.cdk-nag-out}
BACKEND_NAME=${CDK_NAG_BACKEND_NAME:-nagcheck}
BACKEND_NAMESPACE=${CDK_NAG_BACKEND_NAMESPACE:-fsxns3apamplifyportal}

# Synthesise against the committed example configuration, not the one on this machine.
#
# Several finding ids embed a value from `portal-config.ts` -- an IAM5 finding names the
# resource ARN it objects to -- and that file is gitignored, so a developer's copy differs
# from the example CI copies into place. A baseline recorded from a local config named a
# DemoMode bucket that CI has never heard of, and the gate failed on its first run with 13
# findings "no longer reported". The baseline has to be defined against the file everybody
# shares.
#
# `CDK_NAG_KEEP_CONFIG=1` synthesises against whatever is in place instead. Useful for
# looking at your own deployment; the baseline will not match, and that is expected.
CONFIG=amplify/portal-config.ts
EXAMPLE=amplify/portal-config.example.ts
STASHED=""
restore_config() {
  if [ -n "$STASHED" ] && [ -f "$STASHED" ]; then
    mv -f "$STASHED" "$CONFIG"
  fi
}
# On any exit, including an interrupt: losing somebody's configuration to a check that
# only reads things would be a poor trade.
trap restore_config EXIT INT TERM

if [ "${CDK_NAG_KEEP_CONFIG:-0}" != "1" ]; then
  if [ -f "$CONFIG" ]; then
    STASHED="$(mktemp "${TMPDIR:-/tmp}/portal-config.XXXXXX.ts")"
    cp "$CONFIG" "$STASHED"
  fi
  cp "$EXAMPLE" "$CONFIG"
  echo "Synthesising against $EXAMPLE (set CDK_NAG_KEEP_CONFIG=1 to use your own)."
fi

rm -rf "$OUTDIR"
mkdir -p "$OUTDIR"

echo "Synthesising with cdk-nag (nothing is deployed)..."
set +e
CDK_NAG=1 \
CDK_OUTDIR="$OUTDIR" \
CDK_CONTEXT_JSON="{\"amplify-backend-name\":\"$BACKEND_NAME\",\"amplify-backend-namespace\":\"$BACKEND_NAMESPACE\",\"amplify-backend-type\":\"sandbox\"}" \
  npx tsx amplify/backend.ts > "$OUTDIR/synth.log" 2>&1
SYNTH_EXIT=$?
set -e

REPORT="$OUTDIR/validation-report.json"
if [ ! -f "$REPORT" ]; then
  echo "No validation report at $REPORT — synth failed before validation ran:"
  tail -30 "$OUTDIR/synth.log"
  exit 1
fi

python3 - "$REPORT" <<'PY'
import collections, json, sys

report = json.load(open(sys.argv[1]))
for plugin in report.get("pluginReports", []):
    findings = [
        (violation["ruleName"], construct["constructPath"])
        for violation in plugin.get("violations", [])
        for construct in violation.get("violatingConstructs", [])
    ]
    print(f"\n{plugin.get('pluginName')}: {plugin.get('conclusion')}, {len(findings)} finding(s)")

    by_stack = collections.Counter(path.split("/")[1] for _, path in findings)
    for stack, count in by_stack.most_common():
        print(f"  {stack} stack: {count}")

    by_rule = collections.Counter(rule.split("[")[0] for rule, _ in findings)
    print("  by rule: " + ", ".join(f"{rule}={count}" for rule, count in by_rule.most_common()))

    # The roles the portal grants directly, as opposed to what Amplify creates for itself.
    # These are the ones a change to `direct-s3-access.ts` moves, so they are listed rather
    # than counted.
    ours = [
        (rule, path)
        for rule, path in findings
        if "GroupRole" in path or "authenticatedUserRole" in path
    ]
    print(f"  on the portal's own auth roles: {len(ours)}")
    for rule, path in ours:
        print(f"    {rule}\n      {path.split('/', 1)[1]}")
PY

echo
echo "Full report: $REPORT"
echo "Synth log:   $OUTDIR/synth.log"
echo "Synth exited $SYNTH_EXIT (non-zero is expected: Amplify-managed findings remain)."
