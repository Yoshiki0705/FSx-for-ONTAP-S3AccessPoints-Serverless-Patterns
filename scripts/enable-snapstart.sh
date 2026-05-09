#!/bin/bash
# =============================================================================
# Lambda SnapStart 有効化スクリプト
# =============================================================================
#
# 指定した CloudFormation スタックで SnapStart を有効化し、
# 各 Lambda 関数の新バージョンを公開して、SnapStart の最適化が
# 完了（OptimizationStatus: On）するのを待つ。
#
# 使用方法:
#   ./scripts/enable-snapstart.sh <stack-name> [region]
#
# 例:
#   ./scripts/enable-snapstart.sh fsxn-eda-uc6
#   ./scripts/enable-snapstart.sh fsxn-legal-compliance ap-northeast-1
#
# 前提条件:
#   - AWS CLI v2 設定済み
#   - 対象スタックが既にデプロイ済み
#   - jq コマンド利用可能
#
# =============================================================================

set -euo pipefail

STACK_NAME="${1:-}"
REGION="${2:-ap-northeast-1}"

if [[ -z "${STACK_NAME}" ]]; then
    echo "ERROR: Stack name is required" >&2
    echo "Usage: $0 <stack-name> [region]" >&2
    exit 1
fi

# カラー出力
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}===========================================${NC}"
echo -e "${BLUE} Lambda SnapStart 有効化スクリプト${NC}"
echo -e "${BLUE}===========================================${NC}"
echo "Stack: ${STACK_NAME}"
echo "Region: ${REGION}"
echo ""

# -----------------------------------------------------------------------------
# Step 1: 現在のスタックパラメータを取得
# -----------------------------------------------------------------------------
echo -e "${BLUE}[1/5] 現在のスタックパラメータを取得中...${NC}"

# スタックが存在するか確認
if ! aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}" \
    --query 'Stacks[0].StackStatus' \
    --output text > /dev/null 2>&1; then
    echo -e "${RED}ERROR: Stack '${STACK_NAME}' not found in region '${REGION}'${NC}" >&2
    exit 1
fi

# EnableSnapStart パラメータの存在確認
HAS_SNAPSTART_PARAM=$(aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}" \
    --query "Stacks[0].Parameters[?ParameterKey=='EnableSnapStart'] | length(@)" \
    --output text)

if [[ "${HAS_SNAPSTART_PARAM}" == "0" ]]; then
    echo -e "${RED}ERROR: Stack '${STACK_NAME}' does not support EnableSnapStart parameter.${NC}" >&2
    echo -e "${RED}       Please redeploy with a template that includes EnableSnapStart.${NC}" >&2
    exit 1
fi

# -----------------------------------------------------------------------------
# Step 2: スタック更新（EnableSnapStart=true）
# -----------------------------------------------------------------------------
echo -e "${BLUE}[2/5] スタック更新中 (EnableSnapStart=true)...${NC}"

# 全パラメータ名を取得
PARAM_KEYS=$(aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}" \
    --query 'Stacks[0].Parameters[].ParameterKey' \
    --output text)

# UsePreviousValue=true のパラメータリスト構築（EnableSnapStart のみ変更）
PARAMS_ARGS=()
for key in ${PARAM_KEYS}; do
    if [[ "${key}" == "EnableSnapStart" ]]; then
        PARAMS_ARGS+=("ParameterKey=${key},ParameterValue=true")
    else
        PARAMS_ARGS+=("ParameterKey=${key},UsePreviousValue=true")
    fi
done

# スタック更新実行
UPDATE_OUTPUT=$(aws cloudformation update-stack \
    --stack-name "${STACK_NAME}" \
    --use-previous-template \
    --parameters "${PARAMS_ARGS[@]}" \
    --capabilities CAPABILITY_NAMED_IAM \
    --region "${REGION}" 2>&1) || {
    if echo "${UPDATE_OUTPUT}" | grep -q "No updates are to be performed"; then
        echo -e "${YELLOW}  既に EnableSnapStart=true です。スキップします。${NC}"
    else
        echo -e "${RED}ERROR: Stack update failed:${NC}" >&2
        echo "${UPDATE_OUTPUT}" >&2
        exit 1
    fi
}

