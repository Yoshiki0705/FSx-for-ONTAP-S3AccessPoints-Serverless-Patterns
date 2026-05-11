#!/bin/bash
# Deploy multiple UCs (UC1-UC17) using their template-deploy.yaml files.
# Uses same UC6 infra (VPC, S3 AP, Secrets Manager).
#
# Usage:
#   bash scripts/deploy_generic_ucs.sh UC1 UC11 UC14 UC9
#   bash scripts/deploy_generic_ucs.sh UC15 UC16 UC17
#   bash scripts/deploy_generic_ucs.sh legal-compliance retail-catalog insurance-claims
#
# Environment Variables:
#   DEPLOY_BUCKET          - S3 bucket for Lambda packages and CFn templates
#   S3_AP_ALIAS            - FSxN S3 Access Point alias
#   S3_AP_NAME             - FSxN S3 Access Point name (for IAM dual-format)
#   VPC_ID                 - VPC ID for Lambda functions
#   SUBNETS                - Comma-separated private subnet IDs
#   NOTIFICATION_EMAIL     - Email for SNS notifications
#   ONTAP_SECRET_NAME      - Secrets Manager secret name for ONTAP credentials
#   ONTAP_MANAGEMENT_IP    - ONTAP management endpoint IP
#   SVM_UUID               - ONTAP SVM UUID
#   ENABLE_S3_GATEWAY_EP   - "true" or "false" (default: "false")
#                            Set to "false" when S3 Gateway Endpoint already exists in VPC
#
# UC1-specific parameters (optional):
#   ENABLE_EVENT_DRIVEN    - "true" or "false" (default: "false")
#                            Enables S3 → EventBridge → Step Functions auto-trigger
#   ENABLE_CLOUDWATCH_ALARMS - "true" or "false" (default: "false")
#                            Enables CloudWatch Alarms + EventBridge failure notifications
#
# IMPORTANT: If deploying to a VPC that already has a S3 Gateway Endpoint
# (e.g., from UC6 stack), set ENABLE_S3_GATEWAY_EP=false to avoid
# "route table already has a route with destination-prefix-list-id" error.
#
# IMPORTANT: Do NOT set EnableVpcEndpoints=true if the VPC already has
# Interface Endpoints from another stack. This causes "private-dns-enabled
# cannot be set" errors. See docs/operational-runbooks/deployment-troubleshooting.md
# Failure Mode 7.
#
# Performance note (UC1): Discovery Lambda requires 512MB/900s for large
# ONTAP volumes (>100 files). See Failure Mode 2 in deployment-troubleshooting.md.

set -u

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

DEPLOY_BUCKET="${DEPLOY_BUCKET:-fsxn-eda-deploy-<ACCOUNT_ID>}"
S3_AP_ALIAS="${S3_AP_ALIAS:-<S3_AP_ALIAS>}"
S3_AP_NAME="${S3_AP_NAME:-eda-demo-s3ap}"
VPC_ID="${VPC_ID:-<VPC_ID>}"
SUBNETS="${SUBNETS:-<SUBNET_ID>,<SUBNET_ID>}"
NOTIFICATION_EMAIL="${NOTIFICATION_EMAIL:-<NOTIFICATION_EMAIL>}"
ONTAP_SECRET_NAME="${ONTAP_SECRET_NAME:-fsx-ontap-fsxadmin-credentials}"
ONTAP_MANAGEMENT_IP="${ONTAP_MANAGEMENT_IP:-<ONTAP_MGMT_IP>}"
SVM_UUID="${SVM_UUID:-<SVM_UUID>}"
REGION="${AWS_REGION:-ap-northeast-1}"
# Set to "false" when deploying to a VPC that already has a S3 Gateway Endpoint
ENABLE_S3_GATEWAY_EP="${ENABLE_S3_GATEWAY_EP:-false}"

# Map short names to directories (using case for bash 3.2 compat)
uc_to_dir() {
    case "$1" in
        UC1) echo "legal-compliance" ;;
        UC2) echo "financial-idp" ;;
        UC3) echo "manufacturing-analytics" ;;
        UC4) echo "media-vfx" ;;
        UC5) echo "healthcare-dicom" ;;
        UC6) echo "semiconductor-eda" ;;
        UC7) echo "genomics-pipeline" ;;
        UC8) echo "energy-seismic" ;;
        UC9) echo "autonomous-driving" ;;
        UC10) echo "construction-bim" ;;
        UC11) echo "retail-catalog" ;;
        UC12) echo "logistics-ocr" ;;
        UC13) echo "education-research" ;;
        UC14) echo "insurance-claims" ;;
        UC15) echo "defense-satellite" ;;
        UC16) echo "government-archives" ;;
        UC17) echo "smart-city-geospatial" ;;
        *) echo "$1" ;;  # already a directory name
    esac
}

cd "${PROJECT_DIR}"

deploy_one() {
    local INPUT="$1"
    local UC=$(uc_to_dir "$INPUT")
    local STACK="fsxn-${UC}-demo"
    local TEMPLATE="${UC}/template-deploy.yaml"

    if [[ ! -f "$TEMPLATE" ]]; then
        echo "[$UC] MISSING template: $TEMPLATE" >&2
        return 1
    fi

    echo "[$UC] Deploying to stack ${STACK}..."

    aws cloudformation deploy \
        --template-file "$TEMPLATE" \
        --stack-name "$STACK" \
        --region "$REGION" \
        --s3-bucket "$DEPLOY_BUCKET" \
        --s3-prefix "cfn-templates/${UC}" \
        --parameter-overrides \
            DeployBucket="$DEPLOY_BUCKET" \
            S3AccessPointAlias="$S3_AP_ALIAS" \
            S3AccessPointName="${S3_AP_NAME:-}" \
            OntapSecretName="$ONTAP_SECRET_NAME" \
            OntapManagementIp="$ONTAP_MANAGEMENT_IP" \
            SvmUuid="$SVM_UUID" \
            VpcId="$VPC_ID" \
            PrivateSubnetIds="$SUBNETS" \
            NotificationEmail="$NOTIFICATION_EMAIL" \
            EnableS3GatewayEndpoint="$ENABLE_S3_GATEWAY_EP" \
            EnableVpcEndpoints="false" \
        --capabilities CAPABILITY_NAMED_IAM \
        --no-fail-on-empty-changeset 2>&1 | tail -3

    echo "[$UC] ✅ Done"
}

if [[ $# -eq 0 ]]; then
    echo "Usage: $0 <UC1|UC15|legal-compliance> [UC11] [UC14] [...]"
    exit 1
fi

# Deploy in parallel
for uc_input in "$@"; do
    deploy_one "$uc_input" &
done
wait

echo ""
echo "=== All deployments finished ==="
