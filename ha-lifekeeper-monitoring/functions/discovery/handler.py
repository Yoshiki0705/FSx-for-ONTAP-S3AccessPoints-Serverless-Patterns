"""HA LifeKeeper Monitoring — Discovery Lambda

FSx for ONTAP S3 Access Point 経由で SIOS LifeKeeper のログファイル、
フェイルオーバーイベント、ヘルスチェック結果を検出する。

LifeKeeper は以下のログ/データをボリュームに出力する:
- /var/log/lifekeeper.log — メインイベントログ
- /var/log/lifekeeper/ — 詳細ログディレクトリ
- /opt/LifeKeeper/config/ — クラスタ構成
- カスタムリカバリキットログ（SAP, Oracle 等）

Environment Variables:
    S3_ACCESS_POINT_ALIAS: S3 AP Alias (入力読み取り用)
    FILE_PREFIX: スキャン対象プレフィックス (例: "lifekeeper/logs/")
    MAX_FILES: 1 回の実行あたりの最大ファイル数 (デフォルト: 50)
    CLUSTER_NAME: LifeKeeper クラスタ名
    DEMO_MODE: デモモード ("true"/"false")
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

s3_client = boto3.client("s3")

# LifeKeeper 関連ファイルパターン
LIFEKEEPER_PATTERNS = {
    "log": {".log", ".log.gz", ".log.1", ".log.2"},
    "config": {".conf", ".cfg", ".xml"},
    "event": {".evt", ".json", ".csv"},
    "health": {".status", ".health", ".chk"},
}

# LifeKeeper イベントキーワード（ファイル名/パスベースの分類）
FAILOVER_KEYWORDS = {"failover", "switchover", "takeover", "recovery", "fault", "alarm"}
HEALTH_KEYWORDS = {"health", "heartbeat", "status", "check", "monitor", "canary"}
CONFIG_KEYWORDS = {"config", "resource", "hierarchy", "dependency"}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Discovery Lambda ハンドラー

    S3 AP 経由で LifeKeeper ログファイルを検出し、カテゴリ分類する。
    フェイルオーバーイベントを優先的に検出する。
    """
    s3ap_alias = os.environ.get("S3_ACCESS_POINT_ALIAS", "")
    prefix = os.environ.get("FILE_PREFIX", "lifekeeper/logs/")
    max_files = int(os.environ.get("MAX_FILES", "50"))
    cluster_name = os.environ.get("CLUSTER_NAME", "lifekeeper-cluster")

    logger.info(
        "LifeKeeper Discovery: alias=%s, prefix=%s, max=%d, cluster=%s",
        s3ap_alias,
        prefix,
        max_files,
        cluster_name,
    )

    objects = []
    failover_events = []
    continuation_token = None

    try:
        while len(objects) < max_files:
            kwargs: dict[str, Any] = {
                "Bucket": s3ap_alias,
                "Prefix": prefix,
                "MaxKeys": min(1000, max_files - len(objects)),
            }
            if continuation_token:
                kwargs["ContinuationToken"] = continuation_token

            response = s3_client.list_objects_v2(**kwargs)

            for obj in response.get("Contents", []):
                key = obj["Key"]
                category = _categorize_lifekeeper_file(key)
                severity = _assess_severity(key, category)

                file_entry = {
                    "key": key,
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat()
                    if hasattr(obj["LastModified"], "isoformat")
                    else str(obj["LastModified"]),
                    "category": category,
                    "severity": severity,
                    "cluster_name": cluster_name,
                }

                objects.append(file_entry)

                # フェイルオーバーイベントは別途集約
                if category == "failover_event":
                    failover_events.append(file_entry)

                if len(objects) >= max_files:
                    break

            if not response.get("IsTruncated"):
                break
            continuation_token = response.get("NextContinuationToken")

    except Exception as e:
        logger.error("LifeKeeper Discovery failed: %s", str(e))
        return {
            "status": "error",
            "error": str(e),
            "object_count": 0,
            "cluster_name": cluster_name,
        }

    # カテゴリ別サマリ
    category_summary = {}
    for obj in objects:
        cat = obj["category"]
        category_summary[cat] = category_summary.get(cat, 0) + 1

    logger.info(
        "Discovery completed: %d files, %d failover events, categories=%s",
        len(objects),
        len(failover_events),
        category_summary,
    )

    return {
        "status": "completed",
        "object_count": len(objects),
        "objects": objects,
        "failover_events": failover_events,
        "failover_event_count": len(failover_events),
        "category_summary": category_summary,
        "prefix": prefix,
        "cluster_name": cluster_name,
        "timestamp": int(time.time()),
    }


def _categorize_lifekeeper_file(key: str) -> str:
    """LifeKeeper ファイルをカテゴリに分類する"""
    key_lower = key.lower()

    # フェイルオーバー関連
    if any(kw in key_lower for kw in FAILOVER_KEYWORDS):
        return "failover_event"

    # ヘルスチェック関連
    if any(kw in key_lower for kw in HEALTH_KEYWORDS):
        return "health_check"

    # 通信ログ (config より先に判定 — "comm" が両方に該当するため)
    if "comm" in key_lower or "lcm" in key_lower or "tcp" in key_lower:
        return "communication_log"

    # 構成ファイル
    if any(kw in key_lower for kw in CONFIG_KEYWORDS):
        return "cluster_config"

    # リカバリキットログ (SAP, Oracle 等)
    if "sap" in key_lower or "oracle" in key_lower or "mysql" in key_lower:
        return "recovery_kit_log"

    # 一般ログ
    ext = os.path.splitext(key)[1].lower()
    if ext in LIFEKEEPER_PATTERNS["log"]:
        return "general_log"
    elif ext in LIFEKEEPER_PATTERNS["config"]:
        return "cluster_config"
    elif ext in LIFEKEEPER_PATTERNS["event"]:
        return "event_log"

    return "other"


def _assess_severity(key: str, category: str) -> str:
    """ファイルの重要度を評価する"""
    if category == "failover_event":
        return "CRITICAL"
    elif category == "health_check":
        key_lower = key.lower()
        if "fail" in key_lower or "error" in key_lower or "alarm" in key_lower:
            return "HIGH"
        return "MEDIUM"
    elif category == "recovery_kit_log":
        return "HIGH"
    elif category == "communication_log":
        key_lower = key.lower()
        if "timeout" in key_lower or "disconnect" in key_lower:
            return "HIGH"
        return "LOW"
    else:
        return "LOW"
