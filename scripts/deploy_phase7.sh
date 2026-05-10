#!/bin/bash
# Phase 7 (UC15 / UC16 / UC17) ワンショットデプロイスクリプト
#
# 事前にパッケージ化 + デプロイ + サンプル実行を順次実施する。
# 既存の UC6 インフラ（VPC / S3 AP / Secrets Manager）を再利用する前提。
#
# Usage:
#   bash scripts/deploy_phase7.sh                    # 3 UC 全部
#   bash scripts/deploy_phase7.sh defense-satellite  # 1 UC のみ
#
# Environment variables:
#   DEPLOY_BUCKET        Lambda zip 格納 S3 バケット
#   S3_AP_ALIAS          S3 Access Point Alias
#   S3_AP_NAME           S3 Access Point Name (権限付与に必須)
#   VPC_ID               VPC ID
#   SUBNETS              カンマ区切りプライベートサブネット ID
#   NOTIFICATION_EMAIL   SNS 通知先
#   ONTAP_SECRET_NAME    ONTAP 認証情報 Secrets Manager 名
#   ONTAP_MANAGEMENT_IP  ONTAP クラスタ管理 IP
#   SVM_UUID             SVM UUID

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# --- Defaults (UC6 既存インフラ) ---
DEPLOY_BUCKET="${DEPLOY_BUCKET:-fsxn-eda-deploy-178625946981}"
S3_AP_ALIAS="${S3_AP_ALIAS:-eda-demo-s3ap-fnwqydfpmd4gabncr8xqepjrrt131apn1a-ext-s3alias}"
S3_AP_NAME="${S3_AP_NAME:-eda-demo-s3ap}"
VPC_ID="${VPC_ID:-vpc-0ae01826f906191af}"
SUBNETS="${SUBNETS:-subnet-0307ebbd55b35c842,subnet-0af86ebd3c65481b8}"
NOTIFICATION_EMAIL="${NOTIFICATION_EMAIL:-yoshiki.fujiwara@netapp.com}"
ONTAP_SECRET_NAME="${ONTAP_SECRET_NAME:-fsx-ontap-fsxadmin-credentials}"
ONTAP_MANAGEMENT_IP="${ONTAP_MANAGEMENT_IP:-10.0.3.72}"
SVM_UUID="${SVM_UUID:-9ae87e42-068a-11f1-b1ff-ada95e61ee66}"
REGION="${AWS_REGION:-ap-northeast-1}"

UCS=()
if [[ $# -eq 0 ]]; then
    UCS=("defense-satellite" "government-archives" "smart-city-geospatial")
else
    UCS=("$@")
fi

cd "${PROJECT_ROOT}"

for UC in "${UCS[@]}"; do
    STACK_NAME="fsxn-uc$(
        case $UC in
            defense-satellite) echo 15 ;;
            government-archives) echo 16 ;;
            smart-city-geospatial) echo 17 ;;
            *) echo "unknown-$UC"; exit 1 ;;
        esac
    )-demo"

    echo ""
    echo "========================================"
    echo " Deploying ${UC} -> ${STACK_NAME}"
    echo "========================================"

    # 1) パッケージング
    echo "[1/3] Packaging Lambda zips..."
    UC="$UC" bash "${SCRIPT_DIR}/package_uc15_lambdas.sh"

    # 2) CloudFormation デプロイ
    echo "[2/3] Deploying CloudFormation stack..."
    EXTRA_PARAMS=""
    if [[ "$UC" == "government-archives" ]]; then
        EXTRA_PARAMS="OpenSearchMode=none CrossRegion=us-east-1 UseCrossRegion=true"
    elif [[ "$UC" == "smart-city-geospatial" ]]; then
        EXTRA_PARAMS="BedrockModelId=amazon.nova-lite-v1:0"
    fi

    aws cloudformation deploy \
        --template-file "${UC}/template-deploy.yaml" \
        --stack-name "${STACK_NAME}" \
        --region "${REGION}" \
        --parameter-overrides \
            DeployBucket="${DEPLOY_BUCKET}" \
            S3AccessPointAlias="${S3_AP_ALIAS}" \
            S3AccessPointName="${S3_AP_NAME}" \
            OntapSecretName="${ONTAP_SECRET_NAME}" \
            OntapManagementIp="${ONTAP_MANAGEMENT_IP}" \
            SvmUuid="${SVM_UUID}" \
            VpcId="${VPC_ID}" \
            PrivateSubnetIds="${SUBNETS}" \
            NotificationEmail="${NOTIFICATION_EMAIL}" \
            $EXTRA_PARAMS \
        --capabilities CAPABILITY_NAMED_IAM \
        --no-fail-on-empty-changeset

    # 3) スタック情報表示
    echo "[3/3] Stack outputs:"
    aws cloudformation describe-stacks \
        --stack-name "${STACK_NAME}" \
        --region "${REGION}" \
        --query 'Stacks[0].Outputs[?OutputKey==`StateMachineArn` || OutputKey==`OutputBucketName`].[OutputKey,OutputValue]' \
        --output table

    echo "✅ ${STACK_NAME} deployed"
done

echo ""
echo "========================================"
echo " All Phase 7 stacks deployed"
echo "========================================"
echo ""
echo "Next steps:"
echo "  1. Upload sample data to S3 AP:"
echo "     aws s3 cp <file> s3://${S3_AP_ALIAS}/satellite/...  (UC15)"
echo "     aws s3 cp <file> s3://${S3_AP_ALIAS}/archives/...   (UC16)"
echo "     aws s3 cp <file> s3://${S3_AP_ALIAS}/gis/...        (UC17)"
echo ""
echo "  2. Execute Step Functions:"
echo "     aws stepfunctions start-execution --state-machine-arn <arn> --input '{}'"
echo ""
echo "  3. Cleanup when done:"
echo "     bash scripts/cleanup_phase7.sh"
