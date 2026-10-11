#!/bin/bash
# Real-environment run: not yet done (status source: docs/verification-record.md)
#
# Shared library for the shared-vault lab scripts. Source it; never execute it:
#
#   source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"
#
# What it provides:
#   - LAB_ROOT / LAB_REPO_ROOT, the env-file load, derived names, and load-time
#     format validation of every non-empty LAB_* variable (exit 2 on a bad value;
#     exit 78 in 01_preflight.sh and exit 2 elsewhere when a required one is empty)
#   - aws_owner / aws_recipient: the only way scripts call AWS (literal call sites)
#   - run_external: the only way scripts call anything else (sandbox.sh, npx, make)
#   - portal_env / assert_ambient_account: identity for portal child processes
#   - assert_account, require_sso_minutes, require_one, wait_until
#   - check_pass / check_fail / check_warn ITEM MESSAGE, summary
#   - record_event, plan_exit, plan_gate, irreversible_gate, an EXIT trap that
#     prints "digest=<12 hex> run=<UTC>" to stderr
#
# Exit codes used across the lab: 0 success, 1 failure or refusal, 2 usage error,
# 10 plan only (no --apply), 75 missing tool, 78 environment not ready (01 only).
#
# Compatibility: macOS /bin/bash 3.2 and Ubuntu bash 5. No mapfile, no associative
# arrays, no ${v,,}; empty arrays are expanded as ${arr[@]+"${arr[@]}"}.
#
# Counters (check_*) and gate state live in this shell. Do not call check_* inside
# $(...) or a pipeline; the counts would be lost in the subshell.

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  echo "error: common.sh is a library; source it from a lab script" >&2
  exit 2
fi

# --------------------------------------------------------------------------
# Messages and exits
# --------------------------------------------------------------------------

# die MESSAGE [EXIT_CODE]: print to stderr and exit (default 1).
die() {
  printf 'error: %s\n' "$1" >&2
  exit "${2:-1}"
}

# die_usage MESSAGE: exit 2.
die_usage() {
  die "$1" 2
}

# need_cmd NAME: exit 75 when a required tool is missing.
need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    die "required tool not found: $1" 75
  fi
}

# --------------------------------------------------------------------------
# Lab root, env file, derived names
# --------------------------------------------------------------------------

if ! LAB_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P); then
  die "cannot resolve the lab root from ${BASH_SOURCE[0]}" 2
fi
# The repository root is two levels above the lab (infrastructure/<lab>). The
# portal helpers run `make` there because the portal package has no such target.
if ! LAB_REPO_ROOT=$(cd "$LAB_ROOT/../.." && pwd -P); then
  die "cannot resolve the repository root from $LAB_ROOT" 2
fi
export LAB_ROOT LAB_REPO_ROOT

# Gate state is internal. It is initialised here, after any caller environment,
# so an exported variable in the reader's shell can never act as a confirmation.
_LAB_APPLY=0
_LAB_CONFIRM=""
_LAB_MODE=plan
_LAB_VARIANT=""
_LAB_PASSED=0
_LAB_FAILED=0
_LAB_WARNED=0
_LAB_NOW_WARNED=""
_LAB_REGION=""

# _lab_validate NAME REGEX HINT: exit 2 when NAME is non-empty and does not match.
_lab_validate() {
  local name=$1 re=$2 hint=$3 val
  val=${!name:-}
  if [ -z "$val" ]; then
    return 0
  fi
  if ! [[ $val =~ $re ]]; then
    # %q keeps control characters from reaching the terminal.
    printf 'error: %s is invalid: %q (expected %s)\n' "$name" "${val:0:80}" "$hint" >&2
    exit 2
  fi
}

# The env file wins over the shell environment. LAB_ENV_FILE is validated first
# because it decides which file is sourced.
_lab_validate LAB_ENV_FILE '^[^[:cntrl:]]+$' "a path without control characters"
_lab_env_file=${LAB_ENV_FILE:-$LAB_ROOT/lab.local.env}
if [ -f "$_lab_env_file" ]; then
  set -a
  # shellcheck source=/dev/null
  . "$_lab_env_file"
  set +a
elif [ -n "${LAB_ENV_FILE:-}" ]; then
  die "LAB_ENV_FILE does not exist: $LAB_ENV_FILE" 2
fi
unset _lab_env_file

