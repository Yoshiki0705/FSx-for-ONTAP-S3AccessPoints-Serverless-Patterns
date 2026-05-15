#!/usr/bin/env python3
"""
Persistent Store 設定スクリプト

ONTAP REST API を使用して FPolicy Persistent Store を設定する。
VPC 内の Lambda (IP Updater) 経由で ONTAP API を呼び出す。

前提条件:
- AWS CLI が設定済み
- fsxn-fpolicy-ip-updater Lambda がデプロイ済み
- ONTAP 9.14.1+ (Persistent Store サポート)

使用方法:
    python3 scripts/configure_persistent_store.py [--check|--create|--attach]
"""

import argparse
import json
import sys

import boto3

# Configuration
REGION = "ap-northeast-1"
LAMBDA_FUNCTION = "fsxn-fpolicy-ip-updater"
SVM_UUID = "9ae87e42-068a-11f1-b1ff-ada95e61ee66"
MGMT_IP = "10.0.3.72"
SECRET_NAME = "fsx-ontap-fsxadmin-credentials"

# Persistent Store settings
PERSISTENT_STORE_VOLUME = "fpolicy_persistent_store"
PERSISTENT_STORE_NAME = "fpolicy_aws_store"
POLICY_NAME = "fpolicy_aws"


def invoke_ontap_api(method: str, path: str, body: dict = None) -> dict:
    """Invoke ONTAP REST API via a custom Lambda payload.

    Since the IP Updater Lambda has VPC access and Secrets Manager access,
    we create a lightweight wrapper that can execute arbitrary ONTAP API calls.
    """
    # For this script, we'll use direct boto3 + urllib3 from local machine
    # through the VPC. Since we don't have direct access, we'll document
    # the commands and provide a Lambda-based approach.
    print(f"  [API] {method} {path}")
    if body:
        print(f"        Body: {json.dumps(body, indent=2)}")
    return {"status": "documented"}


def check_persistent_store():
    """Check if Persistent Store is already configured."""
    print("=" * 60)
    print("Persistent Store 状態確認")
    print("=" * 60)
    print()
    print("以下の ONTAP REST API コマンドで確認:")
    print()
    print(f"  GET /api/protocols/fpolicy/{SVM_UUID}/persistent-stores")
    print(f"  GET /api/protocols/fpolicy/{SVM_UUID}/policies/{POLICY_NAME}")
    print()
    print("Lambda 経由での確認コマンド:")
    print()
    print(f"""  aws lambda invoke \\
    --function-name {LAMBDA_FUNCTION} \\
    --payload '{{"action": "ontap_api", "method": "GET", "path": "/api/protocols/fpolicy/{SVM_UUID}/persistent-stores"}}' \\
    --cli-binary-format raw-in-base64-out \\
    --region {REGION} \\
    /tmp/ps-check.json && cat /tmp/ps-check.json""")


def create_persistent_store():
    """Create Persistent Store volume and store."""
    print("=" * 60)
    print("Persistent Store 作成手順")
    print("=" * 60)
    print()

    print("Step 1: Persistent Store 用ボリューム作成")
    print("-" * 40)
    print(f"""
curl -k -u fsxadmin:PASSWORD \\
  -X POST "https://{MGMT_IP}/api/storage/volumes" \\
  -H "Content-Type: application/json" \\
  -d '{{
    "name": "{PERSISTENT_STORE_VOLUME}",
    "svm": {{"uuid": "{SVM_UUID}"}},
    "size": "1073741824",
    "type": "rw",
    "nas": {{
      "path": "/{PERSISTENT_STORE_VOLUME}",
      "security_style": "unix"
    }},
    "guarantee": {{"type": "none"}},
    "comment": "FPolicy Persistent Store volume for event buffering"
  }}'
""")

    print("Step 2: Persistent Store 作成")
    print("-" * 40)
    print(f"""
curl -k -u fsxadmin:PASSWORD \\
  -X POST "https://{MGMT_IP}/api/protocols/fpolicy/{SVM_UUID}/persistent-stores" \\
  -H "Content-Type: application/json" \\
  -d '{{
    "name": "{PERSISTENT_STORE_NAME}",
    "volume": "{PERSISTENT_STORE_VOLUME}",
    "autoflush_enabled": true,
    "autoflush_interval": "PT120S"
  }}'
""")

    print("Step 3: FPolicy ポリシーに Persistent Store を関連付け")
    print("-" * 40)
    print(f"""
curl -k -u fsxadmin:PASSWORD \\
  -X PATCH "https://{MGMT_IP}/api/protocols/fpolicy/{SVM_UUID}/policies/{POLICY_NAME}" \\
  -H "Content-Type: application/json" \\
  -d '{{
    "persistent_store": "{PERSISTENT_STORE_NAME}"
  }}'
""")


def generate_lambda_extension():
    """Generate Lambda handler extension for ONTAP API access."""
    print("=" * 60)
    print("Lambda 拡張コード (IP Updater に追加)")
    print("=" * 60)
    print()
    print("以下のコードを handler.py の handler() 関数に追加:")
    print()
    code = '''
    # --- Persistent Store / ONTAP API extension ---
    action = event.get("action", "")

    if action == "ontap_api":
        method = event.get("method", "GET")
        api_path = event.get("path", "")
        api_body = event.get("body")

        # Get credentials
        secret_name = os.environ["FSXN_CREDENTIALS_SECRET"]
        sm_client = boto3.client("secretsmanager")
        secret_value = sm_client.get_secret_value(SecretId=secret_name)
        creds = json.loads(secret_value["SecretString"])

        http = urllib3.PoolManager(cert_reqs="CERT_NONE")
        mgmt_ip = os.environ["FSXN_MGMT_IP"]
        url = f"https://{mgmt_ip}{api_path}"
        headers = urllib3.make_headers(basic_auth=f"{creds[\\'username\\']}:{creds[\\'password\\']}")
        headers["Content-Type"] = "application/json"

        body = json.dumps(api_body).encode() if api_body else None
        resp = http.request(method, url, headers=headers, body=body)

        return {
            "statusCode": resp.status,
            "body": json.loads(resp.data.decode()) if resp.data else {},
        }

    if action == "configure_persistent_store":
        # Full automated Persistent Store setup
        # ... (implement steps 1-3 from create_persistent_store)
        pass
'''
    print(code)


def main():
    parser = argparse.ArgumentParser(description="FPolicy Persistent Store 設定")
    parser.add_argument(
        "command",
        choices=["check", "create", "lambda-extension"],
        default="check",
        nargs="?",
        help="実行するコマンド",
    )
    args = parser.parse_args()

    if args.command == "check":
        check_persistent_store()
    elif args.command == "create":
        create_persistent_store()
    elif args.command == "lambda-extension":
        generate_lambda_extension()


if __name__ == "__main__":
    main()
