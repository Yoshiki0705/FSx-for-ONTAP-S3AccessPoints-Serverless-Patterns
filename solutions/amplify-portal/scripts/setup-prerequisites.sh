#!/usr/bin/env bash
# =============================================================================
# FSx for ONTAP File Portal — Prerequisites Setup
# =============================================================================
# This script validates and displays the values needed for portal-config.ts.
# Run this BEFORE `npm start` to confirm your environment is ready.
#
# Prerequisites:
#   - AWS CLI v2 configured with appropriate credentials
#   - An existing FSx for ONTAP file system (or use DemoMode)
#   - Node.js 18+ and npm
#
# Usage:
#   ./scripts/setup-prerequisites.sh
#   ./scripts/setup-prerequisites.sh --fs-id fs-0123456789abcdef0
# =============================================================================

set -euo pipefail
cd "$(dirname "$0")/.."

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "================================================================="
echo " FSx for ONTAP File Portal — Prerequisites Check"
echo "================================================================="
echo ""

# Parse arguments
FS_ID="${1:-}"
if [[ "$FS_ID" == "--fs-id" ]]; then
  FS_ID="${2:-}"
fi

# Check AWS CLI
if ! command -v aws &> /dev/null; then
  echo -e "${RED}ERROR: AWS CLI not found. Install: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html${NC}"
  exit 1
fi
echo -e "${GREEN}✔${NC} AWS CLI found: $(aws --version | head -1)"

# Check Node.js
if ! command -v node &> /dev/null; then
  echo -e "${RED}ERROR: Node.js not found. Install: https://nodejs.org/${NC}"
  exit 1
fi
NODE_VER=$(node --version)
echo -e "${GREEN}✔${NC} Node.js found: $NODE_VER"

# Check npm dependencies
if [ ! -d "node_modules" ]; then
  echo -e "${YELLOW}⚠${NC}  node_modules not found. Running npm install..."
  npm install
fi
echo -e "${GREEN}✔${NC} npm dependencies installed"

# Check AWS credentials
AWS_IDENTITY=$(aws sts get-caller-identity --output json 2>/dev/null || echo "FAILED")
if [[ "$AWS_IDENTITY" == "FAILED" ]]; then
  echo -e "${RED}ERROR: AWS credentials not configured. Run: aws configure${NC}"
  exit 1
fi
AWS_ACCOUNT=$(echo "$AWS_IDENTITY" | python3 -c "import sys,json;print(json.load(sys.stdin)['Account'])")
AWS_REGION=$(aws configure get region 2>/dev/null || echo "ap-northeast-1")
echo -e "${GREEN}✔${NC} AWS Account: $AWS_ACCOUNT (Region: $AWS_REGION)"

echo ""
echo "================================================================="
echo " Configuration Values for portal-config.ts"
echo "================================================================="
echo ""

# If FS_ID provided, discover values automatically
if [[ -n "$FS_ID" ]]; then
  echo "Discovering values from FSx file system: $FS_ID ..."
  echo ""

  # Get management IP and VPC info
  FS_INFO=$(aws fsx describe-file-systems --file-system-ids "$FS_ID" \
    --query "FileSystems[0].{VpcId:VpcId,SubnetIds:SubnetIds,MgmtIP:OntapConfiguration.Endpoints.Management.IpAddresses[0]}" \
    --output json 2>/dev/null || echo "FAILED")

  if [[ "$FS_INFO" == "FAILED" ]]; then
    echo -e "${RED}ERROR: Could not describe file system $FS_ID. Check permissions and region.${NC}"
    exit 1
  fi

  VPC_ID=$(echo "$FS_INFO" | python3 -c "import sys,json;print(json.load(sys.stdin)['VpcId'])")
  MGMT_IP=$(echo "$FS_INFO" | python3 -c "import sys,json;print(json.load(sys.stdin)['MgmtIP'])")
  SUBNET_ID=$(echo "$FS_INFO" | python3 -c "import sys,json;print(json.load(sys.stdin)['SubnetIds'][0])")

  # Get Security Group from FSx ENIs
  SG_ID=$(aws ec2 describe-network-interfaces \
    --filters "Name=description,Values=*FSx*${FS_ID}*" \
    --query "NetworkInterfaces[0].Groups[0].GroupId" --output text 2>/dev/null || echo "UNKNOWN")

  # Get SVM name
  SVM_NAME=$(aws fsx describe-storage-virtual-machines \
    --filters "Name=file-system-id,Values=$FS_ID" \
    --query "StorageVirtualMachines[0].Name" --output text 2>/dev/null || echo "UNKNOWN")

  echo -e "${GREEN}Discovered values:${NC}"
  echo ""
  echo "  ontapMgmtIp:         \"$MGMT_IP\""
  echo "  ontapSvmName:        \"$SVM_NAME\""
  echo "  vpcId:               \"$VPC_ID\""
  echo "  vpcSubnetIds:        [\"$SUBNET_ID\"]"
  echo "  vpcSecurityGroupIds: [\"$SG_ID\"]"
  echo ""
  echo -e "${YELLOW}Still needed (manual):${NC}"
  echo "  ontapSecretName:     \"<secrets-manager-secret-name>\""
  echo "  ontapVolumeName:     \"<default-volume-name>\""
  echo "  s3ApAlias:           \"<s3-access-point-alias>\""

else
  echo -e "${YELLOW}No --fs-id provided. Showing manual setup instructions.${NC}"
  echo ""
  echo "To auto-discover values, run:"
  echo "  ./scripts/setup-prerequisites.sh --fs-id fs-0123456789abcdef0"
  echo ""
  echo "Or fill in portal-config.ts manually:"
  echo ""
  echo "  1. cp amplify/portal-config.example.ts amplify/portal-config.ts"
  echo "  2. Edit the following values:"
  echo ""
  echo "     # Required for file browsing (works without VPC):"
  echo "     s3ApAlias: \"<your-s3ap-alias-from-fsx-console>\""
  echo ""
  echo "     # Required for admin/data-protection features:"
  echo "     vpcId: \"<vpc-id-where-fsx-enis-reside>\""
  echo "     vpcSubnetIds: [\"<subnet-id>\"]"
  echo "     vpcSecurityGroupIds: [\"<security-group-id>\"]"
  echo "     ontapMgmtIp: \"<management-lif-ip>\""
  echo "     ontapSecretName: \"<secrets-manager-secret>\""
  echo "     ontapSvmName: \"<svm-name>\""
  echo "     ontapVolumeName: \"<default-volume>\""
fi

echo ""
echo "================================================================="
echo " DemoMode (no FSx for ONTAP required)"
echo "================================================================="
echo ""
echo "To try the portal WITHOUT FSx for ONTAP:"
echo "  1. cp amplify/portal-config.example.ts amplify/portal-config.ts"
echo "  2. Set s3ApAlias to a regular S3 bucket name (or leave empty)"
echo "  3. Leave VPC/ONTAP fields empty"
echo "  4. Run: npm start"
echo ""
echo "File browsing works with any S3 bucket. Admin features show"
echo "\"ONTAP Connection Required\" gracefully."
echo ""
echo "================================================================="
echo " Next Steps"
echo "================================================================="
echo ""
echo "  1. cp amplify/portal-config.example.ts amplify/portal-config.ts"
echo "  2. Fill in the values above"
echo "  3. npm start"
echo "  4. Open http://localhost:5173"
echo ""
echo -e "${GREEN}Done!${NC}"
