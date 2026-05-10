#!/bin/bash
# Phase 7 デプロイ前の前提条件検証スクリプト
#
# デプロイ失敗の大半は以下のいずれかが原因。実際に AWS を呼び出して検証する。
#  1. AWS CLI クレデンシャル未設定
#  2. デプロイ S3 バケットが存在しない
#  3. 指定した S3 Access Point が存在しない
#  4. VPC / サブネットが存在しない
#  5. Bedrock モデルアクセスが未有効化（UC17 のみ）
#
# Usage:
#   bash scripts/verify_phase7_prerequisites.sh

set -u

REGION="${AWS_REGION:-ap-northeast-1}"
DEPLOY_BUCKET="${DEPLOY_BUCKET:-fsxn-eda-deploy-178625946981}"
S3_AP_ALIAS="${S3_AP_ALIAS:-eda-demo-s3ap-fnwqydfpmd4gabncr8xqepjrrt131apn1a-ext-s3alias}"
S3_AP_NAME="${S3_AP_NAME:-eda-demo-s3ap}"
VPC_ID="${VPC_ID:-vpc-0ae01826f906191af}"
SUBNETS="${SUBNETS:-subnet-0307ebbd55b35c842,subnet-0af86ebd3c65481b8}"

PASS=0
FAIL=0

check() {
    local label="$1"
    shift
    echo -n "[?] $label ... "
    if "$@" >/dev/null 2>&1; then
        echo "OK"
        PASS=$((PASS + 1))
    else
        echo "FAIL"
        FAIL=$((FAIL + 1))
        return 1
    fi
}

echo "=== Phase 7 Prerequisites Check ==="
echo "Region: ${REGION}"
echo ""

check "AWS credentials valid" \
    aws sts get-caller-identity --region "${REGION}"

check "Deploy bucket exists (${DEPLOY_BUCKET})" \
    aws s3 ls "s3://${DEPLOY_BUCKET}/" --region "${REGION}"

check "VPC exists (${VPC_ID})" \
    aws ec2 describe-vpcs --vpc-ids "${VPC_ID}" --region "${REGION}"

echo -n "[?] Private subnets exist (${SUBNETS}) ... "
IFS=',' read -ra SUBNET_ARRAY <<< "${SUBNETS}"
SUBNET_OK=1
for subnet in "${SUBNET_ARRAY[@]}"; do
    if ! aws ec2 describe-subnets --subnet-ids "${subnet}" --region "${REGION}" >/dev/null 2>&1; then
        SUBNET_OK=0
        break
    fi
done
if [[ $SUBNET_OK -eq 1 ]]; then
    echo "OK"
    PASS=$((PASS + 1))
else
    echo "FAIL"
    FAIL=$((FAIL + 1))
fi

check "S3 Access Point accessible (${S3_AP_ALIAS})" \
    aws s3 ls "s3://${S3_AP_ALIAS}/" --region "${REGION}"

echo -n "[?] Bedrock Nova Lite model access (UC17 only) ... "
if aws bedrock list-foundation-models --region "${REGION}" --query "modelSummaries[?modelId=='amazon.nova-lite-v1:0']" --output text 2>/dev/null | grep -q "amazon.nova-lite-v1"; then
    # 実際の invoke アクセスは model access ページで確認が必要
    echo "OK (model listed, check console for invoke access)"
    PASS=$((PASS + 1))
else
    echo "WARN (model not listed, check console → Model access)"
fi

echo ""
echo "=== Summary ==="
echo "Passed: $PASS"
echo "Failed: $FAIL"
echo ""
if [[ $FAIL -eq 0 ]]; then
    echo "✅ All prerequisites met. Safe to run: bash scripts/deploy_phase7.sh"
    exit 0
else
    echo "❌ Fix failed checks before deploying"
    exit 1
fi