# Defaults. Every one is exported so child processes (07 --ui starts a spec) see
# the same values; derived names are not written to any file.
: "${LAB_TAG:=shared-vault-lab}"
: "${LAB_STANDARD_VAULT_NAME:=${LAB_TAG}-standard}"
: "${LAB_LAG_VAULT_NAME:=${LAB_TAG}-lag}"
: "${LAB_SHARE_NAME:=${LAB_TAG}-lag-share}"
: "${LAB_OWNER_THROUGHPUT_MBPS:=128}"
: "${LAB_OWNER_STORAGE_GIB:=1024}"
: "${LAB_SVM_NAME:=svm_lab}"
: "${LAB_VOLUME_NAME:=vol_lab}"
: "${LAB_VOLUME_SIZE_MB:=1024}"
: "${LAB_SOURCE_BACKUP_RETENTION_DAYS:=2}"
: "${LAB_ALLOW_EXTERNAL_PRINCIPALS:=true}"
: "${LAB_RECIPIENT_THROUGHPUT_MBPS:=128}"
: "${LAB_RESTORE_SVM_NAME:=svm_restore}"
: "${LAB_RESTORE_VOLUME_NAME:=vol_restored}"
: "${LAB_RESTORE_JUNCTION_PATH:=/vol_restored}"
: "${LAB_PORTAL_DIR:=$LAB_REPO_ROOT/solutions/amplify-portal}"
: "${LAB_MIN_SSO_MINUTES:=30}"
export LAB_TAG LAB_STANDARD_VAULT_NAME LAB_LAG_VAULT_NAME LAB_SHARE_NAME \
  LAB_OWNER_THROUGHPUT_MBPS LAB_OWNER_STORAGE_GIB LAB_SVM_NAME LAB_VOLUME_NAME \
  LAB_VOLUME_SIZE_MB LAB_SOURCE_BACKUP_RETENTION_DAYS LAB_ALLOW_EXTERNAL_PRINCIPALS \
  LAB_RECIPIENT_THROUGHPUT_MBPS LAB_RESTORE_SVM_NAME LAB_RESTORE_VOLUME_NAME \
  LAB_RESTORE_JUNCTION_PATH LAB_PORTAL_DIR LAB_MIN_SSO_MINUTES

