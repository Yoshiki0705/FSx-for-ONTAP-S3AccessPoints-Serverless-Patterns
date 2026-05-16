"""S3AP + ONTAP Health Check Canary — CloudWatch Synthetics SDK 互換版.

CloudWatch Synthetics ランタイム (syn-python-selenium-11.0) で動作する
ヘルスチェック Canary。aws_synthetics SDK を使用してテスト結果を報告する。

チェック項目:
1. S3 Access Point への ListObjectsV2
2. S3 Access Point への GetObject（ヘルスマーカーファイル）
3. ONTAP REST API /api/cluster ヘルスチェック
"""

import json
import os
import time

import boto3
import urllib3

# Disable SSL warnings for ONTAP self-signed certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def handler(event, context):
    """Synthetics Canary handler.

    CloudWatch Synthetics は handler の戻り値を使用しない。
    テスト結果は print/logging で報告する。
    例外を raise するとテストが FAILED になる。
    """
    s3ap_alias = os.environ.get("S3AP_ALIAS", "")
    health_prefix = os.environ.get("HEALTH_PREFIX", "_health/")
    health_key = os.environ.get("HEALTH_MARKER_KEY", "_health/marker.txt")
    ontap_ip = os.environ.get("ONTAP_MGMT_IP", "")
    secret_name = os.environ.get("ONTAP_CREDENTIALS_SECRET", "")

    results = []
    all_passed = True

    # Check 1: S3AP ListObjectsV2
    try:
        s3 = boto3.client("s3")
        start = time.time()
        s3.list_objects_v2(Bucket=s3ap_alias, Prefix=health_prefix, MaxKeys=1)
        latency = (time.time() - start) * 1000
        results.append(f"S3AP_List: PASSED ({latency:.0f}ms)")
        print(f"PASSED: S3AP ListObjectsV2 - {latency:.0f}ms")
    except Exception as e:
        results.append(f"S3AP_List: FAILED ({e})")
        print(f"FAILED: S3AP ListObjectsV2 - {e}")
        all_passed = False

    # Check 2: S3AP GetObject
    try:
        start = time.time()
        resp = s3.get_object(Bucket=s3ap_alias, Key=health_key)
        resp["Body"].read()
        resp["Body"].close()
        latency = (time.time() - start) * 1000
        results.append(f"S3AP_Get: PASSED ({latency:.0f}ms)")
        print(f"PASSED: S3AP GetObject - {latency:.0f}ms")
    except Exception as e:
        results.append(f"S3AP_Get: FAILED ({e})")
        print(f"FAILED: S3AP GetObject - {e}")
        all_passed = False

    # Check 3: ONTAP Health
    if ontap_ip and secret_name:
        try:
            sm = boto3.client("secretsmanager")
            secret = json.loads(
                sm.get_secret_value(SecretId=secret_name)["SecretString"]
            )
            http = urllib3.PoolManager(cert_reqs="CERT_NONE")
            headers = urllib3.make_headers(
                basic_auth=f"{secret.get('username', 'fsxadmin')}:{secret['password']}"
            )
            start = time.time()
            resp = http.request(
                "GET",
                f"https://{ontap_ip}/api/cluster",
                headers=headers,
                timeout=urllib3.Timeout(connect=5.0, read=10.0),
            )
            latency = (time.time() - start) * 1000
            if resp.status == 200:
                results.append(f"ONTAP_Health: PASSED ({latency:.0f}ms)")
                print(f"PASSED: ONTAP Health - {latency:.0f}ms")
            else:
                results.append(f"ONTAP_Health: FAILED (HTTP {resp.status})")
                print(f"FAILED: ONTAP Health - HTTP {resp.status}")
                all_passed = False
        except Exception as e:
            results.append(f"ONTAP_Health: FAILED ({e})")
            print(f"FAILED: ONTAP Health - {e}")
            all_passed = False

    # Emit CloudWatch metrics
    try:
        cw = boto3.client("cloudwatch")
        cw.put_metric_data(
            Namespace="FSxN-S3AP-Patterns",
            MetricData=[
                {
                    "MetricName": "CanaryHealthCheck",
                    "Value": 1.0 if all_passed else 0.0,
                    "Unit": "Count",
                }
            ],
        )
    except Exception:
        pass

    # Summary
    print(f"\n{'='*50}")
    print(f"Overall: {'PASSED' if all_passed else 'FAILED'}")
    for r in results:
        print(f"  {r}")
    print(f"{'='*50}")

    # Raise exception if any check failed — this marks the Canary as FAILED
    if not all_passed:
        raise Exception(
            f"Health check failed: {[r for r in results if 'FAILED' in r]}"
        )
