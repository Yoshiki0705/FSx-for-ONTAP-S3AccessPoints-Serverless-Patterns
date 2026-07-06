#!/usr/bin/env bash
#
# sync-ivs-recording-to-fsx.sh
#
# Copies a completed IVS HLS recording package from the standard S3 recording bucket into
# FSx for ONTAP. Two methods are shown; pick ONE per your worker environment.
#
# Run AFTER the "Recording End" event (segments/manifests are not guaranteed complete before).
#
# Usage:
#   SRC_BUCKET=my-ivs-recordings \
#   RECORDING_PREFIX="ivs/v1/123456789012/AbCdef1G2hij/2020/6/23/20/12/EXAMPLE-recording-id" \
#   ./sync-ivs-recording-to-fsx.sh
#
# PoC-grade helper. For large packages / many segments prefer DataSync or an ECS/Batch worker.

set -euo pipefail

SRC_BUCKET="${SRC_BUCKET:-<YOUR_RECORDING_BUCKET_NAME>}"
RECORDING_PREFIX="${RECORDING_PREFIX:-ivs/v1/<ACCOUNT_ID>/<CHANNEL_ID>/<...>}"
AWS_REGION="${AWS_REGION:-ap-northeast-1}"

# Method A: write to FSx via an S3 Access Point alias (S3 API PutObject).
#   - Internet-origin AP: run this from a VPC-external host or via NAT.
FSX_S3AP_ALIAS="${FSX_S3AP_ALIAS:-<FSX_S3_ACCESS_POINT_ALIAS>}"

# Method B: write to FSx via an NFS/SMB mount (from ECS/Batch/EC2 with the volume mounted).
FSX_MOUNT_PATH="${FSX_MOUNT_PATH:-/mnt/fsxontap/vod}"

METHOD="${METHOD:-A}"   # A = S3 AP PutObject, B = NFS/SMB mount

if [[ "${SRC_BUCKET}" == "<YOUR_RECORDING_BUCKET_NAME>" ]]; then
  echo "ERROR: set SRC_BUCKET and RECORDING_PREFIX." >&2
  exit 1
fi

echo ">> Source: s3://${SRC_BUCKET}/${RECORDING_PREFIX}"

case "${METHOD}" in
  A)
    echo ">> Method A: S3 -> FSx via S3 Access Point PutObject (alias=${FSX_S3AP_ALIAS})"
    # aws s3 sync treats the AP alias like a bucket name for object operations.
    aws s3 sync \
      "s3://${SRC_BUCKET}/${RECORDING_PREFIX}/" \
      "s3://${FSX_S3AP_ALIAS}/${RECORDING_PREFIX}/" \
      --region "${AWS_REGION}"
    ;;
  B)
    echo ">> Method B: S3 -> local FSx mount (${FSX_MOUNT_PATH})"
    mkdir -p "${FSX_MOUNT_PATH}/${RECORDING_PREFIX}"
    aws s3 sync \
      "s3://${SRC_BUCKET}/${RECORDING_PREFIX}/" \
      "${FSX_MOUNT_PATH}/${RECORDING_PREFIX}/" \
      --region "${AWS_REGION}"
    ;;
  *)
    echo "ERROR: METHOD must be A (S3 AP) or B (NFS/SMB mount)." >&2
    exit 1
    ;;
esac

echo ">> Done. Verify the master .m3u8 manifest is present before publishing to CloudFront."
