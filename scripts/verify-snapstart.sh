#!/bin/bash
# =============================================================================
# Lambda SnapStart 動作検証スクリプト
# =============================================================================
#
# 指定した CloudFormation スタック内の Lambda 関数について、
# SnapStart の設定状態と最適化ステータスを確認する。
#
# 使用方法:
#   ./scripts/verify-snapstart.sh <stack-name> [region]
#
# 例:
#   ./scripts/verify-snapstart.sh fsxn-eda-uc6
# =============================================================================

set -euo pipefail

STACK_NAME="${1:-}"
REGION="${2:-ap-northeast-1}"

if [[ -z "${STACK_NAME}" ]]; then
    echo "ERROR: Stack name is required" >&2
    echo "Usage: $0 <stack-name> [region]" >&2
    exit 1
fi

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== SnapStart 動作検証: ${STACK_NAME} (${REGION}) ===${NC}"
echo ""

# スタック内の Lambda 関数を取得
LAMBDA_FUNCTIONS=$(aws cloudformation list-stack-resources \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}" \
    --query "StackResourceSummaries[?ResourceType=='AWS::Lambda::Function'].PhysicalResourceId" \
    --output text 2>/dev/null) || {
    echo -e "${RED}ERROR: スタック '${STACK_NAME}' が見つかりません${NC}" >&2
    exit 1
}

if [[ -z "${LAMBDA_FUNCTIONS}" ]]; then
    echo -e "${YELLOW}Lambda 関数が見つかりません${NC}"
    exit 0
fi

printf "%-50s %-10s %-18s %-10s\n" "Function Name" "Runtime" "SnapStart Apply" "Versions"
printf "%-50s %-10s %-18s %-10s\n" "----" "----" "----" "----"

for func in ${LAMBDA_FUNCTIONS}; do
    CONFIG=$(aws lambda get-function-configuration \
        --function-name "${func}" \
        --region "${REGION}" \
        --output json 2>/dev/null) || continue

    RUNTIME=$(echo "${CONFIG}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('Runtime', 'N/A'))")
    SNAPSTART_APPLY=$(echo "${CONFIG}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('SnapStart', {}).get('ApplyOn', 'None'))")

    # バージョン数を取得
    VERSION_COUNT=$(aws lambda list-versions-by-function \
        --function-name "${func}" \
        --region "${REGION}" \
        --query 'length(Versions[?Version!=`$LATEST`])' \
        --output text 2>/dev/null) || VERSION_COUNT="0"

    printf "%-50s %-10s %-18s %-10s\n" "${func:0:48}" "${RUNTIME}" "${SNAPSTART_APPLY}" "${VERSION_COUNT}"
done

echo ""
echo -e "${BLUE}=== Published Versions の OptimizationStatus ===${NC}"

for func in ${LAMBDA_FUNCTIONS}; do
    VERSIONS=$(aws lambda list-versions-by-function \
        --function-name "${func}" \
        --region "${REGION}" \
        --query "Versions[?Version!='\$LATEST'].Version" \
        --output text 2>/dev/null) || continue

    if [[ -z "${VERSIONS}" ]]; then
        continue
    fi

    for version in ${VERSIONS}; do
        STATUS=$(aws lambda get-function-configuration \
            --function-name "${func}" \
            --qualifier "${version}" \
            --region "${REGION}" \
            --query 'SnapStart.OptimizationStatus' \
            --output text 2>/dev/null) || STATUS="Unknown"

        if [[ "${STATUS}" == "On" ]]; then
            COLOR="${GREEN}"
        elif [[ "${STATUS}" == "InProgress" ]]; then
            COLOR="${YELLOW}"
        else
            COLOR="${RED}"
        fi

        echo -e "  ${func}:${version} → ${COLOR}${STATUS}${NC}"
    done
done

echo ""
echo -e "${BLUE}=== Step Functions State Machine の呼び出し先 ===${NC}"

SFN_MACHINES=$(aws cloudformation list-stack-resources \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}" \
    --query "StackResourceSummaries[?ResourceType=='AWS::StepFunctions::StateMachine'].PhysicalResourceId" \
    --output text 2>/dev/null) || SFN_MACHINES=""

if [[ -z "${SFN_MACHINES}" ]]; then
    echo -e "${YELLOW}  Step Functions State Machine が見つかりません${NC}"
else
    for sfn in ${SFN_MACHINES}; do
        echo "  State Machine: ${sfn}"
        DEF=$(aws stepfunctions describe-state-machine \
            --state-machine-arn "${sfn}" \
            --region "${REGION}" \
            --query 'definition' \
            --output text 2>/dev/null) || continue

        # Lambda Resource (ARN) をすべて抽出
        echo "${DEF}" | python3 -c "
import sys, json, re
try:
    d = json.loads(sys.stdin.read())
    arns = set()
    def walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == 'Resource' and isinstance(v, str) and v.startswith('arn:aws:lambda'):
                    arns.add(v)
                walk(v)
        elif isinstance(obj, list):
            for i in obj:
                walk(i)
    walk(d)
    for a in sorted(arns):
        # Check if ARN has qualifier (version or alias)
        parts = a.split(':')
        if len(parts) > 7:
            qualifier = parts[7]
            marker = '✅ SnapStart対象' if qualifier != '' else '⚠️  \$LATEST'
        else:
            marker = '⚠️  \$LATEST (SnapStart非対象)'
        print(f'    {marker}: {a}')
except Exception as e:
    print(f'    (パース失敗: {e})')
"
    done
fi

echo ""
echo -e "${BLUE}=== 検証完了 ===${NC}"
echo ""
echo -e "${YELLOW}ヒント:${NC}"
echo -e "  - Step Functions Resource ARN が ':\$LATEST' または qualifier なしの場合、"
echo -e "    SnapStart は実質的に無効です（\$LATEST には SnapStart は適用されません）。"
echo -e "  - 実運用で SnapStart を活用するには、Alias ARN または Version ARN を呼び出してください。"
