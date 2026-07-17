#!/bin/bash
# ============================================================
# FSx for ONTAP Hands-on Lab — Post-Deployment Health Check
# ============================================================
# Verifies all components are operational after stack deployment.
# Run this after deploy.sh and setup_ontap.sh complete.
#
# Checks:
#   1. CloudFormation stack status
#   2. EC2 instance running + SSM online
#   3. FSx for ONTAP file system available
#   4. SVM lifecycle (AD join status)
#   5. S3 Access Point reachable (HeadBucket + ListObjects)
#   6. Managed AD status
#
# Usage:
#   ./scripts/verify_deployment.sh --stack-name fsx-ontap-handson
# ============================================================

set -euo pipefail

STACK_NAME=""
REGION="${AWS_REGION:-ap-northeast-1}"
PASS=0
FAIL=0
WARN=0

while [[ $# -gt 0 ]]; do
    case $1 in
        --stack-name) STACK_NAME="$2"; shift 2 ;;
        --region) REGION="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: $0 --stack-name <name> [--region REGION]"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

if [[ -z "$STACK_NAME" ]]; then
    echo "ERROR: --stack-name is required"
    exit 1
fi

check_pass() { echo "  ✅ $1"; ((PASS++)); }
check_fail() { echo "  ❌ $1"; ((FAIL++)); }
check_warn() { echo "  ⚠️  $1"; ((WARN++)); }

echo "============================================================"
echo " Post-Deployment Health Check"
echo "============================================================"
echo " Stack: $STACK_NAME"
echo " Region: $REGION"
echo " Time: $(date)"
echo "============================================================"
echo ""

# --- Get stack outputs ---
get_output() {
    aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" \
        --output text 2>/dev/null || echo ""
}

# --- 1. CloudFormation Stack ---
echo "=== 1. CloudFormation Stack ==="
STACK_STATUS=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query "Stacks[0].StackStatus" \
    --output text 2>/dev/null || echo "NOT_FOUND")

if [[ "$STACK_STATUS" == "CREATE_COMPLETE" || "$STACK_STATUS" == "UPDATE_COMPLETE" ]]; then
    check_pass "Stack status: $STACK_STATUS"
else
    check_fail "Stack status: $STACK_STATUS (expected CREATE_COMPLETE)"
fi
echo ""

# --- 2. EC2 Instance ---
echo "=== 2. EC2 Instance ==="
INSTANCE_ID=$(get_output "WindowsInstanceId")
if [[ -n "$INSTANCE_ID" && "$INSTANCE_ID" != "None" ]]; then
    INSTANCE_STATE=$(aws ec2 describe-instances \
        --instance-ids "$INSTANCE_ID" \
        --region "$REGION" \
        --query "Reservations[0].Instances[0].State.Name" \
        --output text 2>/dev/null || echo "unknown")

    if [[ "$INSTANCE_STATE" == "running" ]]; then
        check_pass "EC2 instance $INSTANCE_ID is running"
    else
        check_fail "EC2 instance state: $INSTANCE_STATE"
    fi

    # Check SSM connectivity
    SSM_STATUS=$(aws ssm describe-instance-information \
        --filters "Key=InstanceIds,Values=$INSTANCE_ID" \
        --region "$REGION" \
        --query "InstanceInformationList[0].PingStatus" \
        --output text 2>/dev/null || echo "unknown")

    if [[ "$SSM_STATUS" == "Online" ]]; then
        check_pass "SSM Agent online"
    else
        check_warn "SSM Agent status: $SSM_STATUS (may take 2-5 min after launch)"
    fi
else
    check_fail "Windows Instance ID not found in stack outputs"
fi
echo ""

# --- 3. FSx for ONTAP ---
echo "=== 3. FSx for ONTAP File System ==="
FS_ID=$(get_output "FileSystemId")
if [[ -n "$FS_ID" && "$FS_ID" != "None" ]]; then
    FS_LIFECYCLE=$(aws fsx describe-file-systems \
        --file-system-ids "$FS_ID" \
        --region "$REGION" \
        --query "FileSystems[0].Lifecycle" \
        --output text 2>/dev/null || echo "unknown")

    if [[ "$FS_LIFECYCLE" == "AVAILABLE" ]]; then
        check_pass "File system $FS_ID is AVAILABLE"
    else
        check_fail "File system lifecycle: $FS_LIFECYCLE"
    fi
