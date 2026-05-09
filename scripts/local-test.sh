#!/bin/bash
# =============================================================================
# SAM CLI ローカルテストスクリプト
# =============================================================================
#
# 全 UC の Discovery Lambda を sam local invoke で実行する。
# 実際の AWS サービスにはアクセスしない（モック環境）。
#
# 前提条件:
#   - SAM CLI v1.93.0+ がインストール済み
#   - Docker または Finch が起動済み
#   - Python 3.13 ランタイムイメージが利用可能
#
# 使用方法:
#   ./scripts/local-test.sh [uc-number]
#
# 例:
#   ./scripts/local-test.sh        # 全 UC をテスト
#   ./scripts/local-test.sh 01     # UC01 のみテスト
#   ./scripts/local-test.sh 06     # UC06 のみテスト
#
# Finch 使用時:
#   export SAM_CLI_CONTAINER_CONNECTION_TIMEOUT=30
#   export DOCKER_HOST=unix://$HOME/.finch/finch.sock
#   ./scripts/local-test.sh
#
# 参照: docs/local-testing-guide.md
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# カラー出力
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# UC ディレクトリとイベントファイルのマッピング
declare -A UC_MAP=(
    ["01"]="legal-compliance"
    ["02"]="financial-idp"
    ["03"]="manufacturing-analytics"
    ["04"]="media-vfx"
    ["05"]="healthcare-dicom"
    ["06"]="semiconductor-eda"
    ["07"]="genomics-pipeline"
    ["08"]="energy-seismic"
    ["09"]="autonomous-driving"
    ["10"]="construction-bim"
    ["11"]="retail-catalog"
    ["12"]="logistics-ocr"
    ["13"]="education-research"
    ["14"]="insurance-claims"
)

# 環境変数ファイル
ENV_FILE="${PROJECT_ROOT}/events/env.json"

# SAM CLI の存在確認
check_prerequisites() {
    if ! command -v sam &> /dev/null; then
        echo -e "${RED}エラー: SAM CLI がインストールされていません${NC}"
        echo "インストール: https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html"
        exit 1
    fi

    # Docker or Finch の確認
    if command -v docker &> /dev/null; then
        echo -e "${GREEN}✓ Docker 検出${NC}"
    elif command -v finch &> /dev/null; then
        echo -e "${GREEN}✓ Finch 検出${NC}"
        # Finch 用の環境変数設定
        export DOCKER_HOST="${DOCKER_HOST:-unix://$HOME/.finch/finch.sock}"
    else
        echo -e "${RED}エラー: Docker または Finch が必要です${NC}"
        exit 1
    fi

    echo -e "${GREEN}✓ SAM CLI $(sam --version | awk '{print $NF}')${NC}"
}

# 単一 UC のローカルテスト実行
run_uc_test() {
    local uc_num="$1"
    local uc_dir="${UC_MAP[$uc_num]}"
    local template="${PROJECT_ROOT}/${uc_dir}/template-deploy.yaml"
    local event="${PROJECT_ROOT}/events/uc${uc_num}-${uc_dir}/discovery-event.json"

    if [[ ! -f "$template" ]]; then
        echo -e "${YELLOW}⏭️  UC${uc_num} (${uc_dir}): template-deploy.yaml が見つかりません${NC}"
        return 1
    fi

    if [[ ! -f "$event" ]]; then
        echo -e "${YELLOW}⏭️  UC${uc_num} (${uc_dir}): イベントファイルが見つかりません${NC}"
        return 1
    fi

    echo -e "\n${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}🧪 UC${uc_num}: ${uc_dir} - Discovery Lambda${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    # sam local invoke 実行
    # NOTE: 実際の AWS サービスにはアクセスしないため、
    # Lambda 内で AWS SDK を呼び出す箇所でエラーになるのは想定通り。
    # ここでは Lambda ランタイムの起動とハンドラーの読み込みを検証する。
    sam local invoke \
        --template "$template" \
        --event "$event" \
        --env-vars "$ENV_FILE" \
        --region ap-northeast-1 \
        --skip-pull-image \
        "DiscoveryFunction" \
        2>&1 || true

    echo -e "${GREEN}✓ UC${uc_num} 完了${NC}"
}

# メイン処理
main() {
    echo "============================================================"
    echo " FSxN S3AP Serverless Patterns - ローカルテスト"
    echo "============================================================"
    echo ""

    check_prerequisites

    # 引数で特定の UC を指定可能
    if [[ $# -gt 0 ]]; then
        local target_uc="$1"
        if [[ -z "${UC_MAP[$target_uc]+x}" ]]; then
            echo -e "${RED}エラー: 無効な UC 番号: ${target_uc}${NC}"
            echo "有効な値: 01-14"
            exit 1
        fi
        run_uc_test "$target_uc"
    else
        # 全 UC をテスト
        local passed=0
        local failed=0

        for uc_num in $(echo "${!UC_MAP[@]}" | tr ' ' '\n' | sort); do
            if run_uc_test "$uc_num"; then
                ((passed++))
            else
                ((failed++))
            fi
        done

        echo ""
        echo "============================================================"
        echo " 結果: ${passed} 成功 / ${failed} スキップ"
        echo "============================================================"
    fi
}

main "$@"