# Format validation of every non-empty LAB_* variable (empty ones are handled by
# the required-variable check below). A bad value is a usage error (2).
_lab_re_profile='^[A-Za-z0-9][A-Za-z0-9._@+=,:/-]{0,127}$'
_lab_re_account='^[0-9]{12}$'
_lab_re_region='^[a-z]{2}(-[a-z]+)+-[0-9]$'
_lab_re_vault='^[a-zA-Z0-9_-]{2,50}$'
_lab_re_digits='^[0-9]{1,6}$'
_lab_re_ctrl='^[^[:cntrl:]]+$'
_lab_validate LAB_OWNER_PROFILE "$_lab_re_profile" "an AWS CLI profile name"
_lab_validate LAB_RECIPIENT_PROFILE "$_lab_re_profile" "an AWS CLI profile name"
_lab_validate LAB_OWNER_ACCOUNT_ID "$_lab_re_account" "12 digits"
_lab_validate LAB_RECIPIENT_ACCOUNT_ID "$_lab_re_account" "12 digits"
_lab_validate LAB_PRIMARY_REGION "$_lab_re_region" "a Region such as ap-northeast-1"
_lab_validate LAB_SECOND_REGION "$_lab_re_region" "a Region such as ap-northeast-3"
_lab_validate LAB_TAG '^[a-z0-9-]{3,40}$' "3-40 characters of a-z, 0-9 and -"
_lab_validate LAB_STANDARD_VAULT_NAME "$_lab_re_vault" "2-50 characters of letters, digits, - and _"
_lab_validate LAB_LAG_VAULT_NAME "$_lab_re_vault" "2-50 characters of letters, digits, - and _"
_lab_validate LAB_SHARE_NAME '^[a-zA-Z0-9_-]{1,64}$' "1-64 characters of letters, digits, - and _"
_lab_validate LAB_OWNER_SUBNET_ID '^subnet-[0-9a-f]{8,17}$' "a subnet id"
_lab_validate LAB_OWNER_SECURITY_GROUP_ID '^sg-[0-9a-f]{8,17}$' "a security group id"
_lab_validate LAB_OWNER_THROUGHPUT_MBPS "$_lab_re_digits" "digits"
_lab_validate LAB_OWNER_STORAGE_GIB "$_lab_re_digits" "digits"
_lab_validate LAB_SVM_NAME '^[A-Za-z0-9_]{1,47}$' "1-47 characters of letters, digits and _"
_lab_validate LAB_VOLUME_NAME '^[A-Za-z0-9_]{1,203}$' "letters, digits and _"
_lab_validate LAB_VOLUME_SIZE_MB "$_lab_re_digits" "digits"
_lab_validate LAB_SOURCE_BACKUP_RETENTION_DAYS '^[1-9][0-9]{0,2}$' "a positive integer"
_lab_validate LAB_ALLOW_EXTERNAL_PRINCIPALS '^(true|false)$' "true or false"
_lab_validate LAB_RECIPIENT_EXISTING_FS_ID '^fs-[0-9a-f]{8,17}$' "a file system id"
_lab_validate LAB_RECIPIENT_SUBNET_ID '^subnet-[0-9a-f]{8,17}$' "a subnet id"
_lab_validate LAB_RECIPIENT_SECURITY_GROUP_ID '^sg-[0-9a-f]{8,17}$' "a security group id"
_lab_validate LAB_RECIPIENT_THROUGHPUT_MBPS "$_lab_re_digits" "digits"
_lab_validate LAB_SECOND_RECIPIENT_EXISTING_FS_ID '^fs-[0-9a-f]{8,17}$' "a file system id"
_lab_validate LAB_SECOND_RECIPIENT_SUBNET_ID '^subnet-[0-9a-f]{8,17}$' "a subnet id"
_lab_validate LAB_SECOND_RECIPIENT_SECURITY_GROUP_ID '^sg-[0-9a-f]{8,17}$' "a security group id"
_lab_validate LAB_RESTORE_SVM_NAME '^[A-Za-z0-9_]{1,47}$' "1-47 characters of letters, digits and _"
_lab_validate LAB_RESTORE_VOLUME_NAME '^[A-Za-z0-9_]{1,203}$' "letters, digits and _"
_lab_validate LAB_RESTORE_JUNCTION_PATH '^/[A-Za-z0-9_./-]{1,203}$' "an absolute junction path"
_lab_validate LAB_RECIPIENT_SVM_LIMIT '^[0-9]{1,3}$' "a number"
_lab_validate LAB_PORTAL_DIR "$_lab_re_ctrl" "a path without control characters"
_lab_validate LAB_PORTAL_FUNCTION_NAME '^[A-Za-z0-9_-]{1,64}$' "a Lambda function name"
_lab_validate LAB_PORTAL_RESTORE_FUNCTION_NAME '^[A-Za-z0-9_-]{1,64}$' "a Lambda function name"
_lab_validate LAB_PORTAL_SANDBOX_ID '^[A-Za-z0-9-]{1,40}$' "an Amplify sandbox identifier"
_lab_validate LAB_MIN_SSO_MINUTES '^[0-9]{1,4}$' "minutes (digits)"
_lab_validate LAB_UI_EXPECT '^(arn-missing|arn-present|revoked)$' "arn-missing, arn-present or revoked"
_lab_validate LAB_CAPTURE_DIR "$_lab_re_ctrl" "a path without control characters"
_lab_validate PORTAL_URL '^https?://[^[:space:][:cntrl:]]+$' "an http(s) URL"

if [ -n "${LAB_SECOND_REGION:-}" ] && [ "${LAB_SECOND_REGION}" = "${LAB_PRIMARY_REGION:-}" ]; then
  die "LAB_SECOND_REGION must differ from LAB_PRIMARY_REGION" 2
fi
if [ -n "${LAB_OWNER_ACCOUNT_ID:-}" ] && [ "${LAB_OWNER_ACCOUNT_ID}" = "${LAB_RECIPIENT_ACCOUNT_ID:-}" ]; then
  die "LAB_OWNER_ACCOUNT_ID and LAB_RECIPIENT_ACCOUNT_ID must be different accounts" 2
fi

# Required variables. 01_preflight.sh reports them as "environment not ready" (78);
# every other script refuses with 2 and points at 01.
_lab_missing=""
for _lab_name in LAB_OWNER_PROFILE LAB_RECIPIENT_PROFILE LAB_OWNER_ACCOUNT_ID \
  LAB_RECIPIENT_ACCOUNT_ID LAB_PRIMARY_REGION LAB_OWNER_SUBNET_ID; do
  if [ -z "${!_lab_name:-}" ]; then
    _lab_missing="$_lab_missing $_lab_name"
  fi
