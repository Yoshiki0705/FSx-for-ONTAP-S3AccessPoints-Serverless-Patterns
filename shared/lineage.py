"""shared.lineage — Data Lineage Tracking モジュール

ファイル処理履歴を DynamoDB に記録し、ソースファイルから出力までの追跡を可能にする。
各 UC の Processing Lambda から呼び出される共通ヘルパー。

設計方針:
- DynamoDB テーブル data-lineage への処理履歴レコード書き込み
- PK: source_file_key, SK: processing_timestamp でソートされた履歴
- GSI uc_id-timestamp-index で UC 別クエリをサポート
- 書き込み失敗時は警告ログ出力のみ（メイン処理を中断しない）
- TTL（365 日）による自動削除

Usage:
    from shared.lineage import LineageTracker, LineageRecord

    tracker = LineageTracker()
    record = LineageRecord(
        source_file_key="/vol1/legal/contracts/deal-001.pdf",
        processing_timestamp="2026-06-15T14:30:45.123Z",
        step_functions_execution_arn="arn:aws:states:...:execution:...",
        uc_id="legal-compliance",
        output_keys=["s3://output-bucket/legal/reports/deal-001-analysis.json"],
        status="success",
        duration_ms=4523,
    )
    lineage_id = tracker.record(record)
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

import boto3
from boto3.dynamodb.conditions import Attr, Key

logger = logging.getLogger(__name__)

# 有効なステータス値
VALID_STATUSES = frozenset({"success", "failed", "partial"})


@dataclass
class LineageRecord:
    """ファイル処理履歴レコード。"""

    source_file_key: str
    processing_timestamp: str
    step_functions_execution_arn: str
    uc_id: str
    output_keys: list[str]
    status: str  # "success" | "failed" | "partial"
    duration_ms: int
    metadata: dict[str, Any] | None = None


class LineageTracker:
    """ファイル処理履歴を DynamoDB に記録・検索するクラス。

    Args:
        table_name: DynamoDB テーブル名。None の場合は環境変数から取得。
        dynamodb_resource: boto3 DynamoDB resource。テスト用に注入可能。
    """

    # TTL: 365 日（秒）
    DEFAULT_TTL_DAYS: int = 365

    def __init__(
        self,
        table_name: str | None = None,
        dynamodb_resource: Any | None = None,
    ) -> None:
        self._table_name = table_name or os.environ.get(
            "LINEAGE_TABLE", "fsxn-s3ap-data-lineage"
        )
        self._dynamodb = dynamodb_resource or boto3.resource("dynamodb")

    def _validate_status(self, status: str) -> None:
        """ステータス値を検証する。

        Raises:
            ValueError: 無効なステータス値の場合
        """
        if status not in VALID_STATUSES:
            raise ValueError(
                f"Invalid status '{status}'. Must be one of: {sorted(VALID_STATUSES)}"
            )

    def _item_to_record(self, item: dict[str, Any]) -> LineageRecord:
        """DynamoDB アイテムを LineageRecord に変換する。"""
        return LineageRecord(
            source_file_key=item["source_file_key"],
            processing_timestamp=item["processing_timestamp"],
            step_functions_execution_arn=item.get("step_functions_execution_arn", ""),
            uc_id=item.get("uc_id", ""),
            output_keys=item.get("output_keys", []),
            status=item.get("status", ""),
            duration_ms=int(item.get("duration_ms", 0)),
            metadata=item.get("metadata"),
        )

    def record(self, record: LineageRecord) -> str:
        """処理履歴レコードを DynamoDB に書き込む。

        Args:
            record: 書き込むレコード

        Returns:
            lineage_id: 生成されたレコード ID

        Note:
            書き込み失敗時は警告ログを出力するがメイン処理を中断しない。
        """
        self._validate_status(record.status)

        table = self._dynamodb.Table(self._table_name)

        item: dict[str, Any] = {
            "source_file_key": record.source_file_key,
            "processing_timestamp": record.processing_timestamp,
            "step_functions_execution_arn": record.step_functions_execution_arn,
            "uc_id": record.uc_id,
            "output_keys": record.output_keys,
            "status": record.status,
            "duration_ms": record.duration_ms,
        }

        if record.metadata:
            item["metadata"] = record.metadata

        # TTL: 365 days from now
        item["ttl"] = int(time.time()) + (self.DEFAULT_TTL_DAYS * 86400)

        lineage_id = f"{record.source_file_key}#{record.processing_timestamp}"

        try:
            table.put_item(Item=item)
        except Exception as exc:
            logger.warning(
                "[Lineage] Failed to write record: %s (source=%s, uc=%s). "
                "Main processing will continue.",
                exc,
                record.source_file_key,
                record.uc_id,
            )
            return lineage_id

        logger.info(
            "[Lineage] Recorded: uc=%s source=%s status=%s duration=%dms",
            record.uc_id,
            record.source_file_key,
            record.status,
            record.duration_ms,
        )
        return lineage_id

    def get_history(
        self,
        source_file_key: str,
        limit: int = 50,
    ) -> list[LineageRecord]:
        """ソースファイルキーで処理履歴を検索する。

        Args:
            source_file_key: 検索するソースファイルキー
            limit: 返却する最大レコード数

        Returns:
            processing_timestamp 降順でソートされた履歴リスト
        """
        table = self._dynamodb.Table(self._table_name)

        try:
            response = table.query(
                KeyConditionExpression=Key("source_file_key").eq(source_file_key),
                ScanIndexForward=False,  # 降順ソート
                Limit=limit,
            )
        except Exception as exc:
            logger.warning(
                "[Lineage] Failed to query history for source=%s: %s",
                source_file_key,
                exc,
            )
            return []

        return [self._item_to_record(item) for item in response.get("Items", [])]

    def get_by_uc(
        self,
        uc_id: str,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int = 100,
    ) -> list[LineageRecord]:
        """UC ID で処理履歴を検索する（GSI 使用）。

        Args:
            uc_id: UC 識別子
            start_time: 検索開始時刻（ISO 8601）
            end_time: 検索終了時刻（ISO 8601）
            limit: 返却する最大レコード数

        Returns:
            該当する LineageRecord のリスト
        """
        table = self._dynamodb.Table(self._table_name)

        # Build key condition expression
        key_condition = Key("uc_id").eq(uc_id)

        if start_time and end_time:
            key_condition = key_condition & Key("processing_timestamp").between(
                start_time, end_time
            )
        elif start_time:
            key_condition = key_condition & Key("processing_timestamp").gte(start_time)
        elif end_time:
            key_condition = key_condition & Key("processing_timestamp").lte(end_time)

        try:
            response = table.query(
                IndexName="uc_id-timestamp-index",
                KeyConditionExpression=key_condition,
                ScanIndexForward=False,  # 降順ソート
                Limit=limit,
            )
        except Exception as exc:
            logger.warning(
                "[Lineage] Failed to query by UC uc_id=%s: %s",
                uc_id,
                exc,
            )
            return []

        return [self._item_to_record(item) for item in response.get("Items", [])]

    def get_by_execution(
        self,
        execution_arn: str,
    ) -> list[LineageRecord]:
        """Step Functions 実行 ARN で処理履歴を検索する。

        Uses Scan with FilterExpression since execution_arn is not a key attribute.

        Args:
            execution_arn: Step Functions 実行 ARN

        Returns:
            該当する LineageRecord のリスト
        """
        table = self._dynamodb.Table(self._table_name)

        try:
            response = table.scan(
                FilterExpression=Attr("step_functions_execution_arn").eq(execution_arn),
            )
            items = response.get("Items", [])

            # Handle pagination for large tables
            while "LastEvaluatedKey" in response:
                response = table.scan(
                    FilterExpression=Attr("step_functions_execution_arn").eq(
                        execution_arn
                    ),
                    ExclusiveStartKey=response["LastEvaluatedKey"],
                )
                items.extend(response.get("Items", []))

        except Exception as exc:
            logger.warning(
                "[Lineage] Failed to scan by execution_arn=%s: %s",
                execution_arn,
                exc,
            )
            return []

        return [self._item_to_record(item) for item in items]
