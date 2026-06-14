#!/bin/bash
# =============================================================================
# template-deploy.yaml 一括再生成スクリプト
# =============================================================================
# テンプレート修正後に実行して、全 UC の template-deploy.yaml を再生成する。
#
# Usage:
#   ./scripts/regenerate_deploy_templates.sh
#
# Prerequisites:
#   - Python 3.9+
#   - プロジェクトルートから実行
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "=== template-deploy.yaml 一括再生成 ==="
echo ""

# Phase 1 + Phase 2 全 UC
ALL_UCS=(
  legal-compliance
  financial-idp
  manufacturing-analytics
  media-vfx
  healthcare-dicom
  semiconductor-eda
  genomics-pipeline
  energy-seismic
  autonomous-driving
  construction-bim
  retail-catalog
  logistics-ocr
  education-research
  insurance-claims
)

python3 "${SCRIPT_DIR}/create_deploy_template.py" "${ALL_UCS[@]}"

echo ""
echo "✅ 全 ${#ALL_UCS[@]} UC の template-deploy.yaml を再生成しました"
echo ""
echo "次のステップ:"
echo "  1. cfn-lint で検証: cfn-lint */template-deploy.yaml"
echo "  2. Lambda パッケージ再アップロード: ./scripts/deploy_phase2_batch.sh package"
echo "  3. CloudFormation 再デプロイ: ./scripts/deploy_phase2_batch.sh deploy"
