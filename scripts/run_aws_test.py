#!/usr/bin/env python3
"""AWS 実環境テスト — S3ApHelper + FsxHelper"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("AWS_DEFAULT_REGION", "ap-northeast-1")

S3_AP = os.environ.get("S3_ACCESS_POINT", "")
FS_ID = os.environ.get("FSX_FILESYSTEM_ID", "")

from shared.s3ap_helper import S3ApHelper
from shared.fsx_helper import FsxHelper

print("=== Test 1: S3ApHelper ListObjectsV2 ===")
helper = S3ApHelper(S3_AP)
objects = helper.list_objects(max_keys=10)
print(f"ListObjectsV2: {len(objects)} objects found")
for obj in objects[:5]:
    print(f"  Key={obj['Key']}, Size={obj['Size']}")

if objects:
    print("\n=== Test 2: S3ApHelper HeadObject ===")
    head = helper.head_object(objects[0]["Key"])
    print(f"HeadObject: ContentLength={head.get('ContentLength')}, ContentType={head.get('ContentType')}")

print("\n=== Test 3: FsxHelper describe_file_systems ===")
fsx = FsxHelper()
filesystems = fsx.describe_file_systems(filesystem_ids=[FS_ID])
print(f"describe_file_systems: {len(filesystems)} filesystem(s)")
for fs in filesystems:
    print(f"  ID={fs['FileSystemId']}, Type={fs['FileSystemType']}, Lifecycle={fs['Lifecycle']}")

print("\n=== Test 4: FsxHelper describe_volumes ===")
volumes = fsx.describe_volumes(filters=[{"Name": "file-system-id", "Values": [FS_ID]}])
print(f"describe_volumes: {len(volumes)} volume(s)")
for vol in volumes:
    print(f"  ID={vol['VolumeId']}, Name={vol.get('Name','N/A')}, Lifecycle={vol['Lifecycle']}")

print("\n=== Test 5: S3ApHelper PutObject + GetObject round-trip ===")
test_key = "_test/verification_test.txt"
test_body = "FSxN S3AP Serverless Patterns - verification test"
helper.put_object(key=test_key, body=test_body, content_type="text/plain")
print(f"PutObject: {test_key}")
get_resp = helper.get_object(test_key)
retrieved = get_resp["Body"].read().decode("utf-8")
assert retrieved == test_body, f"Round-trip failed: expected '{test_body}', got '{retrieved}'"
print(f"GetObject: verified content matches")
helper.delete_object(test_key)
print(f"DeleteObject: {test_key} cleaned up")

print("\n=== ALL AWS ENVIRONMENT TESTS PASSED ===")