done
if [ -z "${LAB_RECIPIENT_EXISTING_FS_ID:-}" ] && [ -z "${LAB_RECIPIENT_SUBNET_ID:-}" ]; then
  _lab_missing="$_lab_missing LAB_RECIPIENT_SUBNET_ID"
fi
if [ -n "$_lab_missing" ]; then
  case ${0##*/} in
    01_*)
      die "required variable(s) are empty:$_lab_missing (copy lab.env.example to lab.local.env and fill it in)" 78
      ;;
    *)
      die "required variable(s) are empty:$_lab_missing (run scripts/01_preflight.sh first)" 2
      ;;
  esac
fi
unset _lab_missing _lab_name

# The run record and the digest line need these.
need_cmd jq
need_cmd python3

# --------------------------------------------------------------------------
# Clock
# --------------------------------------------------------------------------

# now: current UTC time as ISO 8601 (YYYY-MM-DDTHH:MM:SSZ). LAB_NOW pins the clock
# for tests; it is the only place that reads it. A pinned clock warns once (the
# call at load time sets the flag that later subshells inherit).
now() {
  local iso='^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?(Z|[+-][0-9]{2}:[0-9]{2})?$'
  if [ -n "${LAB_NOW:-}" ]; then
    if ! [[ $LAB_NOW =~ $iso ]]; then
      die "LAB_NOW is not an ISO 8601 timestamp" 2
    fi
    if [ -z "$_LAB_NOW_WARNED" ]; then
      _LAB_NOW_WARNED=1
      echo "warning: the clock is pinned (test use only)" >&2
    fi
    printf '%s\n' "$LAB_NOW"
  else
    date -u +%Y-%m-%dT%H:%M:%SZ
  fi
}

# The first call runs in this shell so the warning above is printed once and the
# flag is inherited by every later $(now) subshell.
now >/dev/null
_LAB_RUN=$(now)

# --------------------------------------------------------------------------
# Helpers implemented in Python
# --------------------------------------------------------------------------

# lab_py ARGS...: run lab_helpers.py with the interpreter on PATH.
lab_py() {
  python3 "$LAB_ROOT/scripts/lib/lab_helpers.py" "$@"
}

# --------------------------------------------------------------------------
# Script identity and the run record
# --------------------------------------------------------------------------

_lab_script_name=${0##*/}
case $_lab_script_name in
  [0-9][0-9]_*) _LAB_SCRIPT_ID=${_lab_script_name%%_*} ;;
  *) _LAB_SCRIPT_ID=$_lab_script_name ;;
esac
unset _lab_script_name

# lab_set_variant NAME: tag the run as a variant of the script (07-ui).
lab_set_variant() {
  _LAB_VARIANT=$1
}

# lab_apply_on: the script was started with --apply.
lab_apply_on() {
  _LAB_APPLY=1
  _LAB_MODE=apply
}

# lab_confirm_set TOKEN: the value of --confirm (never read from the environment).
lab_confirm_set() {
  _LAB_CONFIRM=$1
}

# lab_region_set REGION: Region used by aws_owner / aws_recipient (default PRIMARY).
# A call can also override it for one command: _LAB_REGION=us-east-1 aws_owner ...
lab_region_set() {
  _LAB_REGION=$1
}

# record_event EVENT ITEM DETAIL: append one JSON line to lab-run.local.jsonl.
# ITEM is a verification item id (V1, E3) or "-". The file is gitignored and may
# contain account ids; never publish it.
record_event() {
  local event=$1 item=${2:--} detail=${3:-} script=$_LAB_SCRIPT_ID file stamp
  if [ -n "$_LAB_VARIANT" ]; then
    script="$script-$_LAB_VARIANT"
  fi
  file="$LAB_ROOT/lab-run.local.jsonl"
  stamp=$(now)
  if ! jq -cn --arg ts "$stamp" --arg script "$script" \
    --arg region "${_LAB_REGION:-$LAB_PRIMARY_REGION}" --arg event "$event" \
    --arg item "$item" --arg detail "$detail" --arg mode "$_LAB_MODE" \
    --arg run "$_LAB_RUN" \
    '{ts: $ts, script: $script, region: $region, event: $event, item: $item,
      detail: $detail, mode: $mode, run: $run}' >>"$file"; then
    echo "warning: could not append to $file" >&2
  fi
}

