#!/bin/bash
# =============================================================================
# KNFSD File Cache — Pre-flight Check
#
# Run this BEFORE terraform apply to validate your environment.
# Checks: FSx for ONTAP reachability, AMI existence, subnet config, NFS export.
#
# Usage:
#   ./scripts/preflight-check.sh [terraform.tfvars]
#
# Exit codes:
#   0 = All checks pass, ready to deploy
#   1 = One or more checks failed (see output for details)
# =============================================================================
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "  ${GREEN}✓${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; FAILURES=$((FAILURES + 1)); }
warn() { echo -e "  ${YELLOW}⚠${NC} $1"; }
FAILURES=0

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  KNFSD File Cache — Pre-flight Validation                    ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Parse tfvars if provided
TFVARS="${1:-terraform.tfvars}"
if [[ ! -f "$TFVARS" ]]; then
  fail "terraform.tfvars not found. Copy terraform.tfvars.example first."
  echo ""
  echo "  cp terraform.tfvars.example terraform.tfvars"
  echo "  # Edit values, then re-run this script"
  exit 1
fi
pass "terraform.tfvars found"

# Extract values from tfvars (simple grep, not full HCL parser)
get_var() { grep "^${1}" "$TFVARS" 2>/dev/null | head -1 | sed 's/.*=.*"\(.*\)".*/\1/' | tr -d ' '; }
REGION=$(get_var aws_region)
AMI_ID=$(get_var knfsd_ami_id)
VPC_ID=$(get_var vpc_id)
NFS_VERSION=$(get_var nfs_version)

echo ""
echo "── 1. AWS CLI & Credentials ──"
if aws sts get-caller-identity --region "${REGION:-ap-northeast-1}" > /dev/null 2>&1; then
  ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
  pass "AWS credentials valid (account: $ACCOUNT)"
else
  fail "AWS credentials not configured or expired"
fi

echo ""
echo "── 2. AMI Check ──"
if [[ -n "$AMI_ID" && "$AMI_ID" != "ami-0123"* ]]; then
  AMI_STATE=$(aws ec2 describe-images --image-ids "$AMI_ID" --query 'Images[0].State' --output text --region "${REGION}" 2>/dev/null || echo "NOT_FOUND")
  if [[ "$AMI_STATE" == "available" ]]; then
    AMI_NAME=$(aws ec2 describe-images --image-ids "$AMI_ID" --query 'Images[0].Name' --output text --region "${REGION}")
    pass "AMI $AMI_ID is available ($AMI_NAME)"
  else
    fail "AMI $AMI_ID not found or not available (state: $AMI_STATE)"
    echo "       Build AMI first: ./scripts/setup.sh --knfsd-repo /path/to/knfsd-file-cache --region $REGION"
  fi
else
  fail "knfsd_ami_id is placeholder — set to your built AMI ID"
fi

echo ""
echo "── 3. Network ──"
if [[ -n "$VPC_ID" && "$VPC_ID" != "vpc-0123"* ]]; then
  VPC_STATE=$(aws ec2 describe-vpcs --vpc-ids "$VPC_ID" --query 'Vpcs[0].State' --output text --region "${REGION}" 2>/dev/null || echo "NOT_FOUND")
  if [[ "$VPC_STATE" == "available" ]]; then
    pass "VPC $VPC_ID exists"
  else
    fail "VPC $VPC_ID not found"
  fi
else
  fail "vpc_id is placeholder — set to your VPC ID"
fi

