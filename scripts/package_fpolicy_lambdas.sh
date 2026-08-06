#!/bin/bash
set -euo pipefail
# =============================================================================
# Phase 10: FPolicy Lambda パッケージングスクリプト
#
# Usage:
#   ./scripts/package_fpolicy_lambdas.sh [DEPLOY_BUCKET]
#
# 注意事項:
#   - jsonschema のバージョンは requirements.txt から読む（ここに書かない）
#   - ARM64 / python3.13 Lambda 用にプラットフォーム指定でインストール
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

# Install jsonschema for the Lambda's platform.
#
# The version comes from requirements.txt. This line used to carry its own range
# ('jsonschema>=4.17.0,<4.18.0'), which made it a third place the version was
# declared alongside requirements.txt and pyproject.toml, and it drifted from both.
JSONSCHEMA_PIN=$(grep -m1 '^jsonschema==' "$PROJECT_ROOT/requirements.txt")
if [ -z "$JSONSCHEMA_PIN" ]; then
  echo "ERROR: no '^jsonschema==' pin found in requirements.txt" >&2
  exit 1
fi
echo "  jsonschema pin: $JSONSCHEMA_PIN (from requirements.txt)"

# --python-version matches the Runtime in shared/cfn/fpolicy-ingestion.yaml
# (python3.13). It said 3.12 before, which selects cp312 wheel tags for a cp313
# runtime — harmless for a pure-Python package, wrong as soon as a dependency
# ships compiled wheels, which is exactly what jsonschema 4.18+ does via rpds-py.
#
# There is deliberately no fallback to a plain `pip3 install`. The previous line
# ended with `2>/dev/null || pip3 install ... -t "$DEST"`, which on failure
# silently installed wheels for the *build machine* — macOS arm64 wheels in a
# Linux Lambda zip — and hid the reason with 2>/dev/null. A zip that fails to
# import at runtime is worse than a build that stops here.
pip3 install "$JSONSCHEMA_PIN" \
  -t "$DEST" \
  --quiet \
  --platform manylinux2014_aarch64 \
  --only-binary=:all: \
  --python-version 3.13

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
