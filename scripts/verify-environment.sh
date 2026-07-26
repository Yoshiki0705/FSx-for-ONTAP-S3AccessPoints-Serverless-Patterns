#!/usr/bin/env bash
# verify-environment.sh — Discover and verify all FSx for ONTAP resources for portal testing
#
# Usage:
#   ./scripts/verify-environment.sh              # Full discovery
#   ./scripts/verify-environment.sh --json       # JSON output (for automation)
#   ./scripts/verify-environment.sh --brief      # One-liner per resource
#
# Prerequisites:
#   - AWS CLI configured with ap-northeast-1 credentials
#   - jq installed
#
# Output:
#   Discovers: File Systems, SVMs, Volumes, S3 Access Points, Secrets Manager secrets
#   Reports: connectivity readiness for the Amplify portal

set -euo pipefail

REGION="${AWS_DEFAULT_REGION:-ap-northeast-1}"
FORMAT="${1:-full}"  # full, --json, --brief

echo "=============================================="
echo "FSx for ONTAP Environment Verification"
echo "Region: $REGION"
echo "Time: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "=============================================="
echo ""

# --- 1. File Systems ---
echo "=== 1. FSx for ONTAP File Systems ==="
FS_JSON=$(aws fsx describe-file-systems \
  --region "$REGION" \
  --query 'FileSystems[?FileSystemType==`ONTAP`].{Id:FileSystemId,Name:Tags[?Key==`Name`]|[0].Value,State:Lifecycle,StorageCapacity:StorageCapacity,ThroughputCapacity:OntapConfiguration.ThroughputCapacity,DeploymentType:OntapConfiguration.DeploymentType,OntapVersion:OntapConfiguration.EndpointIpAddressRange}' \
  --output json 2>/dev/null || echo "[]")

if [ "$FS_JSON" = "[]" ] || [ -z "$FS_JSON" ]; then
  echo "  ❌ No FSx for ONTAP file systems found in $REGION"
  exit 1
fi

echo "$FS_JSON" | jq -r '.[] | "  ✅ \(.Id) | \(.Name // "unnamed") | \(.State) | \(.StorageCapacity)GB | \(.ThroughputCapacity)MBps | \(.DeploymentType)"'
echo ""

# Get first file system ID for subsequent queries
FS_ID=$(echo "$FS_JSON" | jq -r '.[0].Id')
echo "  Using file system: $FS_ID"
echo ""

# --- 2. Storage Virtual Machines (SVMs) ---
echo "=== 2. Storage Virtual Machines (SVMs) ==="
SVM_JSON=$(aws fsx describe-storage-virtual-machines \
  --region "$REGION" \
  --filters "Name=file-system-id,Values=$FS_ID" \
  --query 'StorageVirtualMachines[].{Id:StorageVirtualMachineId,Name:Name,State:Lifecycle,Subtype:Subtype,MgmtEndpoint:Endpoints.Management.IpAddresses[0]}' \
  --output json 2>/dev/null || echo "[]")

if [ "$SVM_JSON" = "[]" ]; then
  echo "  ❌ No SVMs found"
else
  echo "$SVM_JSON" | jq -r '.[] | "  ✅ \(.Id) | \(.Name) | \(.State) | mgmt: \(.MgmtEndpoint // "N/A")"'
fi
echo ""

# Get SVM details for management IP
SVM_ID=$(echo "$SVM_JSON" | jq -r '.[0].Id')
SVM_NAME=$(echo "$SVM_JSON" | jq -r '.[0].Name')
MGMT_IP=$(echo "$SVM_JSON" | jq -r '.[0].MgmtEndpoint // empty')

# --- 3. Volumes ---
echo "=== 3. Volumes ==="
VOL_JSON=$(aws fsx describe-volumes \
  --region "$REGION" \
  --filters "Name=file-system-id,Values=$FS_ID" \
  --query 'Volumes[].{Id:VolumeId,Name:Name,State:Lifecycle,SizeBytes:OntapConfiguration.SizeInBytes,SecurityStyle:OntapConfiguration.SecurityStyle,JunctionPath:OntapConfiguration.JunctionPath,StorageVirtualMachineId:OntapConfiguration.StorageVirtualMachineId}' \
  --output json 2>/dev/null || echo "[]")

if [ "$VOL_JSON" = "[]" ]; then
  echo "  ❌ No volumes found"
else
  echo "$VOL_JSON" | jq -r '.[] | "  ✅ \(.Id) | \(.Name) | \(.State) | \((.SizeBytes // 0) / 1073741824 | floor)GiB | \(.SecurityStyle // "N/A") | \(.JunctionPath // "N/A")"'
fi
echo ""

# --- 4. S3 Access Points ---
echo "=== 4. S3 Access Points ==="
# FSx S3 APs are discovered via the FSx API
S3AP_JSON=$(aws fsx describe-s3-access-points \
  --region "$REGION" \
  --filters "Name=file-system-id,Values=$FS_ID" \
  --query 'S3AccessPoints[].{Alias:Alias,Name:Name,State:Lifecycle,VolumeId:OntapConfiguration.VolumeId,FileSystemIdentity:OntapConfiguration.FileSystemIdentity}' \
  --output json 2>/dev/null || echo "[]")

if [ "$S3AP_JSON" = "[]" ]; then
  echo "  ⚠️  No S3 Access Points found (create one with: aws fsx create-and-attach-s3-access-point)"
