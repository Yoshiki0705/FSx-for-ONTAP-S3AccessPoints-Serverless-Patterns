#!/usr/bin/env bash
# =============================================================================
# deploy.sh — One-command KNFSD File Cache deployment
#
# This script handles the full lifecycle:
#   1. Prerequisites check
#   2. AMI build (Packer) — skipped if AMI ID provided
#   3. Terraform init + plan + apply
#
# Usage:
#   ./scripts/deploy.sh                          # Full flow (build AMI + deploy)
#   ./scripts/deploy.sh --ami ami-0xxx           # Skip AMI build, use existing
#   ./scripts/deploy.sh --plan-only              # Only show plan, don't apply
#   ./scripts/deploy.sh --destroy                # Destroy all resources
#
# Required environment:
#   - terraform.tfvars must exist (copy from terraform.tfvars.example)
#   - AWS credentials configured
#   - For AMI build: KNFSD repo cloned at /tmp/knfsd-file-cache
# =============================================================================
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
readonly TF_DIR="$PROJECT_DIR/terraform"

# --- Defaults ---
AMI_ID=""
PLAN_ONLY=false
DESTROY=false
KNFSD_REPO="/tmp/knfsd-file-cache"
REGION="ap-northeast-1"
ARCH="arm64"

# --- Colors ---
if [[ -t 1 ]]; then
  readonly RED='\033[0;31m' GREEN='\033[0;32m' YELLOW='\033[0;33m'
  readonly BLUE='\033[0;34m' BOLD='\033[1m' NC='\033[0m'
else
  readonly RED='' GREEN='' YELLOW='' BLUE='' BOLD='' NC=''
fi

log_info()  { echo -e "${BLUE}[INFO]${NC} $*"; }
log_ok()    { echo -e "${GREEN}[  OK]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }
log_step()  { echo -e "\n${BOLD}━━━ $* ━━━${NC}"; }

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Options:
  --ami AMI_ID         Use existing AMI (skip Packer build)
  --plan-only          Show Terraform plan without applying
  --destroy            Destroy all KNFSD resources
  --knfsd-repo PATH    Path to KNFSD repo (default: /tmp/knfsd-file-cache)
  --region REGION      AWS region (default: ap-northeast-1)
  --arch ARCH          AMI architecture: arm64 or amd64 (default: arm64)
  --help               Show this help

Examples:
  # First deployment (builds AMI + deploys)
  git clone https://github.com/awslabs/knfsd-file-cache.git /tmp/knfsd-file-cache
  cp terraform/terraform.tfvars.example terraform/terraform.tfvars
  # Edit terraform.tfvars with your values
  ./scripts/deploy.sh

  # Re-deploy with existing AMI
  ./scripts/deploy.sh --ami ami-0123456789abcdef0

  # Destroy everything
  ./scripts/deploy.sh --destroy
EOF
  exit 0
}

# --- Parse Arguments ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    --ami)        AMI_ID="$2"; shift 2 ;;
    --plan-only)  PLAN_ONLY=true; shift ;;
    --destroy)    DESTROY=true; shift ;;
    --knfsd-repo) KNFSD_REPO="$2"; shift 2 ;;
    --region)     REGION="$2"; shift 2 ;;
    --arch)       ARCH="$2"; shift 2 ;;
    --help)       usage ;;
    *)            log_error "Unknown option: $1"; usage ;;
  esac
done

# =============================================================================
# Destroy mode
# =============================================================================
if [[ "$DESTROY" == "true" ]]; then
  log_step "Destroying KNFSD resources"
  cd "$TF_DIR"

  if [[ ! -f "terraform.tfstate" ]] && [[ ! -d ".terraform" ]]; then
    log_warn "No Terraform state found. Nothing to destroy."
    exit 0
  fi

  terraform destroy
  log_ok "All KNFSD resources destroyed"
  exit 0
fi

# =============================================================================
# Step 1: Prerequisites Check
# =============================================================================
log_step "Step 1: Prerequisites Check"

PREREQS_OK=true

check_cmd() {
  if command -v "$1" &>/dev/null; then
    log_ok "$1 → $(command -v "$1")"
  else
    log_error "$1 not found. Install: $2"
    PREREQS_OK=false
  fi
}

check_cmd terraform "brew install hashicorp/tap/terraform"
check_cmd packer    "brew install hashicorp/tap/packer"
check_cmd aws       "brew install awscli"
check_cmd jq        "brew install jq"

# AWS credentials
if aws sts get-caller-identity &>/dev/null; then
  ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
  log_ok "AWS credentials valid (Account: $ACCOUNT)"
