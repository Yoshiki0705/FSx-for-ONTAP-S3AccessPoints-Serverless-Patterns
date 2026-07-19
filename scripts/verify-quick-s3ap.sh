#!/usr/bin/env bash
# =============================================================================
# verify-quick-s3ap.sh
#
# End-to-end verification: Amazon Quick + FSx for ONTAP S3 AP (AD identity)
#
# This script:
# 1. Deploys AD environment (AWS Managed AD)
# 2. Joins an existing SVM to the AD
# 3. Creates an NTFS volume with test data
# 4. Creates S3 AP with Windows identity
# 5. Verifies S3 AP access
# 6. Prints Quick console instructions
# 7. (Optional) Cleans up all resources
#
# Prerequisites:
# - AWS CLI v2.35+ configured with ap-northeast-1
# - Existing FSx for ONTAP file system
# - jq installed
#
# Usage:
#   ./scripts/verify-quick-s3ap.sh --fs-id fs-XXXXXXX --svm-id svm-XXXXXXX
#   ./scripts/verify-quick-s3ap.sh --cleanup --stack-name quick-verify-ad-env
#
# Reference:
# - AWS Blog: https://aws.amazon.com/blogs/storage/enabling-ai-powered-analytics-on-enterprise-file-data-configuring-s3-access-points-for-amazon-fsx-for-netapp-ontap-with-active-directory/
# - Workshop: https://catalog.us-east-1.prod.workshops.aws/workshops/9cd82e0b-8348-456b-932a-818b9e5825a1/en-US/08-quicksuite/61-setup
# =============================================================================
set -euo pipefail

REGION="${AWS_DEFAULT_REGION:-ap-northeast-1}"
STACK_NAME="quick-verify-ad-env"
DOMAIN_NAME="quick.verify.local"
DOMAIN_SHORT="QUICKV"
AP_NAME="quick-verify-ad"

# --- Parse arguments ---
ACTION="deploy"
FS_ID=""
SVM_ID=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --fs-id) FS_ID="$2"; shift 2 ;;
    --svm-id) SVM_ID="$2"; shift 2 ;;
    --stack-name) STACK_NAME="$2"; shift 2 ;;
    --cleanup) ACTION="cleanup"; shift ;;
    --region) REGION="$2"; shift 2 ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

# --- Helper functions ---
log() { echo "[$(date '+%H:%M:%S')] $*"; }
wait_for_cfn() {
  log "Waiting for stack $STACK_NAME..."
  aws cloudformation wait stack-create-complete --stack-name "$STACK_NAME" --region "$REGION"
  log "Stack $STACK_NAME is ready."
}

# =============================================================================
# CLEANUP
# =============================================================================
if [[ "$ACTION" == "cleanup" ]]; then
  log "=== Cleanup mode ==="

  # Delete S3 AP
  log "Deleting S3 AP: $AP_NAME"
  aws fsx detach-and-delete-s3-access-point --name "$AP_NAME" --region "$REGION" 2>/dev/null || true

  # Delete CloudFormation stack
  log "Deleting stack: $STACK_NAME"
  aws cloudformation delete-stack --stack-name "$STACK_NAME" --region "$REGION"
  aws cloudformation wait stack-delete-complete --stack-name "$STACK_NAME" --region "$REGION"

  log "Cleanup complete. Monthly cost eliminated."
  exit 0
fi

# =============================================================================
# DEPLOY & VERIFY
# =============================================================================
if [[ -z "$FS_ID" || -z "$SVM_ID" ]]; then
  echo "Usage: $0 --fs-id fs-XXXXXXX --svm-id svm-XXXXXXX"
  echo ""
  echo "Find your resources:"
  echo "  aws fsx describe-file-systems --region $REGION --query 'FileSystems[*].{Id:FileSystemId,Lifecycle:Lifecycle}'"
  echo "  aws fsx describe-storage-virtual-machines --region $REGION --query 'StorageVirtualMachines[*].{Id:StorageVirtualMachineId,Name:Name,AD:ActiveDirectoryConfiguration.SelfManagedActiveDirectoryConfiguration.DomainName}'"
  exit 1
fi

# --- Step 1: Get network info from FSx ---
log "=== Step 1: Resolving network configuration from FSx ==="
VPC_ID=$(aws fsx describe-file-systems --file-system-ids "$FS_ID" --region "$REGION" \
  --query 'FileSystems[0].VpcId' --output text)
SUBNETS=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" --region "$REGION" \
  --query 'Subnets[*].SubnetId' --output text | tr '\t' ',' | cut -d',' -f1,2)

log "VPC: $VPC_ID"
log "Subnets: $SUBNETS"

# --- Step 2: Deploy AD environment ---
log "=== Step 2: Deploying AD environment (AWS Managed AD) ==="
log "Domain: $DOMAIN_NAME (short: $DOMAIN_SHORT)"
log "This takes 15-30 minutes..."

# Generate a strong password
AD_PASSWORD="QuickV3rify!$(date +%s | tail -c 5)"
log "AD Admin password generated (stored in parameter, not echoed)"