else
  echo "$S3AP_JSON" | jq -r '.[] | "  ✅ \(.Alias) | \(.Name // "unnamed") | \(.State) | volume: \(.VolumeId)"'
fi
echo ""

S3AP_ALIAS=$(echo "$S3AP_JSON" | jq -r '.[0].Alias // empty')

# --- 5. Secrets Manager (ONTAP credentials) ---
echo "=== 5. Secrets Manager (ONTAP credentials) ==="
SECRETS=$(aws secretsmanager list-secrets \
  --region "$REGION" \
  --filters "Key=name,Values=fsxn,ontap,fsx" \
  --query 'SecretList[].{Name:Name,ARN:ARN}' \
  --output json 2>/dev/null || echo "[]")

if [ "$SECRETS" = "[]" ]; then
  echo "  ⚠️  No ONTAP-related secrets found"
  echo "  Create one: aws secretsmanager create-secret --name fsxn/ontap-creds --secret-string '{\"username\":\"fsxadmin\",\"password\":\"YOUR_PASSWORD\"}'"
else
  echo "$SECRETS" | jq -r '.[] | "  ✅ \(.Name)"'
fi
SECRET_NAME=$(echo "$SECRETS" | jq -r '.[0].Name // empty')
echo ""

# --- 6. Management Endpoint Connectivity ---
echo "=== 6. Management Endpoint ==="
# Get file system management endpoint
FS_DETAIL=$(aws fsx describe-file-systems \
  --region "$REGION" \
  --file-system-ids "$FS_ID" \
  --query 'FileSystems[0].OntapConfiguration.Endpoints.Management.IpAddresses[0]' \
  --output text 2>/dev/null || echo "")

if [ -n "$FS_DETAIL" ] && [ "$FS_DETAIL" != "None" ]; then
  echo "  ✅ File System Management IP: $FS_DETAIL"
  FS_MGMT_IP="$FS_DETAIL"
else
  echo "  ⚠️  File system management endpoint not found"
  FS_MGMT_IP=""
fi

if [ -n "$MGMT_IP" ]; then
  echo "  ✅ SVM Management IP: $MGMT_IP"
else
  echo "  ⚠️  SVM management IP not available (SVM may not have management LIF)"
fi
echo ""

# --- 7. Amplify Portal Status ---
echo "=== 7. Amplify Portal ==="
AMPLIFY_DIR="solutions/amplify-portal"
if [ -f "$AMPLIFY_DIR/amplify/portal-config.ts" ]; then
  echo "  ✅ portal-config.ts exists"
  # Check if demoMode
  if grep -q "demoMode.*true" "$AMPLIFY_DIR/amplify/portal-config.ts" 2>/dev/null; then
    echo "  ⚠️  DemoMode is enabled (using regular S3 bucket, not S3 AP)"
  else
    echo "  ✅ Production mode (using S3 AP)"
  fi
else
  echo "  ⚠️  portal-config.ts not found (run: cp amplify/portal-config.example.ts amplify/portal-config.ts)"
fi
echo ""

# --- Summary ---
echo "=============================================="
echo "Summary — Portal Configuration Values"
echo "=============================================="
echo ""
echo "Copy these to portal-config.ts:"
echo ""
echo "  region: '$REGION'"
echo "  s3ApAlias: '${S3AP_ALIAS:-<create S3 AP first>}'"
echo "  ontapMgmtIp: '${FS_MGMT_IP:-${MGMT_IP:-<check VPC connectivity>}}'"
echo "  ontapSecretName: '${SECRET_NAME:-<create secret first>}'"
echo "  svmName: '${SVM_NAME:-<check SVMs>}'"
echo ""
echo "Lambda environment variables:"
echo ""
echo "  ONTAP_MGMT_IP=${FS_MGMT_IP:-${MGMT_IP:-}}"
echo "  ONTAP_SECRET_NAME=${SECRET_NAME:-}"
echo "  SVM_NAME=${SVM_NAME:-}"
echo "  VOLUME_NAME=$(echo "$VOL_JSON" | jq -r '.[0].Name // empty')"
echo "  S3_AP_ALIAS=${S3AP_ALIAS:-}"
echo ""

# --- Readiness Check ---
echo "=============================================="
echo "Readiness Check"
echo "=============================================="
READY=true

if [ -z "$FS_ID" ]; then echo "  ❌ No file system"; READY=false; fi
if [ -z "$SVM_ID" ]; then echo "  ❌ No SVM"; READY=false; fi
if [ "$VOL_JSON" = "[]" ]; then echo "  ❌ No volumes"; READY=false; fi
if [ -z "$S3AP_ALIAS" ]; then echo "  ⚠️  No S3 AP (portal file browsing requires this)"; fi
if [ -z "$SECRET_NAME" ]; then echo "  ⚠️  No ONTAP secret (admin features require this)"; fi
if [ -z "$FS_MGMT_IP" ] && [ -z "$MGMT_IP" ]; then echo "  ⚠️  No management IP (admin features require VPC connectivity)"; fi

if [ "$READY" = true ]; then
  echo ""
  echo "  ✅ Environment is ready for portal deployment"
  echo ""
  echo "Next steps:"
  echo "  1. cd solutions/amplify-portal"
  echo "  2. cp amplify/portal-config.example.ts amplify/portal-config.ts"
  echo "  3. Edit portal-config.ts with values above"
  echo "  4. make sandbox && make dev"
else
  echo ""
  echo "  ❌ Environment is not ready — resolve issues above first"
fi
echo ""
