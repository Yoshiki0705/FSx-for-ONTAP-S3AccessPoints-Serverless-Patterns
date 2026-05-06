#!/bin/bash
set -euo pipefail

# =============================================================================
# Phase 3 デプロイスクリプト
# Kinesis ストリーミング (UC11) + SageMaker Batch Transform (UC9) + 可観測性
# =============================================================================

REGION="${AWS_DEFAULT_REGION:-ap-northeast-1}"
ACCOUNT_ID=$(aws sts get-caller-identity --query 'Account' --output text)

# --- 必須パラメータ ---
S3_ACCESS_POINT_ALIAS="${S3_ACCESS_POINT_ALIAS:-}"
ONTAP_SECRET_NAME="${ONTAP_SECRET_NAME:-fsx-ontap-fsxadmin-credentials}"
ONTAP_MANAGEMENT_IP="${ONTAP_MANAGEMENT_IP:-}"
SVM_UUID="${SVM_UUID:-}"
VPC_ID="${VPC_ID:-}"
SUBNET_IDS="${SUBNET_IDS:-}"
NOTIFICATION_EMAIL="${NOTIFICATION_EMAIL:-}"

# --- Phase 3 オプション ---
ENABLE_STREAMING="${ENABLE_STREAMING:-false}"
ENABLE_SAGEMAKER="${ENABLE_SAGEMAKER:-false}"
ENABLE_XRAY="${ENABLE_XRAY:-true}"
MOCK_MODE="${MOCK_MODE:-true}"

echo "=== Phase 3 Deploy Configuration ==="
echo "Region: $REGION"
echo "Account: $ACCOUNT_ID"
echo "S3 AP: $S3_ACCESS_POINT_ALIAS"
echo "Streaming: $ENABLE_STREAMING"
echo "SageMaker: $ENABLE_SAGEMAKER"
echo "X-Ray: $ENABLE_XRAY"
echo "Mock Mode: $MOCK_MODE"
echo ""

if [ -z "$S3_ACCESS_POINT_ALIAS" ] || [ -z "$ONTAP_MANAGEMENT_IP" ] || [ -z "$VPC_ID" ] || [ -z "$SUBNET_IDS" ]; then
    echo "ERROR: Required parameters not set."
    echo "Usage:"
    echo "  export S3_ACCESS_POINT_ALIAS=<alias>-ext-s3alias"
    echo "  export ONTAP_MANAGEMENT_IP=<management-ip>"
    echo "  export SVM_UUID=svm-xxxxx"
    echo "  export VPC_ID=vpc-xxxxx"
    echo "  export SUBNET_IDS=subnet-xxxxx"
    echo "  export NOTIFICATION_EMAIL=your@email.com"
    echo "  ./scripts/deploy_phase3.sh"
    echo ""
    echo "VPC Connectivity Requirements:"
    echo "  Discovery Lambda requires VPC Endpoints or NAT Gateway for:"
    echo "  - S3 Access Point (Gateway Endpoint works — ensure route table"
    echo "    association with Lambda subnet + endpoint policy allows AP ARN)"
    echo "  - Secrets Manager (Interface Endpoint with Private DNS)"
    echo "  - CloudWatch Logs (Interface Endpoint)"
    echo ""
    echo "  IAM Policy: S3 AP requires BOTH alias format AND ARN format:"
    echo "    arn:aws:s3:::alias-ext-s3alias (S3 API routing)"
    echo "    arn:aws:s3:\${Region}:\${Account}:accesspoint/* (IAM evaluation)"
    echo ""
    echo "  Set EnableVpcEndpoints=true in the deploy command, or ensure"
    echo "  existing VPC Endpoints / NAT Gateway are available."
    exit 1
fi

# --- Lambda コードパッケージング ---
# 注: aws cloudformation package は親ディレクトリの shared/ を含められないため、
#     各Lambda関数ごとに個別ZIPを作成し、template-deploy.yaml (S3Bucket/S3Key参照) でデプロイする
CODE_BUCKET="${CODE_BUCKET:-fsxn-s3ap-lambda-code-${ACCOUNT_ID}-${REGION}}"

# S3 バケット作成（存在しない場合）
if ! aws s3api head-bucket --bucket "$CODE_BUCKET" 2>/dev/null; then
    echo "Creating code bucket: $CODE_BUCKET"
    aws s3api create-bucket \
        --bucket "$CODE_BUCKET" \
        --region "$REGION" \
        --create-bucket-configuration LocationConstraint="$REGION"
fi

