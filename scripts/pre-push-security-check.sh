#!/usr/bin/env bash
# pre-push-security-check.sh — Verify no sensitive data is committed
# Run before every push to a public repository.
# Exit 0 = all checks PASS, Exit 1 = at least one FAIL.
set -euo pipefail

# --- Configuration ---
# Override with environment variable if your account ID differs
SECURITY_CHECK_ACCOUNT_ID="${SECURITY_CHECK_ACCOUNT_ID:-123456789012}"
REPO_ROOT="$(git rev-parse --show-toplevel)"

PASS=0
FAIL=0

check() {
  local desc="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    echo "  ✅ PASS: $desc"
    PASS=$((PASS + 1))
  else
    echo "  ❌ FAIL: $desc"
    FAIL=$((FAIL + 1))
  fi
}

check_empty() {
  local desc="$1"
  local result
  result=$("${@:2}" 2>/dev/null || true)
  if [ -z "$result" ]; then
    echo "  ✅ PASS: $desc"
    PASS=$((PASS + 1))
  else
    echo "  ❌ FAIL: $desc"
    echo "       Found: $result"
    FAIL=$((FAIL + 1))
  fi
}

echo "🔒 Pre-Push Security Check"
echo "   Repository: $REPO_ROOT"
echo "   Account ID pattern: $SECURITY_CHECK_ACCOUNT_ID"
echo ""

# --- Check 1: .kiro/ not tracked ---
echo "📋 Check 1: Sensitive directories not tracked"
check_empty ".kiro/ not in git" git ls-files .kiro/
check_empty ".env not in git" git ls-files .env .env.local '.env.*'
check_empty "*.pem not in git" git ls-files '*.pem'
check_empty ".private/ not in git" git ls-files .private/ '*/.private/'

echo ""

# --- Check 2: No real AWS account ID in tracked files ---
echo "📋 Check 2: No real AWS account ID in tracked files"
check_empty "No account ID ($SECURITY_CHECK_ACCOUNT_ID)" bash -c "git ls-files | xargs grep -rl '$SECURITY_CHECK_ACCOUNT_ID' 2>/dev/null"

echo ""

# --- Check 3: No personal file paths ---
echo "📋 Check 3: No personal file paths (/Users/*/Downloads/*.pem etc.)"
check_empty "No /Users/ paths with .pem" bash -c "git ls-files | xargs grep -rln '/Users/.*\.pem' 2>/dev/null"

# Allow /Users/ in scripts that use it as a default but check for hardcoded sensitive paths
PERSONAL_PATH_FILES=$(git ls-files | xargs grep -rln '/Users/yoshiki' 2>/dev/null || true)
if [ -n "$PERSONAL_PATH_FILES" ]; then
  echo "  ⚠️  WARN: Personal paths found in:"
  echo "$PERSONAL_PATH_FILES" | sed 's/^/       /'
  echo "       Consider using relative paths or \${PROJECT_DIR} variable"
  # This is a warning, not a failure (existing scripts may have this)
fi

echo ""

# --- Check 4: No real IP addresses (non-RFC1918 patterns) ---
echo "📋 Check 4: No real EC2 IP addresses"
check_empty "No known EC2 IPs (3.112.208.171)" bash -c "git ls-files | xargs grep -rl '3\.112\.208\.171' 2>/dev/null"
check_empty "No known EC2 IPs (13.113.190.197)" bash -c "git ls-files | xargs grep -rl '13\.113\.190\.197' 2>/dev/null"

echo ""

# --- Check 5: No ECR registry with real account ---
echo "📋 Check 5: No hardcoded ECR registry"
check_empty "No real ECR registry" bash -c "git ls-files | xargs grep -rl '${SECURITY_CHECK_ACCOUNT_ID}\.dkr\.ecr' 2>/dev/null"

echo ""

# --- Summary ---
TOTAL=$((PASS + FAIL))
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Results: $PASS/$TOTAL passed"
if [ "$FAIL" -gt 0 ]; then
  echo "  ❌ $FAIL check(s) FAILED — fix before pushing"
  exit 1
else
  echo "  ✅ All checks PASSED — safe to push"
  exit 0
fi
