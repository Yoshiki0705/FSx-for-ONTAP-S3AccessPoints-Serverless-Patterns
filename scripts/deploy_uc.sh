#!/bin/bash
# UC デプロイスクリプト
# Usage: ./scripts/deploy_uc.sh <uc_name> <action>
# Examples:
#   ./scripts/deploy_uc.sh financial-idp package    # Lambda ZIP パッケージ作成 + S3 アップロード
#   ./scripts/deploy_uc.sh financial-idp deploy     # CloudFormation デプロイ
#   ./scripts/deploy_uc.sh financial-idp validate   # テンプレート検証のみ
#   ./scripts/deploy_uc.sh financial-idp delete      # スタック削除

set -euo pipefail

UC_NAME="${1:?Usage: $0 <uc_name> <action>}"
ACTION="${2:?Usage: $0 <uc_name> <action>}"

REGION="${AWS_DEFAULT_REGION:-ap-northeast-1}"
DEPLOY_BUCKET="${DEPLOY_BUCKET:-fsxn-s3ap-deploy-$(aws sts get-caller-identity --query Account --output text 2>/dev/null)}"
STACK_PREFIX="fsxn"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# UC ディレクトリとスタック名のマッピング
case "$UC_NAME" in
  legal-compliance)    STACK_NAME="${STACK_PREFIX}-legal-compliance" ;;
  financial-idp)       STACK_NAME="${STACK_PREFIX}-financial-idp" ;;
  manufacturing-analytics) STACK_NAME="${STACK_PREFIX}-manufacturing" ;;
  media-vfx)           STACK_NAME="${STACK_PREFIX}-media-vfx" ;;
  healthcare-dicom)    STACK_NAME="${STACK_PREFIX}-healthcare-dicom" ;;
  *) echo "Unknown UC: $UC_NAME"; exit 1 ;;
esac

UC_DIR="${PROJECT_ROOT}/${UC_NAME}"
FUNCTIONS_DIR="${UC_DIR}/functions"
SHARED_DIR="${PROJECT_ROOT}/shared"

package_lambda() {
  local func_name="$1"
  local func_dir="${FUNCTIONS_DIR}/${func_name}"
  # UC 名をプレフィックスに付けてユニークなパッケージ名にする
  local zip_name="${UC_NAME}-${func_name}.zip"
  local tmp_dir=$(mktemp -d)

  echo "📦 Packaging ${func_name}..."

  # Lambda ハンドラーをコピー
  cp "${func_dir}/handler.py" "${tmp_dir}/"

  # shared モジュールをコピー
  mkdir -p "${tmp_dir}/shared"
  cp "${SHARED_DIR}/__init__.py" "${tmp_dir}/shared/"
  cp "${SHARED_DIR}/ontap_client.py" "${tmp_dir}/shared/"
  cp "${SHARED_DIR}/fsx_helper.py" "${tmp_dir}/shared/"
  cp "${SHARED_DIR}/s3ap_helper.py" "${tmp_dir}/shared/"
  cp "${SHARED_DIR}/exceptions.py" "${tmp_dir}/shared/"
  cp "${SHARED_DIR}/discovery_handler.py" "${tmp_dir}/shared/"

  # ZIP 作成
  (cd "${tmp_dir}" && zip -r "${PROJECT_ROOT}/${zip_name}" . -x "__pycache__/*" "*.pyc")

  # S3 アップロード
  aws s3 cp "${PROJECT_ROOT}/${zip_name}" "s3://${DEPLOY_BUCKET}/lambda/${zip_name}" --region "${REGION}"
  echo "  ✅ Uploaded to s3://${DEPLOY_BUCKET}/lambda/${zip_name}"

  # クリーンアップ
  rm -rf "${tmp_dir}" "${PROJECT_ROOT}/${zip_name}"
}

do_package() {
  echo "🔄 Packaging Lambda functions for ${UC_NAME}..."

  if [ ! -d "${FUNCTIONS_DIR}" ]; then
    echo "❌ Functions directory not found: ${FUNCTIONS_DIR}"
    exit 1
  fi

  for func_dir in "${FUNCTIONS_DIR}"/*/; do
    func_name=$(basename "${func_dir}")
    if [ -f "${func_dir}/handler.py" ]; then
      package_lambda "${func_name}"
    fi
  done

  echo "✅ All Lambda functions packaged and uploaded for ${UC_NAME}"
}

do_validate() {
  local template="${UC_DIR}/template-deploy.yaml"
  if [ ! -f "${template}" ]; then
    template="${UC_DIR}/template.yaml"
  fi
  echo "🔍 Validating ${template}..."
  aws cloudformation validate-template \
    --template-body "file://${template}" \
    --region "${REGION}" \
    --output json
  echo "✅ Template validation passed"
}

do_deploy() {
  local template="${UC_DIR}/template-deploy.yaml"
  if [ ! -f "${template}" ]; then
    echo "❌ template-deploy.yaml not found. Run 'package' first or create template-deploy.yaml"
    exit 1
  fi

  echo "🚀 Deploying ${STACK_NAME}..."
  echo "   Template: ${template}"
  echo "   Region: ${REGION}"
}

do_delete() {
  echo "🗑️  Deleting stack ${STACK_NAME}..."
  aws cloudformation delete-stack \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}"
  echo "⏳ Waiting for stack deletion..."
  aws cloudformation wait stack-delete-complete \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}"
  echo "✅ Stack ${STACK_NAME} deleted"
}

case "$ACTION" in
  package)  do_package ;;
  validate) do_validate ;;
  deploy)   do_deploy ;;
  delete)   do_delete ;;
  *) echo "Unknown action: $ACTION (use: package, validate, deploy, delete)"; exit 1 ;;
esac