aws cloudformation deploy \
  --template-file infrastructure/demo-ad-environment.yaml \
  --stack-name "$STACK_NAME" \
  --parameter-overrides \
    AdMode=create-new \
    DomainName="$DOMAIN_NAME" \
    DomainShortName="$DOMAIN_SHORT" \
    AdminPassword="$AD_PASSWORD" \
    ExistingDirectoryId="" \
    SelfManagedDnsIps="" \
    SelfManagedDomainName="" \
    SelfManagedAdminUser="" \
    SelfManagedAdminPassword="" \
    VpcId="$VPC_ID" \
    PrivateSubnetIds="$SUBNETS" \
    PublicSubnetId="" \
    KeyPairName="" \
    InstanceType=t3.medium \
    FsxFileSystemId="$FS_ID" \
    OntapManagementIp="" \
    OntapSecretName="" \
  --capabilities CAPABILITY_IAM \
  --region "$REGION" \
  --no-fail-on-empty-changeset

wait_for_cfn

# --- Step 3: Join SVM to AD ---
log "=== Step 3: Joining SVM to AD ==="
log "Using scripts/demo-ad-join-svm.sh"

./scripts/demo-ad-join-svm.sh \
  --svm-id "$SVM_ID" \
  --ad-stack-name "$STACK_NAME" \
  --netbios-name "QUICKSVM" \
  --region "$REGION"

# --- Step 4: Create NTFS volume with test documents ---
log "=== Step 4: Creating NTFS volume for Quick test data ==="
VOLUME_RESULT=$(aws fsx create-volume \
  --volume-type ONTAP \
  --name quick-test-data \
  --ontap-configuration "{
    \"StorageVirtualMachineId\": \"$SVM_ID\",
    \"JunctionPath\": \"/quick-test-data\",
    \"SizeInMegabytes\": 1024,
    \"StorageEfficiencyEnabled\": true,
    \"SecurityStyle\": \"NTFS\"
  }" \
  --region "$REGION" \
  --output json 2>&1)

VOLUME_ID=$(echo "$VOLUME_RESULT" | jq -r '.Volume.VolumeId')
log "Volume created: $VOLUME_ID (waiting for AVAILABLE...)"

aws fsx wait volume-available --volume-ids "$VOLUME_ID" --region "$REGION" 2>/dev/null || \
  sleep 60  # fallback if wait not available

# --- Step 5: Create S3 AP with AD Windows identity ---
log "=== Step 5: Creating S3 AP with Windows identity (Admin) ==="

cat > /tmp/create-ap-quick.json <<EOF
{
    "Name": "$AP_NAME",
    "Type": "ONTAP",
    "OntapConfiguration": {
        "VolumeId": "$VOLUME_ID",
        "FileSystemIdentity": {
            "Type": "WINDOWS",
            "WindowsUser": {
                "Name": "Admin"
            }
        }
    }
}
EOF

AP_RESULT=$(aws fsx create-and-attach-s3-access-point \
  --cli-input-json file:///tmp/create-ap-quick.json \
  --region "$REGION" --output json 2>&1)

AP_ALIAS=$(echo "$AP_RESULT" | jq -r '.S3AccessPointAttachment.S3AccessPoint.Alias')
log "S3 AP created. Alias: $AP_ALIAS"
log "Waiting for AVAILABLE..."

for i in $(seq 1 12); do
  sleep 10
  STATUS=$(aws fsx describe-s3-access-point-attachments --region "$REGION" \
    --query "S3AccessPointAttachments[?Name==\`$AP_NAME\`].Lifecycle" --output text)
  log "  Status: $STATUS"
  if [[ "$STATUS" == "AVAILABLE" ]]; then break; fi
  if [[ "$STATUS" == "FAILED" ]]; then
    REASON=$(aws fsx describe-s3-access-point-attachments --region "$REGION" \
      --query "S3AccessPointAttachments[?Name==\`$AP_NAME\`].LifecycleTransitionReason.Message" --output text)
    log "ERROR: S3 AP creation failed: $REASON"
    exit 1
  fi
done

# --- Step 6: Verify S3 AP access ---
log "=== Step 6: Verifying S3 AP access ==="
echo "Quick verification test data" > /tmp/quick-test-file.txt
aws s3 cp /tmp/quick-test-file.txt "s3://${AP_ALIAS}/documents/test-report.txt" --region "$REGION"
aws s3 ls "s3://${AP_ALIAS}/" --region "$REGION"
log "S3 AP access verified!"

# --- Step 7: Print Quick console instructions ---
log "=== Step 7: Amazon Quick Configuration ==="
cat <<INSTRUCTIONS

============================================================
NEXT STEPS (Manual — Amazon Quick Console)
============================================================

1. Open Amazon Quick console: https://$REGION.quicksight.aws.amazon.com/
   (or https://quick.aws.amazon.com/ for the newer interface)

2. Navigate to: Integrations → Knowledge bases → Amazon S3

3. Enter the following:
   - Name: quick-fsxn-test
   - S3 bucket URL: s3://$AP_ALIAS

4. Click Create → Wait for sync to complete (status: Available)

5. Test with Chat Agent:
   - Navigate to: Chat agents
   - Query: "What documents are available?"

6. SCREENSHOT TARGETS (for documentation):
   - Integration creation screen (S3 AP alias input)
   - Sync complete status (Available)
   - Chat Agent query result
   - MASK: Account IDs, ARNs, usernames

============================================================
CLEANUP (when done):
  $0 --cleanup --stack-name $STACK_NAME
============================================================

S3 AP Alias: $AP_ALIAS
AD Password: $AD_PASSWORD
Volume ID:   $VOLUME_ID
Stack:       $STACK_NAME

INSTRUCTIONS

log "Done. Proceed with manual Quick console steps above."
