#!/bin/bash
# Enhanced deploy script for all UCs with UC-specific parameter handling.
# Handles VPC Gateway Endpoint collision by using empty PrivateRouteTableIds.
# Handles S3 AP ARN permission gap by adding inline IAM policy post-deploy.

set -u

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_DIR}"

DEPLOY_BUCKET="${DEPLOY_BUCKET:-fsxn-eda-deploy-<ACCOUNT_ID>}"
S3_AP_ALIAS="${S3_AP_ALIAS:-<S3_AP_ALIAS>}"
VPC_ID="${VPC_ID:-<VPC_ID>}"
SUBNETS="${SUBNETS:-<SUBNET_ID>,<SUBNET_ID>}"
NOTIFICATION_EMAIL="${NOTIFICATION_EMAIL:-<NOTIFICATION_EMAIL>}"
ONTAP_SECRET_NAME="${ONTAP_SECRET_NAME:-fsx-ontap-fsxadmin-credentials}"
ONTAP_MANAGEMENT_IP="${ONTAP_MANAGEMENT_IP:-<ONTAP_MGMT_IP>}"
SVM_UUID="${SVM_UUID:-<SVM_UUID>}"
VOLUME_UUID="${VOLUME_UUID:-<VOLUME_UUID>}"
ROUTE_TABLES="${ROUTE_TABLES:-<ROUTE_TABLE_ID>,<ROUTE_TABLE_ID>}"
REGION="${AWS_REGION:-ap-northeast-1}"

# UC short name → directory mapping
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
        *) echo "$1" ;;
    esac
}

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

    # UC-specific param arrays
    local EXTRA_PARAMS=()

    # All UCs with EnableVpcEndpoints need it set to false AND S3GatewayEndpoint disabled
    # (route tables already have S3 prefix list from UC6 infrastructure)
    case "$UC" in
        legal-compliance)
            EXTRA_PARAMS+=(
                "S3AccessPointOutputAlias=${S3_AP_ALIAS}"
                "VolumeUuid=${VOLUME_UUID}"
                "PrivateRouteTableIds=${ROUTE_TABLES}"
                "EnableVpcEndpoints=false"
                "EnableS3GatewayEndpoint=false"
            )
            ;;
        financial-idp|manufacturing-analytics|healthcare-dicom)
            EXTRA_PARAMS+=(
                "S3AccessPointOutputAlias=${S3_AP_ALIAS}"
                "PrivateRouteTableIds=${ROUTE_TABLES}"
                "EnableVpcEndpoints=false"
                "EnableS3GatewayEndpoint=false"
            )
            ;;
        media-vfx)
            EXTRA_PARAMS+=(
                "S3AccessPointOutputAlias=${S3_AP_ALIAS}"
                "PrivateRouteTableIds=${ROUTE_TABLES}"
                "EnableVpcEndpoints=false"
                "EnableS3GatewayEndpoint=false"
                "DeadlineQueueId=dummy-queue-id"
                "DeadlineFarmId=dummy-farm-id"
            )
            ;;
        genomics-pipeline|energy-seismic)
            EXTRA_PARAMS+=(
                "EnableVpcEndpoints=false"
                "OutputBucketName="
                "GlueDatabaseName="
                "GlueTableName="
                "AthenaWorkgroupName="
            )
            ;;
        construction-bim|logistics-ocr|education-research)
            EXTRA_PARAMS+=(
                "EnableVpcEndpoints=false"
                "OutputBucketName="
            )
            ;;
        retail-catalog|insurance-claims)
            EXTRA_PARAMS+=(
                "EnableVpcEndpoints=false"
                "OutputBucketName="
            )
            ;;
        autonomous-driving)
            EXTRA_PARAMS+=(
                "EnableVpcEndpoints=false"
                "OutputBucketName="
                "ModelVariantsConfig=[]"
            )
            ;;
    esac

    aws cloudformation deploy \
        --template-file "$TEMPLATE" \
        --stack-name "$STACK" \
        --region "$REGION" \
        --s3-bucket "$DEPLOY_BUCKET" \
        --s3-prefix "cfn-templates/${UC}" \
        --parameter-overrides \
            DeployBucket="$DEPLOY_BUCKET" \
            S3AccessPointAlias="$S3_AP_ALIAS" \
            OntapSecretName="$ONTAP_SECRET_NAME" \
            OntapManagementIp="$ONTAP_MANAGEMENT_IP" \
            SvmUuid="$SVM_UUID" \
            VpcId="$VPC_ID" \
            PrivateSubnetIds="$SUBNETS" \
            NotificationEmail="$NOTIFICATION_EMAIL" \
            "${EXTRA_PARAMS[@]}" \
        --capabilities CAPABILITY_NAMED_IAM \
        --no-fail-on-empty-changeset 2>&1 | tail -3

    # Post-deploy: add S3 AP ARN inline policy to all discovery/processing roles
    echo "[$UC] Adding S3 AP ARN inline policy..."
    local POLICY_FILE="${PROJECT_DIR}/build/s3ap_inline_policy.json"
    if [[ ! -f "$POLICY_FILE" ]]; then
        mkdir -p "${PROJECT_DIR}/build"
        cat > "$POLICY_FILE" <<'POLICY_EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "S3APExtraAccess",
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket",
        "s3:GetObject",
        "s3:PutObject",
        "s3:GetBucketLocation"
      ],
      "Resource": [
        "arn:aws:s3:ap-northeast-1:<ACCOUNT_ID>:accesspoint/eda-demo-s3ap",
        "arn:aws:s3:ap-northeast-1:<ACCOUNT_ID>:accesspoint/eda-demo-s3ap/*"
      ]
    }
  ]
}
POLICY_EOF
    fi

    # Find all roles for this stack and attach policy
    for role in $(aws iam list-roles --region "$REGION" --query "Roles[?contains(RoleName, '${STACK}') && !contains(RoleName, 'sfn-role') && !contains(RoleName, 'scheduler-role')].RoleName" --output text 2>&1); do
        aws iam put-role-policy --role-name "$role" --policy-name S3APExtraAccess --policy-document "file://${POLICY_FILE}" 2>&1 | tail -1
    done

    echo "[$UC] ✅ Done"
}

if [[ $# -eq 0 ]]; then
    echo "Usage: $0 <UC1|legal-compliance> [UC2] [...]"
    exit 1
fi

for uc_input in "$@"; do
    deploy_one "$uc_input" &
done
wait

echo ""
echo "=== All deployments finished ==="
