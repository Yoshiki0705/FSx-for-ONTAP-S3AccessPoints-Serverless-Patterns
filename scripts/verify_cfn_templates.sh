#!/bin/bash
# CloudFormation テンプレート検証スクリプト
# cfn-lint で全テンプレートを検証する
#
# 前提条件:
#   pip install cfn-lint
#
# 使用方法:
#   cd fsxn-s3ap-serverless-patterns
#   bash scripts/verify_cfn_templates.sh
set -euo pipefail

echo "=== CloudFormation Template Validation ==="
for template in */template.yaml; do
    echo "Validating: $template"
    cfn-lint "$template" || echo "  WARNINGS found (see above)"
done
echo "=== Validation Complete ==="
