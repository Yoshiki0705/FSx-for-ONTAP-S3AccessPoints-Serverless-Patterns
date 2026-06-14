#!/bin/bash
set -euo pipefail
# =============================================================================
# Phase 10: FPolicy Lambda パッケージングスクリプト
#
# Usage:
#   ./scripts/package_fpolicy_lambdas.sh [DEPLOY_BUCKET]
#
# 注意事項:
#   - jsonschema は 4.17.x を使用（4.18+ は rpds-py が必要で ARM64 Lambda 非互換）
#   - ARM64 Lambda 用にプラットフォーム指定でインストール
#   - スキーマファイルは handler.py と同一ディレクトリに配置
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_DIR="/tmp/fpolicy-lambda-build"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "UNKNOWN")
DEPLOY_BUCKET="${1:-fsxn-eda-deploy-${ACCOUNT_ID}}"
REGION="${AWS_DEFAULT_REGION:-ap-northeast-1}"

echo "=== Phase 10: FPolicy Lambda Packaging ==="
echo "Project root: $PROJECT_ROOT"
echo "Deploy bucket: $DEPLOY_BUCKET"
echo ""

# Clean build directory
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

# --- Package 1: fpolicy_engine ---
echo "[1/3] Packaging fpolicy_engine..."
DEST="$BUILD_DIR/fpolicy_engine"
mkdir -p "$DEST"

# Install jsonschema (ARM64 compatible version)
pip3 install 'jsonschema>=4.17.0,<4.18.0' \
  -t "$DEST" \
  --quiet \
  --platform manylinux2014_aarch64 \
  --only-binary=:all: \
  --python-version 3.12 2>/dev/null || \
pip3 install 'jsonschema>=4.17.0,<4.18.0' -t "$DEST" --quiet

# Copy handler and schema
cp "$PROJECT_ROOT/shared/lambdas/fpolicy_engine/handler.py" "$DEST/"
cp "$PROJECT_ROOT/shared/schemas/fpolicy-event-schema.json" "$DEST/"

# Create zip
cd "$DEST"
zip -r "$BUILD_DIR/fpolicy_engine.zip" . -x '*.pyc' '__pycache__/*' '*.dist-info/*' > /dev/null
echo "  → fpolicy_engine.zip ($(du -h "$BUILD_DIR/fpolicy_engine.zip" | cut -f1))"

# --- Package 2: sqs_to_eventbridge ---
echo "[2/3] Packaging sqs_to_eventbridge..."
DEST="$BUILD_DIR/sqs_to_eventbridge"
mkdir -p "$DEST"

# No external dependencies (boto3 is in Lambda runtime)
cp "$PROJECT_ROOT/shared/lambdas/sqs_to_eventbridge/handler.py" "$DEST/"

cd "$DEST"
zip -r "$BUILD_DIR/sqs_to_eventbridge.zip" . -x '*.pyc' '__pycache__/*' > /dev/null
echo "  → sqs_to_eventbridge.zip ($(du -h "$BUILD_DIR/sqs_to_eventbridge.zip" | cut -f1))"

# --- Package 3: cost_scheduler ---
echo "[3/3] Packaging cost_scheduler..."
DEST="$BUILD_DIR/cost_scheduler"
mkdir -p "$DEST"

# No external dependencies
cp "$PROJECT_ROOT/shared/lambdas/cost_scheduler/handler.py" "$DEST/"

cd "$DEST"
zip -r "$BUILD_DIR/cost_scheduler.zip" . -x '*.pyc' '__pycache__/*' > /dev/null
echo "  → cost_scheduler.zip ($(du -h "$BUILD_DIR/cost_scheduler.zip" | cut -f1))"

# --- Upload to S3 ---
echo ""
echo "Uploading to s3://$DEPLOY_BUCKET/lambda/..."
aws s3 cp "$BUILD_DIR/fpolicy_engine.zip" "s3://$DEPLOY_BUCKET/lambda/fpolicy_engine.zip" --region "$REGION"
aws s3 cp "$BUILD_DIR/sqs_to_eventbridge.zip" "s3://$DEPLOY_BUCKET/lambda/sqs_to_eventbridge.zip" --region "$REGION"
aws s3 cp "$BUILD_DIR/cost_scheduler.zip" "s3://$DEPLOY_BUCKET/lambda/cost_scheduler.zip" --region "$REGION"

echo ""
echo "=== Done! All packages uploaded to s3://$DEPLOY_BUCKET/lambda/ ==="