# Check subnet
SUBNET_ID=$(grep "subnet_ids" "$TFVARS" | grep -oP 'subnet-[a-f0-9]+' | head -1)
if [[ -n "$SUBNET_ID" && "$SUBNET_ID" != "subnet-0123"* ]]; then
  SUBNET_AZ=$(aws ec2 describe-subnets --subnet-ids "$SUBNET_ID" --query 'Subnets[0].AvailabilityZone' --output text --region "${REGION}" 2>/dev/null || echo "NOT_FOUND")
  if [[ "$SUBNET_AZ" != "NOT_FOUND" ]]; then
    pass "Subnet $SUBNET_ID in $SUBNET_AZ"
    # Check if subnet has route to internet (NAT or IGW)
    RT_ID=$(aws ec2 describe-route-tables --filters "Name=association.subnet-id,Values=$SUBNET_ID" --query 'RouteTables[0].RouteTableId' --output text --region "${REGION}" 2>/dev/null)
    if [[ -n "$RT_ID" && "$RT_ID" != "None" ]]; then
      HAS_NAT=$(aws ec2 describe-route-tables --route-table-ids "$RT_ID" --query 'RouteTables[0].Routes[?NatGatewayId!=`null`]' --output text --region "${REGION}" 2>/dev/null)
      HAS_IGW=$(aws ec2 describe-route-tables --route-table-ids "$RT_ID" --query 'RouteTables[0].Routes[?GatewayId!=`null` && starts_with(GatewayId, `igw-`)]' --output text --region "${REGION}" 2>/dev/null)
      if [[ -n "$HAS_NAT" || -n "$HAS_IGW" ]]; then
        pass "Subnet has internet route (NAT or IGW)"
      else
        warn "No NAT/IGW route found — assign_public_ip=true is REQUIRED"
      fi
    fi
  else
    fail "Subnet $SUBNET_ID not found"
  fi
fi

echo ""
echo "── 4. FSx for ONTAP NFS Source ──"
NFS_HOST=$(grep -oP '\d+\.\d+\.\d+\.\d+' "$TFVARS" | head -1)
EXPORT_PATH=$(grep "export" "$TFVARS" | grep -oP '"/[^"]+' | head -1 | tr -d '"')
if [[ -n "$NFS_HOST" && "$NFS_HOST" != "10.0.1.50" ]]; then
  # Try showmount (requires nfs-common)
  if command -v showmount &> /dev/null; then
    if showmount -e "$NFS_HOST" > /dev/null 2>&1; then
      pass "NFS source $NFS_HOST is reachable (showmount OK)"
      if showmount -e "$NFS_HOST" 2>/dev/null | grep -q "${EXPORT_PATH:-/vol1}"; then
        pass "Export ${EXPORT_PATH:-/vol1} is available"
      else
        warn "Export ${EXPORT_PATH:-/vol1} not listed (may still work — check junction path)"
      fi
    else
      warn "Cannot reach $NFS_HOST via showmount (may be blocked by Security Group or not installed locally)"
    fi
  else
    warn "showmount not installed locally — skipping NFS reachability check"
  fi
else
  warn "NFS host IP appears to be placeholder — update source_mounts in terraform.tfvars"
fi

echo ""
echo "── 5. NFS Version ──"
if [[ "$NFS_VERSION" == "4.1" || "$NFS_VERSION" == "4.2" ]]; then
  pass "nfs_version=$NFS_VERSION (correct for FSx for ONTAP re-export)"
elif [[ "$NFS_VERSION" == "3" ]]; then
  fail "nfs_version=3 will cause Stale file handle on file creation with FSx for ONTAP"
  echo "       Set nfs_version = \"4.1\" (see GitHub Issue #40: filehandle size overflow)"
else
  warn "nfs_version=$NFS_VERSION (untested — recommend 4.1)"
fi

echo ""
echo "── 6. Terraform ──"
if command -v terraform &> /dev/null; then
  TF_VER=$(terraform version -json 2>/dev/null | python3 -c "import sys,json;print(json.load(sys.stdin)['terraform_version'])" 2>/dev/null || terraform version | head -1)
  pass "Terraform installed ($TF_VER)"
else
  fail "Terraform not found — install: https://developer.hashicorp.com/terraform/install"
fi

if command -v packer &> /dev/null; then
  pass "Packer installed (for AMI builds)"
else
  warn "Packer not found — needed only for AMI builds (skip if AMI already built)"
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
if [[ $FAILURES -eq 0 ]]; then
  echo -e "${GREEN}All checks passed! Ready to deploy.${NC}"
  echo ""
  echo "  terraform init && terraform apply"
  echo ""
  echo "After deploy (~3 min), verify:"
  echo "  ./scripts/validate.sh"
else
  echo -e "${RED}$FAILURES check(s) failed. Fix issues above before deploying.${NC}"
  exit 1
fi
