#!/usr/bin/env python3
"""
protobuf メッセージキャプチャスクリプト

ONTAP FPolicy engine の format を protobuf に変更し、
実際のメッセージをキャプチャして解析する。

WARNING: このスクリプトは FPolicy engine の format を変更するため、
実行中のイベント処理に影響する。テスト環境でのみ実行すること。

使用方法:
    python3 scripts/capture_protobuf_message.py [--enable|--disable|--status]

前提条件:
    - fsxn-fpolicy-ip-updater Lambda がデプロイ済み
    - FPolicy Server が protobuf 自動検出モードで動作中
"""

import argparse
import json
import sys
import time

import boto3

REGION = "ap-northeast-1"
LAMBDA_FUNCTION = "fsxn-fpolicy-ip-updater"
SVM_UUID = "9ae87e42-068a-11f1-b1ff-ada95e61ee66"
ENGINE_NAME = "fpolicy_aws_engine"
POLICY_NAME = "fpolicy_aws"


def invoke_ontap_api(method: str, path: str, body: dict = None) -> dict:
    """Invoke ONTAP REST API via Lambda."""
    client = boto3.client("lambda", region_name=REGION)
    payload = {
        "action": "ontap_api",
        "method": method,
        "path": path,
    }
    if body:
        payload["body"] = body

    response = client.invoke(
        FunctionName=LAMBDA_FUNCTION,
        Payload=json.dumps(payload).encode(),
    )
    result = json.loads(response["Payload"].read().decode())
    return result


def get_engine_status():
    """Get current engine format setting."""
    result = invoke_ontap_api(
        "GET",
        f"/api/protocols/fpolicy/{SVM_UUID}/engines/{ENGINE_NAME}?fields=format",
    )
    print(json.dumps(result, indent=2))
    return result


def enable_protobuf():
    """Switch engine format to protobuf."""
    print("=" * 60)
    print("Switching FPolicy engine format to protobuf")
    print("=" * 60)

    # Step 1: Disable policy
    print("\n[1/3] Disabling FPolicy policy...")
    result = invoke_ontap_api(
        "PATCH",
        f"/api/protocols/fpolicy/{SVM_UUID}/policies/{POLICY_NAME}",
        {"enabled": False},
    )
    print(f"  Status: {result['statusCode']}")

    time.sleep(2)

    # Step 2: Change engine format
    print("\n[2/3] Changing engine format to protobuf...")
    result = invoke_ontap_api(
        "PATCH",
        f"/api/protocols/fpolicy/{SVM_UUID}/engines/{ENGINE_NAME}",
        {"format": "protobuf"},
    )
    print(f"  Status: {result['statusCode']}")
    if result["statusCode"] not in (200, 202):
        print(f"  Error: {result.get('body', {})}")
        print("\n  NOTE: 'format' field may not be supported via REST API.")
        print("  Use ONTAP CLI instead:")
        print(f"    vserver fpolicy policy external-engine modify \\")
        print(f"      -vserver FSxN_OnPre \\")
        print(f"      -engine-name {ENGINE_NAME} \\")
        print(f"      -format-for-engine-of-type protobuf")

    time.sleep(2)

    # Step 3: Re-enable policy
    print("\n[3/3] Re-enabling FPolicy policy...")
    result = invoke_ontap_api(
        "PATCH",
        f"/api/protocols/fpolicy/{SVM_UUID}/policies/{POLICY_NAME}",
        {"enabled": True, "priority": 1},
    )
    print(f"  Status: {result['statusCode']}")

    print("\n✅ Engine format changed to protobuf")
    print("   Monitor ECS logs for protobuf messages:")
    print("   aws logs tail /ecs/fsxn-fpolicy-server-fsxn-fp-srv --follow")


def disable_protobuf():
    """Switch engine format back to XML."""
    print("=" * 60)
    print("Switching FPolicy engine format back to XML")
    print("=" * 60)

    # Step 1: Disable policy
    print("\n[1/3] Disabling FPolicy policy...")
    result = invoke_ontap_api(
        "PATCH",
        f"/api/protocols/fpolicy/{SVM_UUID}/policies/{POLICY_NAME}",
        {"enabled": False},
    )
    print(f"  Status: {result['statusCode']}")

    time.sleep(2)

    # Step 2: Change engine format back to XML
    print("\n[2/3] Changing engine format to xml...")
    result = invoke_ontap_api(
        "PATCH",
        f"/api/protocols/fpolicy/{SVM_UUID}/engines/{ENGINE_NAME}",
        {"format": "xml"},
    )
    print(f"  Status: {result['statusCode']}")

    time.sleep(2)

    # Step 3: Re-enable policy
    print("\n[3/3] Re-enabling FPolicy policy...")
    result = invoke_ontap_api(
        "PATCH",
        f"/api/protocols/fpolicy/{SVM_UUID}/policies/{POLICY_NAME}",
        {"enabled": True, "priority": 1},
    )
    print(f"  Status: {result['statusCode']}")

    print("\n✅ Engine format reverted to XML")


def main():
    parser = argparse.ArgumentParser(description="protobuf メッセージキャプチャ")
    parser.add_argument(
        "command",
        choices=["status", "enable", "disable"],
        default="status",
        nargs="?",
    )
    args = parser.parse_args()

    if args.command == "status":
        get_engine_status()
    elif args.command == "enable":
        enable_protobuf()
    elif args.command == "disable":
        disable_protobuf()


if __name__ == "__main__":
    main()
