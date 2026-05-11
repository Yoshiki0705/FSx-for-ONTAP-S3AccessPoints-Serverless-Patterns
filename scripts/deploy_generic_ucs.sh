#!/bin/bash
# Deploy multiple existing UCs (UC1-UC14) using their template-deploy.yaml files.
# Uses same UC6 infra (VPC, S3 AP, Secrets Manager).
#
# Usage:
#   bash scripts/deploy_generic_ucs.sh UC1 UC11 UC14 UC9
#   bash scripts/deploy_generic_ucs.sh legal-compliance retail-catalog insurance-claims

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

# Map short names to directories (using case for bash 3.2 compat)
uc_to_dir() {
    case "$1" in
        UC1) echo "legal-compliance" ;;
        UC2) echo "financial-idp" ;;
        UC3) echo "manufacturing-analytics" ;;
        UC4) echo "media-vfx" ;;
        UC5) echo "healthcare-dicom" ;;
        UC7) echo "genomics-pipeline" ;;
        UC8) echo "energy-seismic" ;;
        UC9) echo "autonomous-driving" ;;
        UC10) echo "construction-bim" ;;
        UC11) echo "retail-catalog" ;;
        UC12) echo "logistics-ocr" ;;
        UC13) echo "education-research" ;;
        UC14) echo "insurance-claims" ;;
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
        --capabilities CAPABILITY_NAMED_IAM \
        --no-fail-on-empty-changeset 2>&1 | tail -3

    echo "[$UC] ✅ Done"
}

if [[ $# -eq 0 ]]; then
    echo "Usage: $0 <UC1|legal-compliance> [UC11] [UC14] [...]"
    exit 1
fi

# Deploy in parallel
for uc_input in "$@"; do
    deploy_one "$uc_input" &
done
wait

echo ""
echo "=== All deployments finished ==="
