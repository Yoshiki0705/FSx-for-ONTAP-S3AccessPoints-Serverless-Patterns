"""FlexCache Discovery Lambda

Route Decision の結果に基づいて最適な S3 AP を選択し、
オブジェクト一覧を取得する Discovery Lambda。
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

s3_client = boto3.client("s3")
lambda_client = boto3.client("lambda")


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """FlexCache Discovery Lambda ハンドラー

    Args:
        event: {
            "s3ap_alias": "override-alias (optional)",
            "prefix": "data/",
            "max_keys": 1000,
            "use_route_decision": true
        }

    Returns:
        dict: 検出されたオブジェクト一覧
    """
    logger.info("FlexCache discovery started: %s", json.dumps(event))

    prefix = event.get("prefix", os.environ.get("DEFAULT_PREFIX", ""))
    max_keys = event.get("max_keys", 1000)
    use_route_decision = event.get("use_route_decision", True)

    # S3 AP エイリアスの決定
    s3ap_alias = event.get("s3ap_alias")
    if not s3ap_alias and use_route_decision:
        s3ap_alias = _get_s3ap_from_route_decision(event)
    if not s3ap_alias:
        s3ap_alias = os.environ.get("S3_ACCESS_POINT_ALIAS", "")

    if not s3ap_alias:
        return {
            "status": "error",
            "error": "No S3 AP alias available",
            "timestamp": int(time.time()),
        }

    # S3 AP 経由でオブジェクト一覧取得
    objects = _list_objects(s3ap_alias, prefix, max_keys)

    result = {
        "status": "completed",
        "s3ap_alias": s3ap_alias,
        "prefix": prefix,
        "object_count": len(objects),
        "objects": objects,
        "timestamp": int(time.time()),
    }

    logger.info(
        "Discovery completed: %d objects found via %s",
        len(objects),
        s3ap_alias,
    )

    return result


def _get_s3ap_from_route_decision(event: dict) -> str | None:
    """Route Decision Lambda を呼び出して最適な S3 AP を取得"""
    route_function = os.environ.get("ROUTE_DECISION_FUNCTION", "")
    if not route_function:
        return None

    try:
        response = lambda_client.invoke(
            FunctionName=route_function,
            InvocationType="RequestResponse",
            Payload=json.dumps({
                "client_region": os.environ.get("AWS_REGION", "ap-northeast-1"),
                "strategy": event.get("routing_strategy", "latency_based"),
            }),
        )
        payload = json.loads(response["Payload"].read())
        s3ap_alias = payload.get("s3ap_alias")
        if s3ap_alias:
            logger.info("Route decision selected S3 AP: %s", s3ap_alias)
            return s3ap_alias
    except Exception as e:
        logger.warning("Route decision failed, using default: %s", str(e))

    return None


def _list_objects(s3ap_alias: str, prefix: str, max_keys: int) -> list[dict]:
    """S3 AP 経由でオブジェクト一覧を取得"""
    objects = []
    continuation_token = None

    try:
        while len(objects) < max_keys:
            kwargs = {
                "Bucket": s3ap_alias,
                "Prefix": prefix,
                "MaxKeys": min(1000, max_keys - len(objects)),
            }
            if continuation_token:
                kwargs["ContinuationToken"] = continuation_token

            response = s3_client.list_objects_v2(**kwargs)

            for obj in response.get("Contents", []):
                objects.append({
                    "key": obj["Key"],
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat(),
                })

            if not response.get("IsTruncated"):
                break
            continuation_token = response.get("NextContinuationToken")

    except Exception as e:
        logger.error("Failed to list objects from %s: %s", s3ap_alias, str(e))
        return []

    return objects
