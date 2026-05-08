"""DynamoDB ベース Task Token ストレージ

SageMaker Callback Pattern で使用する Task Token を DynamoDB に保存し、
短縮 Correlation ID（8 文字 hex）をキーとして管理する。

SageMaker ジョブタグの 256 文字制限を回避するため、Task Token（約 1000 文字）を
DynamoDB に格納し、8 文字の Correlation ID を間接参照キーとして使用する。

Classes:
    TaskTokenStore: DynamoDB Task Token ストレージクラス

Usage:
    store = TaskTokenStore(table_name="my-token-table", ttl_seconds=86400)
    correlation_id = store.store_token(task_token="...", transform_job_name="my-job")
    token = store.retrieve_token(correlation_id)
    store.delete_token(correlation_id)
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from shared.exceptions import TokenStorageError

logger = logging.getLogger(__name__)

# Maximum number of retries on correlation ID collision
_MAX_RETRIES = 3


class TaskTokenStore:
    """DynamoDB-based Task Token storage for SageMaker Callback Pattern.

    Correlation ID（UUID4 先頭 8 文字 hex）をパーティションキーとして
    Task Token を DynamoDB に保存する。TTL による自動クリーンアップ、
    conditional write による衝突防止、GSI によるジョブ名逆引きをサポート。

    Global Tables 対応: region パラメータにより書き込み先リージョンを指定可能。
    Global Tables ではローカルレプリカに自動書き込みされるため、通常は
    region=None（現在リージョン）で動作する。source_region 属性をレコードに
    追加し、デバッグ・監査用途に使用する。

    Attributes:
        table_name: DynamoDB テーブル名
        ttl_seconds: Token の有効期間（秒）。デフォルト 86400（24 時間）
        region: DynamoDB 書き込み先リージョン。None の場合は AWS_REGION 環境変数を使用
        source_region: レコードに付与するソースリージョン識別子
    """

    def __init__(
        self,
        table_name: str,
        ttl_seconds: int = 86400,
        region: Optional[str] = None,
    ):
        """Initialize with DynamoDB table name, TTL, and optional region.

        Global Tables ではローカルレプリカに自動書き込みされるため、
        region パラメータは主に明示的なリージョン指定が必要な場合に使用する。
        region=None の場合は AWS_REGION 環境変数（Lambda 実行リージョン）を使用。

        Args:
            table_name: DynamoDB テーブル名
            ttl_seconds: Token の有効期間（秒）。デフォルト 86400（24 時間）
            region: DynamoDB 書き込み先リージョン。None の場合は現在リージョンを使用
        """
        self.table_name = table_name
        self.ttl_seconds = ttl_seconds
        self.region = region or os.environ.get("AWS_REGION", "ap-northeast-1")
        self.source_region = self.region

        if region:
            self._dynamodb = boto3.resource("dynamodb", region_name=region)
        else:
            self._dynamodb = boto3.resource("dynamodb")
        self._table = self._dynamodb.Table(table_name)

    def store_token(self, task_token: str, transform_job_name: str) -> str:
        """Generate correlation ID and store task token.

        Correlation ID を生成し、Task Token を DynamoDB に保存する。
        conditional write（attribute_not_exists）により衝突を防止し、
        衝突時は最大 3 回まで新しい Correlation ID で再試行する。

        Args:
            task_token: Step Functions Task Token
            transform_job_name: SageMaker Batch Transform ジョブ名

        Returns:
            correlation_id: 8 文字 hex の Correlation ID

        Raises:
            TokenStorageError: 3 回のリトライ後も保存に失敗した場合
        """
        current_time = int(time.time())
        ttl_value = current_time + self.ttl_seconds

        for attempt in range(1, _MAX_RETRIES + 1):
            correlation_id = self.generate_correlation_id()

            try:
                self._table.put_item(
                    Item={
                        "correlation_id": correlation_id,
                        "task_token": task_token,
                        "transform_job_name": transform_job_name,
                        "created_at": current_time,
                        "ttl": ttl_value,
                        "source_region": self.source_region,
                    },
                    ConditionExpression="attribute_not_exists(correlation_id)",
                )

                # セキュリティ: task_token の値はログに出力しない
                logger.info(
                    "Stored task token: correlation_id=%s, "
                    "transform_job_name=%s, ttl=%d",
                    correlation_id,
                    transform_job_name,
                    ttl_value,
                )
                return correlation_id

            except ClientError as e:
                if (
                    e.response["Error"]["Code"]
                    == "ConditionalCheckFailedException"
                ):
                    logger.warning(
                        "Correlation ID collision: correlation_id=%s, "
                        "attempt=%d/%d",
                        correlation_id,
                        attempt,
                        _MAX_RETRIES,
                    )
                    if attempt == _MAX_RETRIES:
                        raise TokenStorageError(
                            f"Failed to store task token after {_MAX_RETRIES} "
                            f"retries due to correlation ID collisions",
                            correlation_id=correlation_id,
                            retry_count=_MAX_RETRIES,
                        ) from e
                    # 次のリトライで新しい correlation_id を生成
                    continue
                else:
                    # その他の DynamoDB エラー
                    raise TokenStorageError(
                        f"DynamoDB error storing task token: {e}",
                        correlation_id=correlation_id,
                        retry_count=attempt,
                    ) from e

        # ここには到達しないが、型チェッカー対策
        raise TokenStorageError(  # pragma: no cover
            f"Failed to store task token after {_MAX_RETRIES} retries",
            retry_count=_MAX_RETRIES,
        )

    def retrieve_token(self, correlation_id: str) -> Optional[str]:
        """Retrieve task token by correlation ID.

        Correlation ID をキーとして DynamoDB から Task Token を取得する。
        レコードが存在しない場合（TTL 期限切れ含む）は None を返す。

        Args:
            correlation_id: 8 文字 hex の Correlation ID

        Returns:
            task_token: Task Token 文字列、または None（未発見/期限切れ）
        """
        try:
            response = self._table.get_item(
                Key={"correlation_id": correlation_id},
            )
        except ClientError as e:
            logger.error(
                "DynamoDB error retrieving token: correlation_id=%s, error=%s",
                correlation_id,
                str(e),
            )
            return None

        item = response.get("Item")
        if item is None:
            logger.warning(
                "Token not found: correlation_id=%s",
                correlation_id,
            )
            return None

        # セキュリティ: task_token の値はログに出力しない
        logger.info(
            "Retrieved task token: correlation_id=%s",
            correlation_id,
        )
        return item.get("task_token")

    def retrieve_token_by_job_name(
        self, transform_job_name: str
    ) -> Optional[str]:
        """Retrieve task token by SageMaker job name (GSI query).

        GSI（TransformJobNameIndex）を使用してジョブ名から Task Token を取得する。
        複数レコードが存在する場合は最初のレコードを返す。

        Args:
            transform_job_name: SageMaker Batch Transform ジョブ名

        Returns:
            task_token: Task Token 文字列、または None（未発見）
        """
        try:
            response = self._table.query(
                IndexName="TransformJobNameIndex",
                KeyConditionExpression="transform_job_name = :jn",
                ExpressionAttributeValues={":jn": transform_job_name},
            )
        except ClientError as e:
            logger.error(
                "DynamoDB error querying by job name: "
                "transform_job_name=%s, error=%s",
                transform_job_name,
                str(e),
            )
            return None

        items = response.get("Items", [])
        if not items:
            logger.warning(
                "Token not found by job name: transform_job_name=%s",
                transform_job_name,
            )
            return None

        # セキュリティ: task_token の値はログに出力しない
        logger.info(
            "Retrieved task token by job name: transform_job_name=%s, "
            "correlation_id=%s",
            transform_job_name,
            items[0].get("correlation_id"),
        )
        return items[0].get("task_token")

    def delete_token(self, correlation_id: str) -> None:
        """Delete token record after successful callback.

        コールバック成功後に DynamoDB レコードを削除する。
        レコードが存在しない場合もエラーにはならない。

        Args:
            correlation_id: 8 文字 hex の Correlation ID
        """
        try:
            self._table.delete_item(
                Key={"correlation_id": correlation_id},
            )
            logger.info(
                "Deleted task token: correlation_id=%s",
                correlation_id,
            )
        except ClientError as e:
            logger.error(
                "DynamoDB error deleting token: correlation_id=%s, error=%s",
                correlation_id,
                str(e),
            )

    @staticmethod
    def generate_correlation_id() -> str:
        """Generate 8-character hex correlation ID from UUID4.

        UUID4 を生成し、先頭 8 文字（hex）を Correlation ID として返す。
        32 ビットのエントロピーを提供する。

        Returns:
            8 文字の hex 文字列（例: "a1b2c3d4"）
        """
        return uuid.uuid4().hex[:8]