# --------------------------------------------------------------------------
# Checks and summary
# --------------------------------------------------------------------------

# check_pass|check_fail|check_warn ITEM MESSAGE...
check_pass() {
  local item=$1
  shift
  _LAB_PASSED=$((_LAB_PASSED + 1))
  printf '  \xe2\x9c\x85 [%s] %s\n' "$item" "$*"
  record_event check_pass "$item" "$*"
}

check_fail() {
  local item=$1
  shift
  _LAB_FAILED=$((_LAB_FAILED + 1))
  printf '  \xe2\x9d\x8c [%s] %s\n' "$item" "$*"
  record_event check_fail "$item" "$*"
}

check_warn() {
  local item=$1
  shift
  _LAB_WARNED=$((_LAB_WARNED + 1))
  printf '  \xe2\x9a\xa0 [%s] %s\n' "$item" "$*"
  record_event check_warn "$item" "$*"
}

# summary: print the counts; returns 1 when anything failed.
summary() {
  printf 'Passed: %s  Failed: %s  Warnings: %s\n' "$_LAB_PASSED" "$_LAB_FAILED" "$_LAB_WARNED"
  [ "$_LAB_FAILED" -eq 0 ]
}

# lab_failed_count: number of check_fail calls so far.
lab_failed_count() {
  printf '%s\n' "$_LAB_FAILED"
}

# --------------------------------------------------------------------------
# EXIT trap: record the end of the run and print the digest line
# --------------------------------------------------------------------------

_lab_on_exit() {
  local rc=$? digest=unknown
  trap - EXIT
  if command -v python3 >/dev/null 2>&1; then
    if ! digest=$(lab_py code-digest --root "$LAB_ROOT" 2>/dev/null); then
      digest=unknown
    fi
  fi
  record_event end - "$(jq -cn --arg digest "$digest" --argjson exit "$rc" '{digest: $digest, exit: $exit}')"
  printf 'digest=%s run=%s\n' "$digest" "$_LAB_RUN" >&2
  exit "$rc"
}
trap _lab_on_exit EXIT

# --------------------------------------------------------------------------
# AWS and external commands
# --------------------------------------------------------------------------

# aws_owner SERVICE SUBCOMMAND [ARGS...] / aws_recipient ...
# Profile, Region and output format are always explicit. Write the service and
# subcommand as literals at the call site (never build them in a variable): the
# tracked guard and the stub tests read the call sites.
aws_owner() {
  AWS_PAGER="" aws --profile "$LAB_OWNER_PROFILE" \
    --region "${_LAB_REGION:-$LAB_PRIMARY_REGION}" --output json "$@"
}

aws_recipient() {
  AWS_PAGER="" aws --profile "$LAB_RECIPIENT_PROFILE" \
    --region "${_LAB_REGION:-$LAB_PRIMARY_REGION}" --output json "$@"
}

# run_external NAME [ARGS...]: run a non-AWS command (sandbox.sh, npx, npm, make,
# node). Scripts never call these directly, so tests can swap this one call.
run_external() {
  local name=$1
  shift
  case $name in
    aws | */aws) die "run_external is not for aws: use aws_owner or aws_recipient" 2 ;;
  esac
  "$name" "$@"
}

# --------------------------------------------------------------------------
# Identity checks
# --------------------------------------------------------------------------

# assert_account owner|recipient: the profile must resolve to the declared account.
assert_account() {
  local kind=$1 out acct expected
  case $kind in
    owner)
      expected=$LAB_OWNER_ACCOUNT_ID
      if ! out=$(aws_owner sts get-caller-identity); then
        die "sts get-caller-identity failed for the owner profile (sign in again?)"
      fi
      ;;
    recipient)
      expected=$LAB_RECIPIENT_ACCOUNT_ID
      if ! out=$(aws_recipient sts get-caller-identity); then
        die "sts get-caller-identity failed for the recipient profile (sign in again?)"
      fi
      ;;
    *) die_usage "assert_account: expected owner or recipient" ;;
  esac
  if ! acct=$(printf '%s' "$out" | jq -er '.Account'); then
    die "sts get-caller-identity returned no Account for the $kind profile"
  fi
  if [ "$acct" != "$expected" ]; then
    die "the $kind profile resolves to account $acct, expected $expected"
  fi
}

