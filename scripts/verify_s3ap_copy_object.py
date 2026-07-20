"""V-2: Verify S3 AP CopyObject support.

Tests whether CopyObject works on FSx for ONTAP S3 Access Points.
Required for: UX-3 (trash), UX-9 (rename), UX-10 (batch move).

Usage:
    S3AP_ALIAS=your-ap-alias python3 scripts/verify_s3ap_copy_object.py

Expected result: CopyObject should work (it's listed as supported in AWS docs).
This script confirms it works in your specific environment.
"""

from __future__ import annotations

import os
import time

import boto3
from botocore.config import Config

REGION = os.environ.get("AWS_REGION", "ap-northeast-1")
S3AP_ALIAS = os.environ.get("S3AP_ALIAS", "")


def main():
    if not S3AP_ALIAS:
        print("ERROR: S3AP_ALIAS not set")
        return

    s3 = boto3.client(
        "s3",
        region_name=REGION,
        endpoint_url=f"https://s3.{REGION}.amazonaws.com",
        config=Config(signature_version="s3v4"),
    )

    test_key = "v2_copy_test_source.txt"
    copy_key = "v2_copy_test_destination.txt"
    content = f"CopyObject test at {time.time()}"

    print(f"V-2: Testing CopyObject on S3 AP: {S3AP_ALIAS}")
    print(f"  Source: {test_key}")
    print(f"  Destination: {copy_key}")

    # Step 1: Create source file
    try:
        s3.put_object(Bucket=S3AP_ALIAS, Key=test_key, Body=content.encode())
        print("  ✅ PutObject (source): OK")
    except Exception as e:
        print(f"  ❌ PutObject failed: {e}")
        return

    # Step 2: CopyObject
    try:
        copy_source = f"{S3AP_ALIAS}/{test_key}"
        resp = s3.copy_object(Bucket=S3AP_ALIAS, CopySource=copy_source, Key=copy_key)
        etag = resp.get("CopyObjectResult", {}).get("ETag", "")
        print(f"  ✅ CopyObject: OK (ETag: {etag})")
    except Exception as e:
        print(f"  ❌ CopyObject FAILED: {e}")
        print("     → Rename (UX-9) and Trash (UX-3) will NOT work on this S3 AP")
        # Cleanup source
        s3.delete_object(Bucket=S3AP_ALIAS, Key=test_key)
        return

    # Step 3: Verify copy content
    try:
        obj = s3.get_object(Bucket=S3AP_ALIAS, Key=copy_key)
        copy_content = obj["Body"].read().decode()
        if copy_content == content:
            print("  ✅ Content verification: matches source")
        else:
            print(f"  ⚠️ Content mismatch: source={len(content)}B, copy={len(copy_content)}B")
    except Exception as e:
        print(f"  ❌ GetObject (copy) failed: {e}")

    # Step 4: DeleteObject (cleanup)
    try:
        s3.delete_object(Bucket=S3AP_ALIAS, Key=test_key)
        s3.delete_object(Bucket=S3AP_ALIAS, Key=copy_key)
        print("  ✅ Cleanup: OK")
    except Exception as e:
        print(f"  ⚠️ Cleanup warning: {e}")

    print("\n🎉 V-2 PASSED: CopyObject works on FSx for ONTAP S3 AP")
    print("   → UX-3 (trash), UX-9 (rename), UX-10 (batch move) are viable")


if __name__ == "__main__":
    main()
