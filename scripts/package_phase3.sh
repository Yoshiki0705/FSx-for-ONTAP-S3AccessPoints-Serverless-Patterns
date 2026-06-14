#!/bin/bash
set -euo pipefail

# =============================================================================
# Phase 3 Lambda パッケージングスクリプト
# 各 Lambda 関数ごとに個別 ZIP を作成し S3 にアップロードする
#
# 知見: aws cloudformation package は template.yaml のあるディレクトリをZIP化するため、
#       親ディレクトリの shared/ モジュールは含まれない。
#       そのため各Lambda関数ごとに handler.py + shared/ を含む個別ZIPを作成する。
#       template-deploy.yaml で Code.S3Bucket/S3Key を参照してデプロイする。
# =============================================================================

REGION="${AWS_DEFAULT_REGION:-ap-northeast-1}"
ACCOUNT_ID=$(aws sts get-caller-identity --query 'Account' --output text)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# S3 バケット（Lambda コード格納用）
CODE_BUCKET="${CODE_BUCKET:-fsxn-s3ap-lambda-code-${ACCOUNT_ID}-${REGION}}"

echo "=== Phase 3 Lambda Packaging ==="
echo "Region: $REGION"
echo "Code Bucket: $CODE_BUCKET"
echo ""

# S3 バケット作成（存在しない場合）
if ! aws s3api head-bucket --bucket "$CODE_BUCKET" 2>/dev/null; then
    echo "Creating code bucket: $CODE_BUCKET"
    aws s3api create-bucket \
        --bucket "$CODE_BUCKET" \
        --region "$REGION" \
        --create-bucket-configuration LocationConstraint="$REGION"
fi

# 個別 Lambda ZIP 作成 + S3 アップロード
# 各ZIPの構造:
#   handler.py      (Lambda エントリポイント)
#   shared/         (共有モジュール)
#   *.py            (その他の関数固有ファイル)
# → Handler: handler.handler で解決される
package_lambda() {
    local uc_name=$1
    local func_name=$2
    local func_dir="$PROJECT_ROOT/${uc_name}/functions/${func_name}"

    if [ ! -d "$func_dir" ]; then
        echo "  ⚠️  Skipping ${uc_name}/${func_name} (directory not found)"
        return
    fi

    local tmp_dir=$(mktemp -d)

    # Lambda 関数コードをコピー
    cp -r "$func_dir/"* "$tmp_dir/" 2>/dev/null || true

    # shared/ モジュールをルートレベルにコピー
    cp -r "$PROJECT_ROOT/shared" "$tmp_dir/"

    # __pycache__ を除外
    find "$tmp_dir" -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

    # ZIP 作成
    (cd "$tmp_dir" && zip -qr "/tmp/${uc_name}-${func_name}.zip" .)
    rm -rf "$tmp_dir"

    # S3 にアップロード
    aws s3 cp "/tmp/${uc_name}-${func_name}.zip" \
        "s3://${CODE_BUCKET}/lambda/${uc_name}-${func_name}.zip" --quiet
    rm -f "/tmp/${uc_name}-${func_name}.zip"

    echo "  ✅ ${uc_name}/${func_name}"
}

echo "=== Packaging UC11: Retail Catalog ==="
for func in discovery image_tagging catalog_metadata quality_check stream_producer stream_consumer; do
    package_lambda "retail-catalog" "$func"
done

echo ""
echo "=== Packaging UC9: Autonomous Driving ==="
for func in discovery frame_extraction point_cloud_qc annotation_manager sagemaker_invoke sagemaker_callback; do
    package_lambda "autonomous-driving" "$func"
done

echo ""
echo "=== Packaging Complete ==="
echo "Code bucket: $CODE_BUCKET"
echo "S3 prefix: s3://${CODE_BUCKET}/lambda/"
echo ""
echo "ZIP structure (per function):"
echo "  handler.py    ← Lambda entrypoint (Handler: handler.handler)"
echo "  shared/       ← Shared module (copied from project root)"
echo ""
echo "To deploy, run:"
echo "  export CODE_BUCKET=$CODE_BUCKET"
echo "  ./scripts/deploy_phase3.sh"
