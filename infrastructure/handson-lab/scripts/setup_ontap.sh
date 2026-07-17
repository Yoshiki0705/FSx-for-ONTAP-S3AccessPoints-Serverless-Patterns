#!/bin/bash
# ============================================================
# FSx for ONTAP Post-Deployment Configuration
# ============================================================
# Configures ONTAP-specific settings that cannot be set via CloudFormation:
#   1. Enable Tamperproof Snapshot on the volume
#   2. Create initial snapshots (for hands-on demo)
#   3. Verify SMB share accessibility
#   4. Set up snapshot schedule
#
# Prerequisites:
#   - Stack deployment completed
#   - SSH access to ONTAP management IP (via EC2 or local)
#   - fsxadmin password available
#
# Usage:
#   ./scripts/setup_ontap.sh --stack-name <stack-name>
#   ./scripts/setup_ontap.sh --mgmt-ip <ip> --password <pass>
# ============================================================

set -euo pipefail

# --- Configuration ---
STACK_NAME=""
REGION="${AWS_REGION:-ap-northeast-1}"
MGMT_IP=""
FSXADMIN_PASSWORD=""
SVM_NAME="svm01"
VOLUME_NAME="user01"

# --- Parse arguments ---
while [[ $# -gt 0 ]]; do
    case $1 in
        --stack-name) STACK_NAME="$2"; shift 2 ;;
        --mgmt-ip) MGMT_IP="$2"; shift 2 ;;
        --password) FSXADMIN_PASSWORD="$2"; shift 2 ;;
        --svm) SVM_NAME="$2"; shift 2 ;;
        --volume) VOLUME_NAME="$2"; shift 2 ;;
        --region) REGION="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: $0 --stack-name <name> | --mgmt-ip <ip> --password <pass>"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# --- Resolve management IP from stack outputs ---
if [[ -n "$STACK_NAME" && -z "$MGMT_IP" ]]; then
    echo "Resolving ONTAP management IP from stack: $STACK_NAME"
    MGMT_IP=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query "Stacks[0].Outputs[?OutputKey=='OntapManagementIp'].OutputValue" \
        --output text)

    if [[ -z "$MGMT_IP" || "$MGMT_IP" == "None" ]]; then
        echo "ERROR: Could not resolve management IP from stack outputs"
        exit 1
    fi
    echo "  Management IP: $MGMT_IP"
fi

if [[ -z "$MGMT_IP" ]]; then
    echo "ERROR: --mgmt-ip or --stack-name is required"
    exit 1
fi

# --- Resolve password from Secrets Manager ---
if [[ -z "$FSXADMIN_PASSWORD" && -n "$STACK_NAME" ]]; then
    # Try to get the secret ARN from parameters
    echo "Retrieving fsxadmin password from Secrets Manager..."
    SECRET_ARN=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query "Stacks[0].Parameters[?ParameterKey=='FsxAdminPasswordSecretArn'].ParameterValue" \
        --output text 2>/dev/null || echo "")

    if [[ -n "$SECRET_ARN" && "$SECRET_ARN" != "None" ]]; then
        FSXADMIN_PASSWORD=$(aws secretsmanager get-secret-value \
            --secret-id "$SECRET_ARN" \
            --region "$REGION" \
            --query "SecretString" \
            --output text)
    fi
fi

if [[ -z "$FSXADMIN_PASSWORD" ]]; then
    echo "Enter fsxadmin password:"
    read -s FSXADMIN_PASSWORD
fi

echo ""
echo "============================================================"
echo " ONTAP Post-Deployment Configuration"
echo "============================================================"
echo " Management IP: $MGMT_IP"
echo " SVM:           $SVM_NAME"
echo " Volume:        $VOLUME_NAME"
echo "============================================================"
echo ""

# --- Helper function to run ONTAP CLI commands ---
run_ontap_cmd() {
    local cmd="$1"
    # Use sshpass for non-interactive SSH (install if needed)
    if command -v sshpass &>/dev/null; then
        sshpass -p "$FSXADMIN_PASSWORD" ssh -o StrictHostKeyChecking=no \
            -o UserKnownHostsFile=/dev/null \
            "fsxadmin@${MGMT_IP}" "$cmd" 2>/dev/null
    else
        echo "NOTE: sshpass not installed. Run commands manually:"
        echo "  ssh fsxadmin@${MGMT_IP}"
        echo "  Command: $cmd"
        echo ""
        return 1
    fi
}