else
  log_error "AWS credentials not configured"
  PREREQS_OK=false
fi

# terraform.tfvars
if [[ ! -f "$TF_DIR/terraform.tfvars" ]]; then
  log_error "terraform.tfvars not found"
  log_info "Create it: cp $TF_DIR/terraform.tfvars.example $TF_DIR/terraform.tfvars"
  log_info "Then edit with your VPC, subnet, and FSx for ONTAP details"
  PREREQS_OK=false
else
  log_ok "terraform.tfvars exists"
fi

if [[ "$PREREQS_OK" != "true" ]]; then
  log_error "Prerequisites check failed. Fix issues above and retry."
  exit 1
fi

# =============================================================================
# Step 2: AMI Build (Packer) — skip if --ami provided
# =============================================================================
if [[ -z "$AMI_ID" ]]; then
  log_step "Step 2: Building KNFSD AMI (Packer, ~25 min)"

  if [[ ! -d "$KNFSD_REPO/image" ]]; then
    log_error "KNFSD repo not found at $KNFSD_REPO"
    log_info "Clone it first: git clone https://github.com/awslabs/knfsd-file-cache.git $KNFSD_REPO"
    exit 1
  fi

  # Get subnet from tfvars for Packer
  SUBNET=$(grep 'subnet_ids' "$TF_DIR/terraform.tfvars" | grep -oP 'subnet-[a-z0-9]+' | head -1)
  if [[ -z "$SUBNET" ]]; then
    log_error "Could not extract subnet from terraform.tfvars"
    exit 1
  fi

  log_info "Building AMI: region=$REGION, arch=$ARCH, subnet=$SUBNET"
  log_info "This takes approximately 25 minutes (kernel compilation + NFS packages)."
  log_info "A Spot instance will be used for cost efficiency (~\$0.30)."
  echo ""

  cd "$KNFSD_REPO/image"
  packer init .
  packer build \
    -var "REGION=$REGION" \
    -var "SUBNET=$SUBNET" \
    -var "ARCH=[\"$ARCH\"]" \
    -var "ASSOCIATE_PUBLIC_IP_ADDRESS=true" \
    .

  # Extract AMI ID from the most recently created AMI
  AMI_ID=$(aws ec2 describe-images \
    --owners self \
    --filters "Name=name,Values=knfsd-proxy*$ARCH*" \
    --query 'Images | sort_by(@, &CreationDate) | [-1].ImageId' \
    --output text \
    --region "$REGION")

  if [[ -z "$AMI_ID" || "$AMI_ID" == "None" ]]; then
    log_error "Could not find built AMI. Check Packer output above."
    exit 1
  fi

  log_ok "AMI built: $AMI_ID"
  echo "$AMI_ID" > "$PROJECT_DIR/.ami-id"
else
  log_step "Step 2: Using existing AMI"
  log_ok "AMI: $AMI_ID (skipping Packer build)"
fi

# =============================================================================
# Step 3: Terraform Deploy
# =============================================================================
log_step "Step 3: Terraform Deploy"

cd "$TF_DIR"

# Inject AMI ID into tfvars if not already set
if grep -q 'knfsd_ami_id.*ami-0123' "$TF_DIR/terraform.tfvars" 2>/dev/null; then
  log_info "Updating knfsd_ami_id in terraform.tfvars → $AMI_ID"
  sed -i.bak "s/knfsd_ami_id.*=.*/knfsd_ami_id = \"$AMI_ID\"/" "$TF_DIR/terraform.tfvars"
  rm -f "$TF_DIR/terraform.tfvars.bak"
fi

terraform init -upgrade

log_info "Planning..."
terraform plan -out=tfplan

if [[ "$PLAN_ONLY" == "true" ]]; then
  log_ok "Plan complete. Review above. Run without --plan-only to apply."
  rm -f tfplan
  exit 0
fi

echo ""
log_info "Applying..."
terraform apply tfplan
rm -f tfplan

# =============================================================================
# Step 4: Output
# =============================================================================
log_step "Deployment Complete"

echo ""
terraform output
echo ""
log_ok "KNFSD File Cache is deploying."
log_info "proxy-startup.sh will configure NFS automatically on boot (~60 sec)."
log_info ""
log_info "Verify:"
log_info "  Instance ID: $(terraform output -json knfsd_instance_ids | jq -r '.[0]')"
log_info "  Private IP:  $(terraform output -json knfsd_private_ips | jq -r '.[0]')"
log_info ""
log_info "Mount from client:"
terraform output -json nfs_mount_commands | jq -r '.[]'
log_info ""
log_info "Cleanup: ./scripts/deploy.sh --destroy"
