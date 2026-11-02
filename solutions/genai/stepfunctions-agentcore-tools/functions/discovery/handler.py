"""Discovery Lambda — Step Functions × AgentCore Gateway pattern.

FSx for ONTAP S3 Access Point 経由でファイルを検出し、後続の Map 処理に渡す
Manifest（オブジェクト一覧）を生成する。AgentCore Gateway の Step Functions コネクタ
から起動されたワークフローの最初の Task。

S3 AP アクセスは shared.s3ap_helper.S3ApHelper に集約する（boto3 を直叩きしない）。
DemoMode では S3AccessPointAlias に通常の S3 バケット名を渡しても同じ経路で動く。

Environment Variables:
    S3_ACCESS_POINT_ALIAS: S3 AP Alias（DemoMode では通常バケット名）
    FILE_PREFIX: スキャン対象プレフィックス（例: "idoc-export/"）
    MAX_FILES: 1 実行あたりの最大ファイル数（デフォルト: 100）
"""

from __future__ import annotations

import logging
import os
from typing import Any

from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@lambda_error_handler
def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Discovery Lambda ハンドラー。

    S3 AP からファイル一覧を取得し、後続 Map 処理の入力を生成する。

    Args:
        event: ワークフロー入力。エージェントが StartExecution に渡した
            `input` JSON がそのまま届く（例: {"file_prefix": "...", "max_files": 50}）。
        context: Lambda コンテキスト。

    Returns:
        dict: {status, object_count, objects, prefix}。
            object_count が 0 のときは後続 Choice が Report へ分岐する。

    Raises:
        S3ApHelperError: S3 AP アクセスに失敗した場合（Step Functions の
            Retry/Catch を機能させるため握りつぶさず再送出する）。
    """
    prefix = event.get("file_prefix") or os.environ.get("FILE_PREFIX", "")
    max_files = int(event.get("max_files") or os.environ.get("MAX_FILES", "100"))
    alias = os.environ.get("S3_ACCESS_POINT_ALIAS", "")

    logger.info("Discovery: alias=%s, prefix=%s, max=%d", alias, prefix, max_files)

    metrics = EmfMetrics(service="stepfunctions-agentcore-tools")

    helper = S3ApHelper(alias)
    objects = helper.list_objects(prefix=prefix, max_keys=min(1000, max_files))

    # list_objects はページネーションで全件返すため、上限でクライアント側に切る。
    truncated = len(objects) > max_files
    objects = objects[:max_files]

    manifest = [
        {
            "key": obj["Key"],
            "size": obj["Size"],
            "last_modified": _isoformat(obj.get("LastModified")),
            "category": _categorize(obj["Key"]),
        }
        for obj in objects
    ]

    metrics.put_metric("FilesDiscovered", len(manifest), "Count")
    metrics.flush()

    logger.info("Discovery completed: %d files (truncated=%s)", len(manifest), truncated)

    return {
        "status": "completed",
        "object_count": len(manifest),
        "objects": manifest,
        "prefix": prefix,
        "truncated": truncated,
    }


def _isoformat(value: Any) -> str:
    """LastModified を ISO 文字列に正規化する。"""
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _categorize(key: str) -> str:
    """ファイルキーからおおまかなカテゴリを推定する（要約プロンプトの切り替え用）。"""
    key_lower = key.lower()
    if ".idoc" in key_lower or "idoc" in key_lower:
        return "sap_idoc"
    if ".edi" in key_lower or ".x12" in key_lower or ".edifact" in key_lower:
        return "edi_document"
    if ".csv" in key_lower or ".tsv" in key_lower:
        return "data_extract"
    if ".json" in key_lower:
        return "json_document"
    if ".xml" in key_lower:
        return "xml_document"
    return "general"