# --- Step 1: Verify connectivity ---
echo "=== Step 1: Verifying ONTAP connectivity ==="
if run_ontap_cmd "version" 2>/dev/null; then
    echo "  Connected to ONTAP successfully"
else
    echo ""
    echo "  Cannot connect automatically. Please run the following commands manually:"
    echo ""
    echo "  ssh fsxadmin@${MGMT_IP}"
    echo "  Password: (from Secrets Manager)"
    echo ""
fi

# --- Step 2: Enable Tamperproof Snapshot ---
echo ""
echo "=== Step 2: Enable Tamperproof Snapshot ==="
echo ""
echo "Run these commands on the ONTAP CLI:"
echo ""
cat << EOF
# Disable page limit
rows 0

# Check current snapshot locking status
volume snapshot locking show -vserver $SVM_NAME -volume $VOLUME_NAME

# Enable Tamperproof Snapshot (minimum retention: 1 hour for demo)
volume snapshot locking modify -vserver $SVM_NAME -volume $VOLUME_NAME -is-enabled true -minimum-retention-period "1hours"

# Verify
volume snapshot locking show -vserver $SVM_NAME -volume $VOLUME_NAME
EOF

# Try automated execution
if command -v sshpass &>/dev/null; then
    echo ""
    echo "  Attempting automated configuration..."
    run_ontap_cmd "rows 0; volume snapshot locking modify -vserver $SVM_NAME -volume $VOLUME_NAME -is-enabled true -minimum-retention-period 1hours" || true
fi

# --- Step 3: Create Initial Snapshots ---
echo ""
echo "=== Step 3: Create Initial Snapshots (Tamperproof protected) ==="
echo ""
echo "Run these commands:"
echo ""
cat << EOF
# Create snapshots with Tamperproof retention
snapshot create -vserver $SVM_NAME -volume $VOLUME_NAME -snapshot tamperproof_demo_1 -snaplock-expiry-time "07/17/2026 00:00:00"
snapshot create -vserver $SVM_NAME -volume $VOLUME_NAME -snapshot tamperproof_demo_2 -snaplock-expiry-time "07/17/2026 00:00:00"

# Verify tamperproof status
snapshot show -vserver $SVM_NAME -volume $VOLUME_NAME -fields snaplock-expiry-time
EOF

if command -v sshpass &>/dev/null; then
    echo ""
    echo "  Attempting automated snapshot creation..."
    # Create snapshots with 24-hour tamperproof retention
    EXPIRY=$(date -v+1d "+%m/%d/%Y %H:%M:%S" 2>/dev/null || date -d "+1 day" "+%m/%d/%Y %H:%M:%S" 2>/dev/null || echo "")
    if [[ -n "$EXPIRY" ]]; then
        run_ontap_cmd "snapshot create -vserver $SVM_NAME -volume $VOLUME_NAME -snapshot tamperproof_demo_1 -snaplock-expiry-time \"$EXPIRY\"" || true
        run_ontap_cmd "snapshot create -vserver $SVM_NAME -volume $VOLUME_NAME -snapshot tamperproof_demo_2 -snaplock-expiry-time \"$EXPIRY\"" || true
    fi
fi

# --- Step 4: Verify SMB Share ---
echo ""
echo "=== Step 4: Verify SMB Share ==="
echo ""
echo "Run this command to verify the SMB share exists:"
echo ""
cat << EOF
cifs share show -vserver $SVM_NAME

# If share doesn't exist, create it:
cifs share create -share-name $VOLUME_NAME -path /$VOLUME_NAME -vserver $SVM_NAME
EOF

# --- Step 5: Verify Snapshot Policy ---
echo ""
echo "=== Step 5: Verify Snapshot Policy ==="
echo ""
cat << EOF
volume show -vserver $SVM_NAME -volume $VOLUME_NAME -fields snapshot-policy
snapshot policy show -policy default
EOF

echo ""
echo "============================================================"
echo " ONTAP Configuration Complete"
echo "============================================================"
echo ""
echo " Summary of manual steps (if sshpass not available):"
echo "  1. SSH to: fsxadmin@${MGMT_IP}"
echo "  2. Enable Tamperproof Snapshot"
echo "  3. Create demo snapshots with retention"
echo "  4. Verify SMB share"
echo ""
echo " The hands-on environment is ready for use after these steps."
echo "============================================================"