# 個別 Lambda ZIP 作成 + S3 アップロード
# 各ZIPには handler.py + shared/ がルートレベルに含まれる
# → Handler は handler.handler で解決される
package_lambda() {
    local uc_name=$1
    local func_name=$2
    local tmp_dir=$(mktemp -d)
    
    cp -r "${uc_name}/functions/${func_name}/"* "$tmp_dir/" 2>/dev/null
    cp -r shared "$tmp_dir/"
    find "$tmp_dir" -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    
    (cd "$tmp_dir" && zip -qr "/tmp/${uc_name}-${func_name}.zip" .)
    rm -rf "$tmp_dir"
    
    aws s3 cp "/tmp/${uc_name}-${func_name}.zip" \
        "s3://${CODE_BUCKET}/lambda/${uc_name}-${func_name}.zip" --quiet
    rm -f "/tmp/${uc_name}-${func_name}.zip"
    echo "  ✅ ${uc_name}/${func_name}"
}

echo "=== Packaging Lambda functions ==="
# UC11: Retail Catalog
for func in discovery image_tagging catalog_metadata quality_check stream_producer stream_consumer; do
    package_lambda "retail-catalog" "$func"
done

# UC9: Autonomous Driving
for func in discovery frame_extraction point_cloud_qc annotation_manager sagemaker_invoke sagemaker_callback; do
    package_lambda "autonomous-driving" "$func"
done
echo ""

# --- UC11: Retail Catalog (with Kinesis streaming) ---
echo "=== Deploying UC11: Retail Catalog ==="
aws cloudformation deploy \
    --template-file retail-catalog/template-deploy.yaml \
    --stack-name fsxn-retail-catalog-phase3 \
    --capabilities CAPABILITY_NAMED_IAM \
    --parameter-overrides \
        S3AccessPointAlias="$S3_ACCESS_POINT_ALIAS" \
        OntapSecretName="$ONTAP_SECRET_NAME" \
        OntapManagementIp="$ONTAP_MANAGEMENT_IP" \
        SvmUuid="$SVM_UUID" \
        VpcId="$VPC_ID" \
        PrivateSubnetIds="$SUBNET_IDS" \
        NotificationEmail="$NOTIFICATION_EMAIL" \
        EnableStreamingMode="$ENABLE_STREAMING" \
        EnableXRayTracing="$ENABLE_XRAY" \
        EnableCloudWatchAlarms=true \
        DeployBucket="$CODE_BUCKET" \
    --no-fail-on-empty-changeset \
    --region "$REGION"

echo "UC11 deployed successfully"

# --- UC9: Autonomous Driving (with SageMaker) ---
echo "=== Deploying UC9: Autonomous Driving ==="
aws cloudformation deploy \
    --template-file autonomous-driving/template-deploy.yaml \
    --stack-name fsxn-autonomous-driving-phase3 \
    --capabilities CAPABILITY_NAMED_IAM \
    --parameter-overrides \
        S3AccessPointAlias="$S3_ACCESS_POINT_ALIAS" \
        OntapSecretName="$ONTAP_SECRET_NAME" \
        OntapManagementIp="$ONTAP_MANAGEMENT_IP" \
        SvmUuid="$SVM_UUID" \
        VpcId="$VPC_ID" \
        PrivateSubnetIds="$SUBNET_IDS" \
        NotificationEmail="$NOTIFICATION_EMAIL" \
        EnableSageMakerTransform="$ENABLE_SAGEMAKER" \
        MockMode="$MOCK_MODE" \
        EnableXRayTracing="$ENABLE_XRAY" \
        EnableCloudWatchAlarms=true \
        DeployBucket="$CODE_BUCKET" \
    --no-fail-on-empty-changeset \
    --region "$REGION"

echo "UC9 deployed successfully"

# --- Observability Dashboard ---
echo "=== Deploying Observability Dashboard ==="
aws cloudformation deploy \
    --template-file shared/cfn/observability-dashboard.yaml \
    --stack-name fsxn-observability-dashboard \
    --parameter-overrides \
        UseCaseStackNames="fsxn-retail-catalog-phase3,fsxn-autonomous-driving-phase3" \
        EnableKinesisWidgets="$ENABLE_STREAMING" \
        EnableSageMakerWidgets="$ENABLE_SAGEMAKER" \
    --no-fail-on-empty-changeset \
    --region "$REGION"

echo "Dashboard deployed successfully"

# --- Alert Automation ---
echo "=== Deploying Alert Automation ==="
aws cloudformation deploy \
    --template-file shared/cfn/alert-automation.yaml \
    --stack-name fsxn-alert-automation \
    --capabilities CAPABILITY_NAMED_IAM \
    --parameter-overrides \
        NotificationEmail="$NOTIFICATION_EMAIL" \
        UseCaseStackNames="fsxn-retail-catalog-phase3,fsxn-autonomous-driving-phase3" \
        EnableKinesisAlarms="$ENABLE_STREAMING" \
    --no-fail-on-empty-changeset \
    --region "$REGION"

echo "Alert automation deployed successfully"

echo ""
echo "=== Phase 3 Deployment Complete ==="
echo "Stacks deployed:"
echo "  - fsxn-retail-catalog-phase3"
echo "  - fsxn-autonomous-driving-phase3"
echo "  - fsxn-observability-dashboard"
echo "  - fsxn-alert-automation"