# portal_env: identity for portal child processes. Use it ONLY inside a subshell:
#   ( portal_env; assert_ambient_account; cd "$LAB_PORTAL_DIR" && run_external ./scripts/sandbox.sh --once )
# Static credential variables are removed so the recipient profile decides; the
# variables that point at a role or token file are left alone and
# assert_ambient_account is the last guard.
portal_env() {
  unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_SECURITY_TOKEN \
    AWS_DEFAULT_PROFILE
  export AWS_PROFILE=$LAB_RECIPIENT_PROFILE
  export AWS_REGION=$LAB_PRIMARY_REGION
  export AWS_DEFAULT_REGION=$LAB_PRIMARY_REGION
  export AMPLIFY_PORTAL_REGION=$LAB_PRIMARY_REGION
}

# assert_ambient_account: run inside the portal_env subshell, before any change.
# The call has no --profile on purpose: it reads what a child process would see.
assert_ambient_account() {
  local out acct
  if ! out=$(aws sts get-caller-identity --output json); then
    die "ambient sts get-caller-identity failed (sign in again?)"
  fi
  if ! acct=$(printf '%s' "$out" | jq -er '.Account'); then
    die "ambient sts get-caller-identity returned no Account"
  fi
  if [ "$acct" != "$LAB_RECIPIENT_ACCOUNT_ID" ]; then
    die "child processes would act in account $acct, expected the recipient account $LAB_RECIPIENT_ACCOUNT_ID"
  fi
}

# require_sso_minutes PROFILE MINUTES: stop before a long step when the SSO token
# for PROFILE has less than MINUTES left. Profiles that are not SSO profiles are
# skipped; an unreadable token cache is a warning, not a failure.
require_sso_minutes() {
  local profile=$1 minutes=$2 left
  if ! left=$(lab_py sso-minutes --profile "$profile" --now "$(now)"); then
    check_warn - "SSO token time for $profile could not be checked"
    return 0
  fi
  case $left in
    n/a)
      echo "  SSO token check skipped: $profile is not an SSO profile"
      ;;
    unknown:*)
      check_warn - "SSO token time for $profile could not be checked (${left#unknown:})"
      ;;
    *)
      if [ "$left" -lt "$minutes" ]; then
        check_fail - "SSO token for $profile has $left minutes left (need $minutes); run aws sso login"
        exit 1
      fi
      check_pass - "SSO token for $profile has $left minutes left"
      ;;
  esac
}

# --------------------------------------------------------------------------
# Reading results
# --------------------------------------------------------------------------

