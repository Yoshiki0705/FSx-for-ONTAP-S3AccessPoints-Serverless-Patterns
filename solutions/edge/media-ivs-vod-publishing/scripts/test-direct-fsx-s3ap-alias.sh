#!/usr/bin/env bash
#
# test-direct-fsx-s3ap-alias.sh
#
# EXPERIMENTAL: attempts to create an IVS Recording Configuration whose destination bucketName
# is an FSx for ONTAP S3 Access Point ALIAS. This is NOT documented by AWS as supported.
# The purpose is to OBSERVE and RECORD the behavior (success or failure) for evidence.
#
# See direct-recording-experiment.md for the full plan and how to label the result.
#
# Usage:
#   FSX_S3AP_ALIAS=<your-fsx-s3ap-alias> ./test-direct-fsx-s3ap-alias.sh
#
# WARNING: Do NOT conclude "Supported" from a success here. Label as "Experimental / observed
# in this test environment, not documented as officially supported."

set -euo pipefail

FSX_S3AP_ALIAS="${FSX_S3AP_ALIAS:-<FSX_S3_ACCESS_POINT_ALIAS>}"
CONFIG_NAME="${CONFIG_NAME:-ivs-fsx-s3ap-direct-test}"
AWS_REGION="${AWS_REGION:-ap-northeast-1}"

if [[ "${FSX_S3AP_ALIAS}" == "<FSX_S3_ACCESS_POINT_ALIAS>" ]]; then
  echo "ERROR: set FSX_S3AP_ALIAS to your FSx for ONTAP S3 Access Point alias." >&2
  exit 1
fi

echo ">> [EXPERIMENTAL] Creating RecordingConfiguration with FSx for ONTAP S3 AP alias as bucketName"
echo "   alias=${FSX_S3AP_ALIAS} region=${AWS_REGION}"

# Capture stdout+stderr; a failure here is a meaningful (and expected-possible) result.
set +e
RESULT=$(aws ivs create-recording-configuration \
  --region "${AWS_REGION}" \
  --name "${CONFIG_NAME}" \
  --destination-configuration "{\"s3\": {\"bucketName\": \"${FSX_S3AP_ALIAS}\"}}" \
  2>&1)
RC=$?
set -e

echo "----- create-recording-configuration output -----"
echo "${RESULT}"
echo "--------------------------------------------------"

if [[ ${RC} -ne 0 ]]; then
  echo ">> RESULT: create call returned non-zero (${RC})."
  echo ">> Record this failure reason as evidence (likely: bucket not found / ownership"
  echo "   validation / region mismatch / access denied on a bucket-level API)."
  echo ">> Conclusion candidate: 'Not supported (observed)'."
  exit 0
fi

RC_ARN=$(echo "${RESULT}" | python3 -c 'import sys,json; print(json.load(sys.stdin)["recordingConfiguration"]["arn"])')
echo ">> Created: ${RC_ARN}. Polling state ..."
for _ in $(seq 1 30); do
  STATE=$(aws ivs get-recording-configuration --region "${AWS_REGION}" \
    --arn "${RC_ARN}" --query 'recordingConfiguration.state' --output text)
  echo "   state=${STATE}"
  [[ "${STATE}" == "ACTIVE" || "${STATE}" == "CREATE_FAILED" ]] && break
  sleep 5
done

# This script tests config-creation validation ONLY. Auto-delete the RecordingConfiguration so
# nothing is left behind (safe to re-run). Set KEEP_RC=1 to keep it for a live-stream test.
if [[ "${KEEP_RC:-0}" != "1" ]]; then
  echo ">> Cleaning up (config-creation test only): deleting ${RC_ARN}"
  aws ivs delete-recording-configuration --region "${AWS_REGION}" --arn "${RC_ARN}" || true
fi

# Optional: confirm the ARN form is rejected on the 63-char bucketName limit (no resource created).
if [[ -n "${FSX_S3AP_ARN:-}" ]]; then
  echo ">> Confirming ARN form is rejected (expected ValidationException, 63-char limit)"
  set +e
  aws ivs create-recording-configuration --region "${AWS_REGION}" --name "${CONFIG_NAME}-arn" \
    --destination-configuration "{\"s3\": {\"bucketName\": \"${FSX_S3AP_ARN}\"}}" 2>&1 | tail -2
  set -e
fi

echo ">> Next steps for a full recording test (see direct-recording-experiment.md; KEEP_RC=1):"
echo "   1) Attach to a channel, stream briefly."
echo "   2) Watch EventBridge 'IVS Recording State Change' (Start/End/Failure)."
echo "   3) Check for ivs/v1/... objects on the FSx volume (via S3 AP or NFS/SMB)."
echo "   4) Review CloudTrail for the S3 APIs IVS/SLR invoked and any AccessDenied."
echo ">> Even if ACTIVE + recording works: label 'Experimental', NOT 'Supported'."
