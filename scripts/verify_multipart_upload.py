"""C-1: MultipartUpload 検証スクリプト — S3 AP での 5GB 超ファイルアップロード確認

FSx for ONTAP S3 AP が MultipartUpload (CreateMultipartUpload, UploadPart,
CompleteMultipartUpload) をサポートするか検証する。

AWS docs: MultipartUpload は S3 AP supported operations に含まれる。
最大オブジェクトサイズ: 5GB (S3 AP 制約)。
MultipartUpload 自体は 5GB 以下でも使用可能（大きなファイルの並列アップロード高速化）。

Usage:
    # 100MB テスト (安全)
    python3 scripts/verify_multipart_upload.py --size 100

    # 1GB テスト
    python3 scripts/verify_multipart_upload.py --size 1024

    # 5GB テスト (S3 AP 上限)
    python3 scripts/verify_multipart_upload.py --size 5120

Environment:
    S3AP_ALIAS: S3 Access Point alias
    AWS_REGION: Region (default: ap-northeast-1)
"""

from __future__ import annotations

import argparse
import logging
import os
import time

import boto3
from botocore.config import Config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

REGION = os.environ.get("AWS_REGION", "ap-northeast-1")
S3AP_ALIAS = os.environ.get("S3AP_ALIAS", "")
PART_SIZE = 50 * 1024 * 1024  # 50MB per part


def main():
    parser = argparse.ArgumentParser(description="C-1: MultipartUpload verification")
    parser.add_argument("--size", type=int, default=100, help="File size in MB (default: 100)")
    parser.add_argument("--key", default="p3_multipart_test.dat", help="S3 key for test file")
    parser.add_argument("--keep", action="store_true", help="Don't delete test file after")
    args = parser.parse_args()

    if not S3AP_ALIAS:
        logger.error("S3AP_ALIAS not set")
        return

    s3 = boto3.client(
        "s3",
        region_name=REGION,
        endpoint_url=f"https://s3.{REGION}.amazonaws.com",
        config=Config(signature_version="s3v4"),
    )

    total_bytes = args.size * 1024 * 1024
    num_parts = max(1, total_bytes // PART_SIZE)
    logger.info(f"Testing MultipartUpload: {args.size}MB → {num_parts} parts × {PART_SIZE // (1024 * 1024)}MB")
    logger.info(f"Target: {S3AP_ALIAS}/{args.key}")

    # Step 1: CreateMultipartUpload
    try:
        create_resp = s3.create_multipart_upload(Bucket=S3AP_ALIAS, Key=args.key)
        upload_id = create_resp["UploadId"]
        logger.info(f"✅ CreateMultipartUpload succeeded: UploadId={upload_id[:20]}...")
    except Exception as e:
        logger.error(f"❌ CreateMultipartUpload FAILED: {e}")
        logger.error("S3 AP may not support MultipartUpload — check ONTAP version")
        return

    # Step 2: UploadPart
    parts = []
    total_start = time.perf_counter()
    try:
        for i in range(num_parts):
            part_num = i + 1
            part_data = b"\x00" * min(PART_SIZE, total_bytes - i * PART_SIZE)

            start = time.perf_counter()
            part_resp = s3.upload_part(
                Bucket=S3AP_ALIAS,
                Key=args.key,
                UploadId=upload_id,
                PartNumber=part_num,
                Body=part_data,
            )
            elapsed = time.perf_counter() - start

            etag = part_resp["ETag"]
            parts.append({"PartNumber": part_num, "ETag": etag})
            throughput_mbps = len(part_data) / elapsed / (1024 * 1024)
            logger.info(
                f"  Part {part_num}/{num_parts}: {len(part_data) // (1024 * 1024)}MB in {elapsed:.1f}s ({throughput_mbps:.1f} MB/s)"
            )

        logger.info(f"✅ All {num_parts} UploadPart calls succeeded")
    except Exception as e:
        logger.error(f"❌ UploadPart FAILED at part {len(parts) + 1}: {e}")
        # Abort
        s3.abort_multipart_upload(Bucket=S3AP_ALIAS, Key=args.key, UploadId=upload_id)
        logger.info("Aborted multipart upload")
        return

    # Step 3: CompleteMultipartUpload
    try:
        complete_resp = s3.complete_multipart_upload(
            Bucket=S3AP_ALIAS,
            Key=args.key,
            UploadId=upload_id,
            MultipartUpload={"Parts": parts},
        )
        total_elapsed = time.perf_counter() - total_start
        logger.info("✅ CompleteMultipartUpload succeeded")
        logger.info(f"   Location: {complete_resp.get('Location', 'N/A')}")
        logger.info(f"   Total time: {total_elapsed:.1f}s")
        logger.info(f"   Throughput: {total_bytes / total_elapsed / (1024 * 1024):.1f} MB/s")
    except Exception as e:
        logger.error(f"❌ CompleteMultipartUpload FAILED: {e}")
        return

    # Step 4: Verify
    try:
        head_resp = s3.head_object(Bucket=S3AP_ALIAS, Key=args.key)
        actual_size = head_resp["ContentLength"]
        logger.info(f"✅ Verification: HeadObject reports {actual_size} bytes (expected {total_bytes})")
        if actual_size == total_bytes:
            logger.info("🎉 MultipartUpload fully verified on FSx for ONTAP S3 AP")
        else:
            logger.warning(f"⚠️ Size mismatch: expected {total_bytes}, got {actual_size}")
    except Exception as e:
        logger.error(f"❌ HeadObject verification failed: {e}")

    # Cleanup
    if not args.keep:
        try:
            s3.delete_object(Bucket=S3AP_ALIAS, Key=args.key)
            logger.info(f"Cleaned up: {args.key}")
        except Exception:
            pass


if __name__ == "__main__":
    main()
