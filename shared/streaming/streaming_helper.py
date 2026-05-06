"""Kinesis Data Streams ヘルパー

Kinesis Data Streams の PutRecord / PutRecords 操作を抽象化し、
バッチ分割・部分失敗リトライ・イベントレコード生成を提供する。

Key patterns:
- StreamingConfig: dataclass ベースの設定（to_dict / from_dict round-trip 対応）
- StreamingHelper: Kinesis 操作ラッパー（put_record, put_records, describe_stream）
- put_records: 500 レコードまたは 5 MB 以下でバッチ分割
- 部分失敗時: 失敗レコードのみ指数バックオフでリトライ（max_retries 回）
- create_event_record: ファイル変更イベントを Kinesis レコードにシリアライズ
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass

import boto3

from shared.exceptions import StreamingError

logger = logging.getLogger(__name__)

# Kinesis PutRecords API の制約
MAX_RECORDS_PER_BATCH = 500
MAX_BATCH_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


@dataclass
class StreamingConfig:
    """Kinesis ストリーミング設定

    Attributes:
        stream_name: Kinesis Data Stream 名
        region: AWS リージョン
        batch_size: バッチあたりの最大レコード数 (デフォルト: 500)
        max_retries: 最大リトライ回数 (デフォルト: 3)
    """

    stream_name: str
    region: str
    batch_size: int = 500
    max_retries: int = 3

    def to_dict(self) -> dict:
        """設定を辞書に変換"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> StreamingConfig:
        """辞書から設定を復元

        未知のキーは無視し、dataclass フィールドに一致するキーのみ使用する。
        """
        return cls(
            **{k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        )


class StreamingHelper:
    """Kinesis Data Streams 操作ヘルパー

    Kinesis Data Streams の PutRecord / PutRecords / DescribeStream を
    抽象化し、バッチ分割・部分失敗リトライを提供する。

    Usage:
        config = StreamingConfig(stream_name="my-stream", region="ap-northeast-1")
        helper = StreamingHelper(config)
        helper.put_record(data=b'{"key": "value"}', partition_key="pk-1")
    """

    def __init__(
        self,
        config: StreamingConfig,
        session: boto3.Session | None = None,
    ):
        self._config = config
        self._session = session or boto3.Session()
        self._client = self._session.client(
            "kinesis",
            region_name=config.region,
        )

    def put_record(self, data: bytes, partition_key: str) -> dict:
        """単一レコードを Kinesis Data Stream に書き込む

        Args:
            data: レコードデータ (バイト列)
            partition_key: パーティションキー

        Returns:
            dict: Kinesis PutRecord レスポンス

        Raises:
            StreamingError: Kinesis API 呼び出しに失敗した場合
        """
        try:
            response = self._client.put_record(
                StreamName=self._config.stream_name,
                Data=data,
                PartitionKey=partition_key,
            )
            logger.debug(
                "PutRecord succeeded: SequenceNumber=%s, ShardId=%s",
                response.get("SequenceNumber"),
                response.get("ShardId"),
            )
            return response
        except Exception as e:
            raise StreamingError(
                f"PutRecord failed for stream '{self._config.stream_name}': {e}",
                failed_records=[{"Data": data, "PartitionKey": partition_key}],
            ) from e

    def put_records(self, records: list[dict]) -> dict:
        """複数レコードを Kinesis Data Stream にバッチ書き込みする

        レコードを 500 件または 5 MB 以下のバッチに分割し、
        部分失敗時は失敗レコードのみ指数バックオフでリトライする。

        Args:
            records: レコードリスト。各レコードは {"Data": bytes, "PartitionKey": str} 形式

        Returns:
            dict: 最終バッチの Kinesis PutRecords レスポンス（集約）

        Raises:
            StreamingError: 全リトライ失敗時
        """
        if not records:
            return {"FailedRecordCount": 0, "Records": []}

        batches = self._batch_records(records)
        all_responses: list[dict] = []
        total_failed: list[dict] = []
        error_codes: list[str] = []

        for batch in batches:
            response = self._put_batch_with_retry(batch)
            all_responses.append(response)

            # 最終リトライ後も失敗が残っている場合を収集
            if response.get("_remaining_failures"):
                total_failed.extend(response["_remaining_failures"])
                error_codes.extend(response.get("_error_codes", []))

        if total_failed:
            raise StreamingError(
                f"PutRecords failed for {len(total_failed)} records after "
                f"{self._config.max_retries} retries",
                failed_records=total_failed,
                error_codes=error_codes,
            )

        return {
            "FailedRecordCount": 0,
            "Records": [r for resp in all_responses for r in resp.get("Records", [])],
        }

    def describe_stream(self) -> dict:
        """Kinesis Data Stream の情報を取得する

        Returns:
            dict: Kinesis DescribeStream レスポンス

        Raises:
            StreamingError: Kinesis API 呼び出しに失敗した場合
        """
        try:
            response = self._client.describe_stream(
                StreamName=self._config.stream_name,
            )
            return response
        except Exception as e:
            raise StreamingError(
                f"DescribeStream failed for stream "
                f"'{self._config.stream_name}': {e}",
            ) from e

    @staticmethod
    def create_event_record(
        key: str,
        event_type: str,
        timestamp: str,
        metadata: dict | None = None,
    ) -> dict:
        """ファイル変更イベントを Kinesis レコード形式にシリアライズする

        パーティションキーはファイルパスの最初のディレクトリセグメントから導出する。

        Args:
            key: S3 オブジェクトキー (例: "images/product/001.jpg")
            event_type: イベントタイプ (例: "created", "modified", "deleted")
            timestamp: ISO 8601 タイムスタンプ
            metadata: 追加メタデータ (オプション)

        Returns:
            dict: {"Data": bytes, "PartitionKey": str} 形式の Kinesis レコード
        """
        event_data = {
            "key": key,
            "event_type": event_type,
            "timestamp": timestamp,
        }
        if metadata:
            event_data["metadata"] = metadata

        # パーティションキー: ファイルパスの最初のディレクトリセグメント
        segments = key.split("/")
        partition_key = segments[0] if segments else key

        return {
            "Data": json.dumps(event_data).encode("utf-8"),
            "PartitionKey": partition_key,
        }

    @staticmethod
    def _batch_records(records: list[dict]) -> list[list[dict]]:
        """レコードリストを Kinesis API 制約に準拠するバッチに分割する

        制約:
        - 1 バッチあたり最大 500 レコード
        - 1 バッチあたり最大 5 MB ペイロード

        Args:
            records: レコードリスト

        Returns:
            list[list[dict]]: バッチに分割されたレコードリスト
        """
        batches: list[list[dict]] = []
        current_batch: list[dict] = []
        current_size = 0

        for record in records:
            record_size = len(record.get("Data", b"")) + len(
                record.get("PartitionKey", "").encode("utf-8")
            )

            # 現在のバッチに追加するとサイズ制約を超える場合、新バッチを開始
            would_exceed_count = len(current_batch) >= MAX_RECORDS_PER_BATCH
            would_exceed_size = (current_size + record_size) > MAX_BATCH_SIZE_BYTES

            if current_batch and (would_exceed_count or would_exceed_size):
                batches.append(current_batch)
                current_batch = []
                current_size = 0

            current_batch.append(record)
            current_size += record_size

        if current_batch:
            batches.append(current_batch)

        return batches

    def _put_batch_with_retry(self, records: list[dict]) -> dict:
        """バッチ PutRecords を部分失敗リトライ付きで実行する

        Args:
            records: レコードリスト

        Returns:
            dict: Kinesis PutRecords レスポンス + _remaining_failures (あれば)
        """
        current_records = records
        last_response: dict = {}

        for attempt in range(self._config.max_retries + 1):
            try:
                last_response = self._client.put_records(
                    StreamName=self._config.stream_name,
                    Records=current_records,
                )
            except Exception as e:
                if attempt == self._config.max_retries:
                    raise StreamingError(
                        f"PutRecords API call failed after "
                        f"{self._config.max_retries} retries: {e}",
                        failed_records=current_records,
                    ) from e
                # 指数バックオフ
                wait_time = (2**attempt) * 0.1
                logger.warning(
                    "PutRecords API error (attempt %d/%d): %s. "
                    "Retrying in %.2fs",
                    attempt + 1,
                    self._config.max_retries,
                    str(e),
                    wait_time,
                )
                time.sleep(wait_time)
                continue

            failed_count = last_response.get("FailedRecordCount", 0)
            if failed_count == 0:
                return last_response

            # 部分失敗: 失敗レコードのみ抽出してリトライ
            if attempt < self._config.max_retries:
                current_records, error_codes = self._retry_failed(
                    current_records, last_response
                )
                wait_time = (2**attempt) * 0.1
                logger.warning(
                    "PutRecords partial failure: %d/%d failed (attempt %d/%d). "
                    "Retrying in %.2fs",
                    failed_count,
                    len(records),
                    attempt + 1,
                    self._config.max_retries,
                    wait_time,
                )
                time.sleep(wait_time)
            else:
                # 最終リトライ後も失敗が残っている
                failed_records, error_codes = self._retry_failed(
                    current_records, last_response
                )
                last_response["_remaining_failures"] = failed_records
                last_response["_error_codes"] = error_codes

        return last_response

    @staticmethod
    def _retry_failed(
        records: list[dict], response: dict
    ) -> tuple[list[dict], list[str]]:
        """PutRecords レスポンスから失敗レコードを抽出する

        Args:
            records: 送信したレコードリスト
            response: Kinesis PutRecords レスポンス

        Returns:
            tuple: (失敗レコードリスト, エラーコードリスト)
        """
        failed_records: list[dict] = []
        error_codes: list[str] = []

        for i, result in enumerate(response.get("Records", [])):
            if result.get("ErrorCode"):
                failed_records.append(records[i])
                error_codes.append(result["ErrorCode"])

        return failed_records, error_codes
