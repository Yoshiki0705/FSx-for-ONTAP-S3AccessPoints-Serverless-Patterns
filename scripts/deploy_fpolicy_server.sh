#!/bin/bash
set -euo pipefail
# =============================================================================
# FPolicy Server デプロイスクリプト
#
# 1. ECR リポジトリ作成（初回のみ）
# 2. Docker イメージビルド（ARM64）
# 3. ECR プッシュ
# 4. CloudFormation スタックデプロイ（ECS Fargate + NLB）
#
# Usage:
#   ./scripts/deploy_fpolicy_server.sh <VPC_ID> <SUBNET_IDS> <FSxN_SVM_SG_ID> <SQS_QUEUE_URL>
#
# Example:
#   ./scripts/deploy_fpolicy_server.sh \
#     vpc-0123456789abcdef0 \
#     "subnet-aaa,subnet-bbb" \
#     sg-0123456789abcdef0 \
#     "https://sqs.<REGION>.amazonaws.com/<ACCOUNT_ID>/fsxn-fpolicy-ingestion-..."
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REGION="${AWS_DEFAULT_REGION:-ap-northeast-1}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO="fsxn-fpolicy-server"
STACK_NAME="fsxn-fpolicy-server"
IMAGE_TAG="$(date +%Y%m%d-%H%M%S)"

# Parse arguments
VPC_ID="${1:?Usage: $0 <VPC_ID> <SUBNET_IDS> <FSxN_SVM_SG_ID> <SQS_QUEUE_URL>}"
SUBNET_IDS="${2:?Usage: $0 <VPC_ID> <SUBNET_IDS> <FSxN_SVM_SG_ID> <SQS_QUEUE_URL>}"
FSXN_SVM_SG="${3:?Usage: $0 <VPC_ID> <SUBNET_IDS> <FSxN_SVM_SG_ID> <SQS_QUEUE_URL>}"
SQS_QUEUE_URL="${4:?Usage: $0 <VPC_ID> <SUBNET_IDS> <FSxN_SVM_SG_ID> <SQS_QUEUE_URL>}"

ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPO}"

echo "=== FPolicy Server Deployment ==="
echo "Region: $REGION"
echo "Account: $ACCOUNT_ID"
echo "VPC: $VPC_ID"
echo "Image tag: $IMAGE_TAG"
echo ""

# --- Step 1: ECR Repository ---
echo "[1/4] Ensuring ECR repository exists..."
aws ecr describe-repositories --repository-names "$ECR_REPO" --region "$REGION" > /dev/null 2>&1 || \
  aws ecr create-repository \
    --repository-name "$ECR_REPO" \
    --image-scanning-configuration scanOnPush=true \
    --region "$REGION" > /dev/null
echo "  → ECR: ${ECR_URI}"

# --- Step 2: Docker Build (ARM64) ---
echo "[2/4] Building Docker image (ARM64)..."

# Create build context with schema file
BUILD_CONTEXT="/tmp/fpolicy-server-build"
rm -rf "$BUILD_CONTEXT"
mkdir -p "$BUILD_CONTEXT/schemas"
cp "$PROJECT_ROOT/shared/fpolicy-server/fpolicy_server.py" "$BUILD_CONTEXT/"
cp "$PROJECT_ROOT/shared/fpolicy-server/requirements.txt" "$BUILD_CONTEXT/"
cp "$PROJECT_ROOT/shared/schemas/fpolicy-event-schema.json" "$BUILD_CONTEXT/schemas/"

# Write Dockerfile (corrected paths for build context)
cat > "$BUILD_CONTEXT/Dockerfile" << 'DOCKERFILE'
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY fpolicy_server.py .
COPY schemas/ /app/schemas/

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('localhost', 9898)); s.close()" || exit 1

EXPOSE 9898

ENV FPOLICY_PORT=9898
ENV MODE=realtime
ENV WRITE_COMPLETE_DELAY_SEC=5
ENV SCHEMA_PATH=/app/schemas/fpolicy-event-schema.json

CMD ["python", "fpolicy_server.py"]
DOCKERFILE

docker buildx build \
  --platform linux/arm64 \
  -t "${ECR_URI}:${IMAGE_TAG}" \
  -t "${ECR_URI}:latest" \
  "$BUILD_CONTEXT" \
  --load

echo "  → Image: ${ECR_URI}:${IMAGE_TAG}"

# --- Step 3: ECR Push ---
echo "[3/4] Pushing to ECR..."
aws ecr get-login-password --region "$REGION" | \
  docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

docker push "${ECR_URI}:${IMAGE_TAG}"
docker push "${ECR_URI}:latest"
echo "  → Pushed: ${IMAGE_TAG} + latest"

# --- Step 4: CloudFormation Deploy ---
echo "[4/4] Deploying CloudFormation stack..."
aws cloudformation deploy \
  --template-file "$PROJECT_ROOT/shared/cfn/fpolicy-server-fargate.yaml" \
  --stack-name "$STACK_NAME" \
  --parameter-overrides \
    VpcId="$VPC_ID" \
    SubnetIds="$SUBNET_IDS" \
    FsxnSvmSecurityGroupId="$FSXN_SVM_SG" \
    SqsQueueUrl="$SQS_QUEUE_URL" \
    ContainerImage="${ECR_URI}:${IMAGE_TAG}" \
  --capabilities CAPABILITY_NAMED_IAM \
  --region "$REGION" \
  --no-fail-on-empty-changeset

echo ""
echo "=== Deployment Complete ==="
echo ""

# Get NLB DNS and instructions
NLB_DNS=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query 'Stacks[0].Outputs[?OutputKey==`NLBDnsName`].OutputValue' \
  --output text)

echo "NLB DNS: $NLB_DNS"
echo ""
echo "Next steps:"
echo "  1. Get NLB private IP:"
echo "     aws ec2 describe-network-interfaces \\"
echo "       --filters Name=description,Values=\"ELB net/fpolicy-nlb-*\" \\"
echo "       --query 'NetworkInterfaces[*].PrivateIpAddress' --output text"
echo ""
echo "  2. Configure ONTAP FPolicy external-engine:"
echo "     vserver fpolicy policy external-engine create \\"
echo "       -vserver <SVM_NAME> \\"
echo "       -engine-name fpolicy_aws_engine \\"
echo "       -primary-servers <NLB_PRIVATE_IP> \\"
echo "       -port 9898 \\"
echo "       -extern-engine-type asynchronous"
