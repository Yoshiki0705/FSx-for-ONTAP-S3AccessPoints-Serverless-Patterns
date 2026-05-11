#!/bin/bash
# Cleanup generic UC demo stacks
# Handles: Athena WorkGroup, versioned S3 buckets, VPC Endpoint SG rules, CloudFormation stacks
set +e

# Resolve AWS account ID from environment or STS (override via ACCOUNT_ID env var)
ACCOUNT_ID="${ACCOUNT_ID:-$(aws sts get-caller-identity --query 'Account' --output text 2>/dev/null)}"
if [ -z "$ACCOUNT_ID" ] || [ "$ACCOUNT_ID" = "<ACCOUNT_ID>" ]; then
    echo "ERROR: could not resolve AWS account ID. Set ACCOUNT_ID env var or configure AWS credentials." >&2
    exit 1
fi
REGION="${REGION:-ap-northeast-1}"
VPC_ENDPOINT_SG="${VPC_ENDPOINT_SG:-}"  # Optional: set to auto-revoke Lambda SG rules
echo "Cleanup target account: $ACCOUNT_ID, region: $REGION"

FAILED_RESOURCES=()

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
        *) echo "$1" ;;
    esac
}

empty_versioned_bucket() {
    local bucket="$1"
    # Check if bucket exists
    if ! aws s3api head-bucket --bucket "$bucket" --region "$REGION" 2>/dev/null; then
        return 0  # Bucket doesn't exist, nothing to do
    fi

    echo "  Emptying bucket: $bucket"

    # Remove current-version objects
    aws s3 rm "s3://${bucket}" --recursive --region "$REGION" 2>/dev/null

    # Delete versioned objects
    local versions
    versions=$(aws s3api list-object-versions --bucket "$bucket" --region "$REGION" \
        --output json --query '{Objects: Versions[].{Key:Key,VersionId:VersionId}}' 2>/dev/null)
    if [ -n "$versions" ] && [ "$versions" != '{"Objects": null}' ] && [ "$versions" != "null" ]; then
        aws s3api delete-objects --bucket "$bucket" --region "$REGION" \
            --delete "$versions" 2>/dev/null
    fi

    # Delete delete markers
    local markers
    markers=$(aws s3api list-object-versions --bucket "$bucket" --region "$REGION" \
        --output json --query '{Objects: DeleteMarkers[].{Key:Key,VersionId:VersionId}}' 2>/dev/null)
    if [ -n "$markers" ] && [ "$markers" != '{"Objects": null}' ] && [ "$markers" != "null" ]; then
        aws s3api delete-objects --bucket "$bucket" --region "$REGION" \
            --delete "$markers" 2>/dev/null
    fi

    # Remove bucket
    aws s3 rb "s3://${bucket}" --region "$REGION" 2>/dev/null
}

delete_athena_workgroup() {
    local workgroup="$1"
    # Check if workgroup exists
    if aws athena get-work-group --work-group "$workgroup" --region "$REGION" 2>/dev/null | grep -q "$workgroup"; then
        echo "  Deleting Athena WorkGroup: $workgroup (recursive)"
        aws athena delete-work-group --work-group "$workgroup" --recursive-delete-option --region "$REGION" 2>/dev/null
    fi
}

revoke_vpc_endpoint_sg_rule() {
    local lambda_sg="$1"
    if [ -z "$VPC_ENDPOINT_SG" ]; then
        return 0  # VPC_ENDPOINT_SG not set, skip
    fi
    echo "  Revoking VPC Endpoint SG rule for Lambda SG: $lambda_sg"
    aws ec2 revoke-security-group-ingress \
        --group-id "$VPC_ENDPOINT_SG" \
        --region "$REGION" \
        --ip-permissions "IpProtocol=tcp,FromPort=443,ToPort=443,UserIdGroupPairs=[{GroupId=$lambda_sg}]" 2>/dev/null
}

get_lambda_sg_from_stack() {
    local stack="$1"
    aws cloudformation describe-stack-resource \
        --stack-name "$stack" \
        --logical-resource-id LambdaSecurityGroup \
        --region "$REGION" \
        --query 'StackResourceDetail.PhysicalResourceId' \
        --output text 2>/dev/null
}

for input in "$@"; do
    UC=$(uc_to_dir "$input")
    STACK="fsxn-${UC}-demo"

    echo ""
    echo "=========================================="
    echo "  Cleaning up: $STACK ($input)"
    echo "=========================================="

    # Check if stack exists
    STACK_STATUS=$(aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" \
        --query 'Stacks[0].StackStatus' --output text 2>/dev/null)
    if [ -z "$STACK_STATUS" ] || [ "$STACK_STATUS" = "None" ]; then
        echo "  Stack not found (already deleted or never created). Skipping."
        continue
    fi
    echo "  Current status: $STACK_STATUS"

    # Step 1: Delete Athena WorkGroup (if exists) — prevents DELETE_FAILED
    WORKGROUP="${STACK}-workgroup"
    delete_athena_workgroup "$WORKGROUP"

    # Step 2: Empty output bucket (versioned)
    OUT_BUCKET="${STACK}-output-${ACCOUNT_ID}"
    empty_versioned_bucket "$OUT_BUCKET"

    # Step 3: Empty Athena results bucket (versioned)
    ATHENA_BUCKET="${STACK}-athena-results-${ACCOUNT_ID}"
    empty_versioned_bucket "$ATHENA_BUCKET"

    # Step 4: Revoke VPC Endpoint SG inbound rule (if VPC_ENDPOINT_SG is set)
    if [ -n "$VPC_ENDPOINT_SG" ]; then
        LAMBDA_SG=$(get_lambda_sg_from_stack "$STACK")
        if [ -n "$LAMBDA_SG" ] && [ "$LAMBDA_SG" != "None" ]; then
            revoke_vpc_endpoint_sg_rule "$LAMBDA_SG"
        fi
    fi

    # Step 5: Delete CloudFormation stack
    echo "  Deleting stack: $STACK"
    aws cloudformation delete-stack --stack-name "$STACK" --region "$REGION"

    if [ $? -ne 0 ]; then
        FAILED_RESOURCES+=("$STACK: delete-stack failed")
    else
        echo "  Delete initiated."
    fi
done

# Summary
echo ""
echo "=========================================="
echo "  Cleanup Summary"
echo "=========================================="
if [ ${#FAILED_RESOURCES[@]} -eq 0 ]; then
    echo "  All stacks: delete initiated successfully."
    echo "  Note: VPC Lambda ENI release may take 15-30 minutes."
    echo "  Monitor with: bash scripts/_check_cleanup_progress.sh"
else
    echo "  FAILED RESOURCES:"
    for r in "${FAILED_RESOURCES[@]}"; do
        echo "    ❌ $r"
    done
fi

echo ""
echo "  Post-cleanup checklist:"
echo "    □ Wait for DELETE_COMPLETE (15-30 min for VPC Lambda ENIs)"
echo "    □ Check for retained DynamoDB tables:"
echo "      aws dynamodb list-tables --region $REGION --query 'TableNames[?contains(@, \`fsxn-\`)]'"
echo "    □ If DELETE_FAILED, see: docs/operational-runbooks/cleanup-troubleshooting.md"
