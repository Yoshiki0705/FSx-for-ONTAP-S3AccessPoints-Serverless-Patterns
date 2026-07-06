#!/usr/bin/env bash
#
# create-ivs-recording-config.sh
#
# Creates an Amazon IVS Recording Configuration that Auto-Records to a STANDARD Amazon S3
# bucket (the documented, supported destination), then creates a channel attached to it.
#
# This is the RECOMMENDED path. For the experimental "record directly to an FSx for ONTAP
# S3 Access Point alias" test, see scripts/test-direct-fsx-s3ap-alias.sh.
#
# Usage:
#   RECORDING_BUCKET=my-ivs-recordings-bucket ./create-ivs-recording-config.sh
#
# Requirements: awscli v2, permissions for ivs:*RecordingConfiguration and ivs:*Channel.
# Note: channel, recording configuration, and S3 bucket must be in the SAME region.

set -euo pipefail

RECORDING_BUCKET="${RECORDING_BUCKET:-<YOUR_RECORDING_BUCKET_NAME>}"
CONFIG_NAME="${CONFIG_NAME:-ivs-fsx-vod-recording-config}"
CHANNEL_NAME="${CHANNEL_NAME:-ivs-fsx-vod-channel}"
AWS_REGION="${AWS_REGION:-ap-northeast-1}"

if [[ "${RECORDING_BUCKET}" == "<YOUR_RECORDING_BUCKET_NAME>" ]]; then
  echo "ERROR: set RECORDING_BUCKET to a standard S3 bucket name (same region as IVS)." >&2
  exit 1
fi

echo ">> Creating IVS Recording Configuration '${CONFIG_NAME}' -> s3://${RECORDING_BUCKET}"
RC_ARN=$(aws ivs create-recording-configuration \
  --region "${AWS_REGION}" \
  --name "${CONFIG_NAME}" \
  --recording-reconnect-window-seconds 60 \
  --destination-configuration "{\"s3\": {\"bucketName\": \"${RECORDING_BUCKET}\"}}" \
  --thumbnail-configuration 'recordingMode=INTERVAL,targetIntervalSeconds=30' \
  --query 'recordingConfiguration.arn' \
  --output text)

echo ">> RecordingConfiguration ARN: ${RC_ARN}"
echo ">> Waiting for RecordingConfiguration to become ACTIVE ..."
for _ in $(seq 1 30); do
  STATE=$(aws ivs get-recording-configuration --region "${AWS_REGION}" \
    --arn "${RC_ARN}" --query 'recordingConfiguration.state' --output text)
  echo "   state=${STATE}"
  [[ "${STATE}" == "ACTIVE" ]] && break
  [[ "${STATE}" == "CREATE_FAILED" ]] && { echo "ERROR: CREATE_FAILED" >&2; exit 2; }
  sleep 5
done

echo ">> Creating channel '${CHANNEL_NAME}' attached to the recording configuration"
aws ivs create-channel \
  --region "${AWS_REGION}" \
  --name "${CHANNEL_NAME}" \
  --recording-configuration-arn "${RC_ARN}" \
  --query '{channelArn: channel.arn, ingestEndpoint: channel.ingestEndpoint, playbackUrl: channel.playbackUrl}' \
  --output json

echo ">> Done. Stream to the ingest endpoint; recordings land under s3://${RECORDING_BUCKET}/ivs/v1/..."