# require_one LABEL JSON: succeed only for exactly one usable value.
# Arrays count their non-null, non-empty elements; a scalar counts as 1 unless it
# is null or empty. Prints the single value (raw for strings, compact JSON
# otherwise). Zero, several and null all end in: die "LABEL: expected exactly one
# value (rows=N)". Call as: if ! v=$(require_one LABEL "$json"); then exit 1; fi
require_one() {
  local label=$1 json=$2 rows
  if ! rows=$(printf '%s' "$json" | jq -r '
      if type == "array" then [.[] | select(. != null and . != "")] | length
      elif . == null or . == "" then 0
      else 1 end'); then
    die "$label: not valid JSON"
  fi
  if [ "$rows" != "1" ]; then
    die "$label: expected exactly one value (rows=$rows)"
  fi
  printf '%s' "$json" | jq -r '
    (if type == "array" then [.[] | select(. != null and . != "")][0] else . end)
    | if type == "string" then . else tojson end'
}

# tags_have_lab_tag JSON: true when a {"Tags":[{"Key","Value"}]} document carries
# Project=$LAB_TAG. Use it on `fsx list-tags-for-resource` output; the describe-*
# responses of FSx do not include tags.
tags_have_lab_tag() {
  printf '%s' "$1" | jq -e --arg tag "$LAB_TAG" \
    '[.Tags[]? | select(.Key == "Project" and .Value == $tag)] | length == 1' >/dev/null
}

# json_build SPEC VALUE [SPEC VALUE ...]: compact JSON object built by jq, never by
# string concatenation. SPEC is a key, or key:json when VALUE is itself JSON.
json_build() {
  local filter="" sep="" i=0 key val spec
  local args=()
  while [ "$#" -ge 2 ]; do
    spec=$1
    val=$2
    shift 2
    key=${spec%:json}
    args+=(--arg "k$i" "$key")
    if [ "$spec" != "$key" ]; then
      args+=(--argjson "v$i" "$val")
    else
      args+=(--arg "v$i" "$val")
    fi
    filter="$filter$sep(\$k$i): \$v$i"
    sep=", "
    i=$((i + 1))
  done
  jq -cn ${args[@]+"${args[@]}"} "{$filter}"
}

# --------------------------------------------------------------------------
# Argument validation (exit 2)
# --------------------------------------------------------------------------

# validate_retention_days VALUE: integer 7-35.
validate_retention_days() {
  if ! [[ ${1:-} =~ ^[0-9]{1,2}$ ]] || [ "$1" -lt 7 ] || [ "$1" -gt 35 ]; then
    die_usage "--retention-days must be an integer from 7 to 35"
  fi
}

# validate_since VALUE: a real YYYY-MM-DD date.
validate_since() {
  if ! lab_py valid-date "${1:-}"; then
    die_usage "--since must be a real date in YYYY-MM-DD form"
  fi
}

# validate_arn LABEL VALUE [SERVICE]: arn:<partition>:<service>:<region>:<account>:<resource>.
validate_arn() {
  local label=$1 value=${2:-} service=${3:-[a-z0-9-]+} re
  re="^arn:aws[a-z-]*:${service}:[a-z0-9-]*:[0-9]*:[A-Za-z0-9/_:.+=,@*-]+\$"
  if ! [[ $value =~ $re ]]; then
    die_usage "$label is not a valid ARN${3:+ for service $3}"
  fi
}

# validate_region_arg VALUE: must be the primary or the second Region.
validate_region_arg() {
  local value=${1:-}
  if [ "$value" != "$LAB_PRIMARY_REGION" ] && { [ -z "${LAB_SECOND_REGION:-}" ] || [ "$value" != "$LAB_SECOND_REGION" ]; }; then
    die_usage "--region must be LAB_PRIMARY_REGION${LAB_SECOND_REGION:+ or LAB_SECOND_REGION}"
  fi
}

# --------------------------------------------------------------------------
# Waiting
# --------------------------------------------------------------------------

# wait_until LABEL TIMEOUT_SEC INTERVAL_SEC CMD...
# CMD exits 0 = done, 1 = not yet, 2 or more = the poll itself failed. Three poll
# failures in a row return 1 (a failure is never read as "not yet"). Elapsed time
# is the sum of the intervals slept, not the wall clock, so a stubbed sleep makes
# a 60-minute timeout run in milliseconds. The caller continues only on 0.
wait_until() {
  local label=$1 timeout=$2 interval=$3
  shift 3
  local waited=0 fails=0 rc
  while :; do
    rc=0
    "$@" || rc=$?
    case $rc in
      0) return 0 ;;
      1) fails=0 ;;
      *)
        fails=$((fails + 1))
        if [ "$fails" -ge 3 ]; then
          echo "$label: poll failed 3x" >&2
          return 1
        fi
        ;;
    esac
    if [ "$waited" -ge "$timeout" ]; then
      echo "$label: timeout after ${waited}s slept" >&2
      return 1
    fi
    sleep "$interval"
    waited=$((waited + interval))
  done
}

# --------------------------------------------------------------------------
# Plan, apply and irreversible gates
# --------------------------------------------------------------------------

# plan_exit COMMAND: print how to run for real and exit 10.
plan_exit() {
  printf 'PLAN ONLY: no AWS state was changed. To run:\n  %s\n' "$1"
  exit 10
}

# plan_gate COMMAND: without --apply, end the run as a plan (exit 10).
plan_gate() {
  if [ "$_LAB_APPLY" != "1" ]; then
    plan_exit "$1"
  fi
}

# irreversible_gate TOKEN COMMAND: call after printing the IMPACT lines and before
# the first change. Without --apply: plan (exit 10). With --apply and a --confirm
# value that is not exactly TOKEN: refuse (exit 1) and print the token. COMMAND is
# the full command line to show in the plan, including --apply --confirm TOKEN.
irreversible_gate() {
  local token=$1 command=$2
  plan_gate "$command"
  if [ "$_LAB_CONFIRM" != "$token" ]; then
    {
      echo "refused: --confirm does not match this operation."
      echo "  expected: --confirm $token"
    } >&2
    exit 1
  fi
}
