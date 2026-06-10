#!/bin/bash
# =============================================================================
# SnapMirror One-Click Sync — AWS インフラデプロイスクリプト
# =============================================================================
set -euo pipefail

STACK_NAME="${STACK_NAME:-snapmirror-demo}"
REGION="${AWS_REGION:-ap-northeast-1}"
FSX_ADMIN_PASSWORD="${FSX_ADMIN_PASSWORD:-}"
DRY_RUN=false

# --- 引数パース ---
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --stack-name)
            STACK_NAME="$2"
            shift 2
            ;;
        --region)
            REGION="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --dry-run       検証のみ（デプロイしない）"
            echo "  --stack-name    スタック名 (default: snapmirror-demo)"
            echo "  --region        リージョン (default: ap-northeast-1)"
            echo "  -h, --help      ヘルプ表示"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo "============================================"
echo "  SnapMirror Demo — AWS Infrastructure Deploy"
echo "============================================"
echo ""
echo "  Stack Name: ${STACK_NAME}"
echo "  Region:     ${REGION}"
echo "  Dry Run:    ${DRY_RUN}"
echo ""

# --- 前提チェック ---
echo "📋 前提条件チェック..."

if ! command -v aws &> /dev/null; then
    echo "  ❌ AWS CLI がインストールされていません"
    exit 1
fi
echo "  ✅ AWS CLI"

# AWS 認証確認
if ! aws sts get-caller-identity --region "${REGION}" > /dev/null 2>&1; then
    echo "  ❌ AWS 認証が設定されていません（aws configure を実行）"
    exit 1
fi
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "  ✅ AWS 認証 (Account: ${ACCOUNT_ID})"

# テンプレートファイル確認
TEMPLATE_FILE="$(dirname "$0")/template.yaml"
if [ ! -f "${TEMPLATE_FILE}" ]; then
    echo "  ❌ テンプレートファイルが見つかりません: ${TEMPLATE_FILE}"
    exit 1
fi
echo "  ✅ テンプレートファイル"

# パスワードチェック
if [ -z "${FSX_ADMIN_PASSWORD}" ]; then
    echo ""
    echo "  ⚠️  FSX_ADMIN_PASSWORD 環境変数を設定してください"
    echo "     export FSX_ADMIN_PASSWORD='YourSecurePassword123!'"
    if [ "${DRY_RUN}" = false ]; then
        exit 1
    fi
    echo "     (dry-run のため続行)"
fi
echo ""

# --- テンプレート検証 ---
echo "🔍 テンプレート検証中..."
aws cloudformation validate-template \
    --template-body "file://${TEMPLATE_FILE}" \
    --region "${REGION}" \
    > /dev/null 2>&1
echo "  ✅ テンプレート構文 OK"
echo ""

# --- Dry Run ここまで ---
if [ "${DRY_RUN}" = true ]; then
    echo "============================================"
    echo "  ✅ Dry Run 完了 — 問題なし"
    echo "============================================"
    echo ""
    echo "  実際にデプロイするには --dry-run を外して実行:"
    echo "  export FSX_ADMIN_PASSWORD='YourPassword'"
    echo "  $0"
    echo ""
    echo "  デプロイ所要時間: 約 20-30 分（FSx 作成）"
    exit 0
fi

# --- SSM パラメータ作成 ---
echo "📝 SSM パラメータを作成中..."
aws ssm put-parameter \
    --name "/snapmirror-demo/fsx-admin-password" \
    --type "SecureString" \
    --value "${FSX_ADMIN_PASSWORD}" \
    --overwrite \
    --region "${REGION}" \
    > /dev/null 2>&1
echo "  ✅ SSM パラメータ作成完了"
echo ""

# --- CloudFormation デプロイ ---
echo "🚀 CloudFormation スタックをデプロイ中..."
echo "   ※ FSx for ONTAP の作成には 20-30 分かかります"
echo ""

aws cloudformation deploy \
    --template-file "${TEMPLATE_FILE}" \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}" \
    --parameter-overrides \
        FsxStorageCapacity="${FSX_STORAGE_CAPACITY:-1024}" \
        FsxThroughputCapacity="${FSX_THROUGHPUT_CAPACITY:-128}" \
        EnableVpn="${ENABLE_VPN:-false}" \
        OnPremPublicIp="${ONPREM_PUBLIC_IP:-0.0.0.0}" \
        OnPremCidr="${ONPREM_CIDR:-192.168.0.0/16}" \
    --capabilities CAPABILITY_IAM \
    --no-fail-on-empty-changeset

echo ""
echo "✅ デプロイ完了"
echo ""

# --- 出力表示 ---
echo "📋 スタック出力:"
echo "--------------------------------------------"
aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}" \
    --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue]' \
    --output table

echo ""
echo "🔜 次の手順:"
echo "  1. VPN / Direct Connect でオンプレミスと接続"
echo "  2. オンプレミス ONTAP で cluster peer / vserver peer を設定"
echo "  3. SnapMirror 関係を作成: ./scripts/setup-snapmirror.sh"
echo "  4. S3 Access Point を構成: ./scripts/setup-s3-access-point.sh"
echo "  5. Amazon Quick で S3 データソースを接続"
echo "  6. Sync Server を起動して E2E テスト: ./scripts/e2e-test.sh"