else
    check_warn "File System ID not in outputs (may be using existing FSx)"
fi
echo ""

# --- 4. SVM AD Join ---
echo "=== 4. Storage Virtual Machine (AD Join) ==="
if [[ -n "$FS_ID" && "$FS_ID" != "None" ]]; then
    SVM_INFO=$(aws fsx describe-storage-virtual-machines \
        --filters "Name=file-system-id,Values=$FS_ID" \
        --region "$REGION" \
        --query "StorageVirtualMachines[0].[StorageVirtualMachineId,Lifecycle]" \
        --output text 2>/dev/null || echo "unknown unknown")
    SVM_ID=$(echo "$SVM_INFO" | awk '{print $1}')
    SVM_LIFECYCLE=$(echo "$SVM_INFO" | awk '{print $2}')

    if [[ "$SVM_LIFECYCLE" == "CREATED" ]]; then
        check_pass "SVM $SVM_ID lifecycle: CREATED (AD join successful)"
    elif [[ "$SVM_LIFECYCLE" == "MISCONFIGURED" ]]; then
        check_fail "SVM $SVM_ID is MISCONFIGURED (AD join failed — check DNS, OU path, credentials)"
    else
        check_warn "SVM lifecycle: $SVM_LIFECYCLE"
    fi
fi
echo ""

# --- 5. S3 Access Point ---
echo "=== 5. S3 Access Point ==="
S3AP_ALIAS=$(get_output "S3AccessPointAlias")
if [[ -n "$S3AP_ALIAS" && "$S3AP_ALIAS" != "None" ]]; then
    # HeadBucket check
    if aws s3api head-bucket --bucket "$S3AP_ALIAS" --region "$REGION" 2>/dev/null; then
        check_pass "S3 AP HeadBucket: OK (alias: $S3AP_ALIAS)"
    else
        check_warn "S3 AP HeadBucket failed (may need IAM permissions from this context)"
    fi

    # ListObjects check (more reliable — tests data plane)
    LIST_RESULT=$(aws s3 ls "s3://${S3AP_ALIAS}/" --region "$REGION" 2>&1 || echo "FAILED")
    if [[ "$LIST_RESULT" != *"FAILED"* && "$LIST_RESULT" != *"AccessDenied"* ]]; then
        check_pass "S3 AP ListObjects: OK"
    else
        check_warn "S3 AP ListObjects: $LIST_RESULT (run from EC2 with proper IAM role)"
    fi
else
    check_warn "S3 AP alias not in outputs (may not be deployed yet)"
fi
echo ""

# --- 6. Managed AD ---
echo "=== 6. AWS Managed AD ==="
DIR_ID=$(get_output "DirectoryId")
if [[ -n "$DIR_ID" && "$DIR_ID" != "None" ]]; then
    DIR_STATUS=$(aws ds describe-directories \
        --directory-ids "$DIR_ID" \
        --region "$REGION" \
        --query "DirectoryDescriptions[0].Stage" \
        --output text 2>/dev/null || echo "unknown")

    if [[ "$DIR_STATUS" == "Active" ]]; then
        check_pass "Managed AD $DIR_ID is Active"
    else
        check_fail "Managed AD status: $DIR_STATUS"
    fi
else
    check_warn "Directory ID not in outputs"
fi
echo ""

# --- Summary ---
echo "============================================================"
echo " Health Check Summary"
echo "============================================================"
echo "  ✅ Passed: $PASS"
echo "  ❌ Failed: $FAIL"
echo "  ⚠️  Warnings: $WARN"
echo ""

if [[ $FAIL -eq 0 ]]; then
    echo "  Status: READY FOR HANDS-ON"
    echo ""
    echo "  Next steps:"
    echo "    1. Access EC2 via Fleet Manager"
    echo "    2. Run map_drives.ps1 on desktop"
    echo "    3. Follow docs/handson_guide.md"
else
    echo "  Status: ISSUES DETECTED — review failures above"
    echo ""
    echo "  Common fixes:"
    echo "    - SVM MISCONFIGURED: Check AD credentials, OU path, DNS"
    echo "    - SSM offline: Wait 5 min, check VPC Endpoints / NAT GW"
    echo "    - S3 AP failed: Verify SVM AD join completed first"
fi
echo "============================================================"

exit $FAIL