# スタック更新完了待ち
if echo "${UPDATE_OUTPUT}" | grep -q "StackId"; then
    echo "  スタック更新完了を待機中..."
    aws cloudformation wait stack-update-complete \
        --stack-name "${STACK_NAME}" \
        --region "${REGION}"
    echo -e "${GREEN}  スタック更新完了${NC}"
fi

# -----------------------------------------------------------------------------
# Step 3: スタック内の Lambda 関数を列挙
# -----------------------------------------------------------------------------
echo -e "${BLUE}[3/5] スタック内の Lambda 関数を列挙中...${NC}"

LAMBDA_FUNCTIONS=$(aws cloudformation list-stack-resources \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}" \
    --query "StackResourceSummaries[?ResourceType=='AWS::Lambda::Function'].PhysicalResourceId" \
    --output text)

if [[ -z "${LAMBDA_FUNCTIONS}" ]]; then
    echo -e "${YELLOW}  Lambda 関数が見つかりません。終了します。${NC}"
    exit 0
fi

FUNCTION_COUNT=$(echo "${LAMBDA_FUNCTIONS}" | wc -w | tr -d ' ')
echo -e "${GREEN}  ${FUNCTION_COUNT} 個の Lambda 関数を検出${NC}"

# -----------------------------------------------------------------------------
# Step 4: 各 Lambda 関数の新バージョンを公開
# -----------------------------------------------------------------------------
echo -e "${BLUE}[4/5] Lambda 関数のバージョンを公開中...${NC}"

declare -a PUBLISHED_VERSIONS=()

for func in ${LAMBDA_FUNCTIONS}; do
    echo -n "  ${func}: "
    VERSION=$(aws lambda publish-version \
        --function-name "${func}" \
        --region "${REGION}" \
        --query 'Version' \
        --output text 2>/dev/null) || {
        echo -e "${YELLOW}失敗（スキップ）${NC}"
        continue
    }
    echo -e "${GREEN}Version ${VERSION} 公開${NC}"
    PUBLISHED_VERSIONS+=("${func}:${VERSION}")
done

# -----------------------------------------------------------------------------
# Step 5: SnapStart 最適化ステータスを確認
# -----------------------------------------------------------------------------
echo -e "${BLUE}[5/5] SnapStart 最適化ステータスを確認中...${NC}"
echo "  （SnapStart 最適化は数分かかる場合があります）"

SUCCESS_COUNT=0
FAILED_COUNT=0

for entry in "${PUBLISHED_VERSIONS[@]}"; do
    func="${entry%:*}"
    version="${entry#*:}"

    STATUS=$(aws lambda get-function-configuration \
        --function-name "${func}" \
        --qualifier "${version}" \
        --region "${REGION}" \
        --query 'SnapStart.OptimizationStatus' \
        --output text 2>/dev/null) || STATUS="Unknown"

    if [[ "${STATUS}" == "On" ]]; then
        echo -e "  ${func}:${version} → ${GREEN}${STATUS}${NC}"
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
    elif [[ "${STATUS}" == "InProgress" ]]; then
        echo -e "  ${func}:${version} → ${YELLOW}${STATUS} (処理中)${NC}"
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
    else
        echo -e "  ${func}:${version} → ${YELLOW}${STATUS}${NC}"
        FAILED_COUNT=$((FAILED_COUNT + 1))
    fi
done

# -----------------------------------------------------------------------------
# サマリー
# -----------------------------------------------------------------------------
echo ""
echo -e "${BLUE}===========================================${NC}"
echo -e "${BLUE} 結果${NC}"
echo -e "${BLUE}===========================================${NC}"
echo -e "  成功: ${GREEN}${SUCCESS_COUNT}${NC}"
echo -e "  失敗: ${YELLOW}${FAILED_COUNT}${NC}"
echo ""
echo -e "${YELLOW}⚠️  重要: Step Functions や他のサービスから SnapStart 有効${NC}"
echo -e "${YELLOW}    バージョンを呼び出すには、Lambda ARN の末尾に${NC}"
echo -e "${YELLOW}    バージョン番号または Alias 名を付ける必要があります。${NC}"
echo -e "${YELLOW}    詳細: docs/snapstart-guide.md${NC}"
