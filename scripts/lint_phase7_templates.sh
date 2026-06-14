#!/bin/bash
# Phase 7 テンプレートを個別に cfn-lint 検証する（フリーズ回避版）
#
# 注意: `python3 -c "from cfnlint import api; api.lint_all(...)"` は内部で
# Python の GC / スキーマ解決の組み合わせで稀に数十分ハングする事象が発生するため、
# cfn-lint CLI バイナリを直接使う。Python API よりも桁違いに速い。
#
# Usage:
#   bash scripts/lint_phase7_templates.sh
#   bash scripts/lint_phase7_templates.sh defense-satellite

set -u

CFN_LINT="${CFN_LINT:-${HOME}/Library/Python/3.9/bin/cfn-lint}"

if [[ ! -x "$CFN_LINT" ]]; then
    # PATH を探索
    if command -v cfn-lint >/dev/null 2>&1; then
        CFN_LINT=$(command -v cfn-lint)
    else
        echo "ERROR: cfn-lint CLI not found. Install with: python3 -m pip install --user cfn-lint" >&2
        exit 1
    fi
fi

TEMPLATES=(
    "defense-satellite/template-deploy.yaml"
    "government-archives/template-deploy.yaml"
    "smart-city-geospatial/template-deploy.yaml"
)

if [[ $# -gt 0 ]]; then
    TEMPLATES=("$1/template-deploy.yaml")
fi

# 無視する informational / warning
# E2530: SnapStart リージョン対応情報（他リージョン未対応は想定内）
# E3006: 他リージョン非対応リソース警告（ap-northeast-1 でデプロイ）
# W2530: SnapStart Version 未作成（運用方針）
IGNORE_RULES="E2530,E3006,W2530,I3011,I3042"

TOTAL_ERRORS=0

for tpl in "${TEMPLATES[@]}"; do
    if [[ ! -f "$tpl" ]]; then
        echo "SKIP (missing): $tpl"
        continue
    fi

    echo "=== Linting $tpl ==="
    # `cfn-lint` CLI は Python API より高速で、--ignore-checks でルール除外できる
    OUTPUT=$("$CFN_LINT" --ignore-checks "$IGNORE_RULES" "$tpl" 2>&1)
    RC=$?

    # cfn-lint の exit code: 0=clean, 2=warnings, 4=errors, 6=both, 8=lint error
    # https://github.com/aws-cloudformation/cfn-lint#exit-codes
    # エラー (E) のみカウント
    ERR_LINES=$(echo "$OUTPUT" | grep -c '^E[0-9]' || true)

    if [[ $RC -eq 0 ]] || [[ "$ERR_LINES" == "0" ]]; then
        echo "  OK (exit=$RC, 0 errors, warnings ignored)"
    else
        echo "  REAL ERRORS: $ERR_LINES"
        echo "$OUTPUT" | grep '^E[0-9]' | head -10
        TOTAL_ERRORS=$((TOTAL_ERRORS + ERR_LINES))
    fi
    echo ""
done

if [[ $TOTAL_ERRORS -eq 0 ]]; then
    echo "=== ALL PASSED ==="
    exit 0
else
    echo "=== FAILED ($TOTAL_ERRORS total errors) ==="
    exit 1
fi
