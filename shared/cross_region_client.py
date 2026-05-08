"""クロスリージョン API クライアント

ap-northeast-1 非対応の AWS サービス（Textract, Comprehend Medical）を
対応リージョン（デフォルト: us-east-1）にルーティングするクライアントラッパー。

Lambda 実行ロールの認証情報をそのまま使用し、追加の認証設定は不要。
TLS 検証はデフォルトで有効。

Phase 5 拡張:
- discover_regional_endpoints(): リージョン別 S3 AP ARN を返す
- access_with_failover(): Primary → Secondary 自動フェイルオーバー
- EMF メトリクス: CrossRegionLatency, CrossRegionRequestCount, CrossRegionFailoverCount

Key patterns:
- CrossRegionConfig: dataclass ベースの設定（to_dict / from_dict round-trip 対応）
- CrossRegionClient: 許可リスト制御付きの boto3 クライアントファクトリ
- analyze_document(): Textract AnalyzeDocument のクロスリージョン実行
- detect_entities_v2(): Comprehend Medical DetectEntitiesV2 のクロスリージョン実行
- 許可リスト外サービス要求時に CrossRegionClientError を raise
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import (
    ClientError,
    ConnectTimeoutError,
    EndpointConnectionError,
    ReadTimeoutError,
)

from shared.exceptions import CrossRegionClientError
from shared.observability import EmfMetrics

logger = logging.getLogger(__name__)

# フェイルオーバー対象のエラーコード（HTTP 5xx）
_FAILOVER_HTTP_CODES = {500, 502, 503, 504}

# フェイルオーバー対象の例外タイプ
_FAILOVER_EXCEPTIONS = (
    ConnectTimeoutError,
    ReadTimeoutError,
    EndpointConnectionError,
)


@dataclass
class CrossRegionConfig:
    """クロスリージョンクライアント設定

    Attributes:
        target_region: ターゲットリージョン (デフォルト: us-east-1)
        services: 許可サービスリスト (デフォルト: ["textract", "comprehendmedical"])
        verify_ssl: TLS 検証の有効/無効 (デフォルト: True)
        connect_timeout: 接続タイムアウト秒数 (デフォルト: 10)
        read_timeout: 読み取りタイムアウト秒数 (デフォルト: 60)
    """

    target_region: str = "us-east-1"
    services: list[str] = field(
        default_factory=lambda: ["textract", "comprehendmedical"]
    )
    verify_ssl: bool = True
    connect_timeout: int = 10
    read_timeout: int = 60

    def to_dict(self) -> dict:
        """設定を辞書に変換"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> CrossRegionConfig:
        """辞書から設定を復元

        未知のキーは無視し、dataclass フィールドに一致するキーのみ使用する。
        """
        return cls(
            **{k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        )


class CrossRegionClient:
    """クロスリージョン API クライアント

    ap-northeast-1 非対応の AWS サービス（Textract, Comprehend Medical）を
    対応リージョン（デフォルト: us-east-1）にルーティングする。
    Lambda 実行ロールの認証情報をそのまま使用し、追加の認証設定は不要。

    Usage:
        config = CrossRegionConfig(target_region="us-east-1")
        client = CrossRegionClient(config)
        result = client.analyze_document(document_bytes, ["TABLES", "FORMS"])
    """

    def __init__(
        self,
        config: CrossRegionConfig,
        session: boto3.Session | None = None,
        primary_region: str = "ap-northeast-1",
        secondary_region: str = "us-east-1",
        failover_enabled: bool = True,
    ):
        self._config = config
        self._session = session or boto3.Session()
        self._clients: dict[str, boto3.client] = {}
        self._primary_region = primary_region
        self._secondary_region = secondary_region
        self._failover_enabled = failover_enabled
        self._s3_clients: dict[str, boto3.client] = {}

    def get_client(self, service_name: str) -> boto3.client:
        """指定サービスのクロスリージョン boto3 クライアントを取得

        Args:
            service_name: AWS サービス名 (例: "textract", "comprehendmedical")

        Returns:
            boto3.client: ターゲットリージョンの boto3 クライアント

        Raises:
            CrossRegionClientError: サービスが許可リストにない場合、
                                     またはクライアント作成に失敗した場合
        """
        if service_name not in self._config.services:
            raise CrossRegionClientError(
                f"Service '{service_name}' is not in allowed services: "
                f"{self._config.services}",
                target_region=self._config.target_region,
                service_name=service_name,
            )

        if service_name not in self._clients:
            try:
                boto_config = Config(
                    connect_timeout=self._config.connect_timeout,
                    read_timeout=self._config.read_timeout,
                )
                self._clients[service_name] = self._session.client(
                    service_name,
                    region_name=self._config.target_region,
                    verify=self._config.verify_ssl,
                    config=boto_config,
                )
                logger.info(
                    "Created cross-region client for '%s' in region '%s'",
                    service_name,
                    self._config.target_region,
                )
            except Exception as e:
                raise CrossRegionClientError(
                    f"Failed to create client for '{service_name}' in region "
                    f"'{self._config.target_region}': {e}",
                    target_region=self._config.target_region,
                    service_name=service_name,
                    original_error=e,
                ) from e

        return self._clients[service_name]

    def analyze_document(
        self,
        document_bytes: bytes,
        feature_types: list[str] | None = None,
    ) -> dict:
        """Textract AnalyzeDocument をクロスリージョンで実行

        Args:
            document_bytes: ドキュメントのバイトデータ
            feature_types: 抽出する特徴タイプ (例: ["TABLES", "FORMS"])
                           未指定時は ["TABLES", "FORMS"] をデフォルトで使用

        Returns:
            dict: Textract AnalyzeDocument レスポンス

        Raises:
            CrossRegionClientError: Textract API 呼び出しに失敗した場合
        """
        client = self.get_client("textract")
        params: dict = {
            "Document": {"Bytes": document_bytes},
            "FeatureTypes": feature_types if feature_types else ["TABLES", "FORMS"],
        }

        try:
            return client.analyze_document(**params)
        except CrossRegionClientError:
            raise
        except Exception as e:
            raise CrossRegionClientError(
                f"Textract AnalyzeDocument failed in region "
                f"'{self._config.target_region}': {e}",
                target_region=self._config.target_region,
                service_name="textract",
                original_error=e,
            ) from e

    def detect_entities_v2(self, text: str) -> dict:
        """Comprehend Medical DetectEntitiesV2 をクロスリージョンで実行

        Args:
            text: 解析対象テキスト

        Returns:
            dict: Comprehend Medical DetectEntitiesV2 レスポンス

        Raises:
            CrossRegionClientError: Comprehend Medical API 呼び出しに失敗した場合
        """
        client = self.get_client("comprehendmedical")

        try:
            return client.detect_entities_v2(Text=text)
        except CrossRegionClientError:
            raise
        except Exception as e:
            raise CrossRegionClientError(
                f"Comprehend Medical DetectEntitiesV2 failed in region "
                f"'{self._config.target_region}': {e}",
                target_region=self._config.target_region,
                service_name="comprehendmedical",
                original_error=e,
            ) from e

    # =================================================================
    # Phase 5: Multi-Region Failover Methods
    # =================================================================

    @property
    def primary_region(self) -> str:
        """プライマリリージョンを返す。"""
        return self._primary_region

    @property
    def secondary_region(self) -> str:
        """セカンダリリージョンを返す。"""
        return self._secondary_region

    @property
    def failover_enabled(self) -> bool:
        """フェイルオーバーが有効かどうかを返す。"""
        return self._failover_enabled

    def discover_regional_endpoints(self) -> dict[str, str]:
        """リージョン別 S3 Access Point ARN を返す。

        環境変数または DynamoDB 設定テーブルから S3 AP ARN を取得する。
        環境変数の命名規則: S3AP_ARN_{REGION_UPPER} (例: S3AP_ARN_AP_NORTHEAST_1)

        Returns:
            dict[str, str]: リージョン → S3 AP ARN のマッピング
                例: {"ap-northeast-1": "arn:aws:s3:ap-northeast-1:...", "us-east-1": "arn:..."}
        """
        endpoints: dict[str, str] = {}

        # 環境変数から取得（優先）
        for region in [self._primary_region, self._secondary_region]:
            env_key = f"S3AP_ARN_{region.upper().replace('-', '_')}"
            arn = os.environ.get(env_key)
            if arn:
                endpoints[region] = arn

        # DynamoDB 設定テーブルからのフォールバック
        if not endpoints:
            config_table_name = os.environ.get(
                "REGIONAL_CONFIG_TABLE", "fsxn-s3ap-regional-config"
            )
            try:
                dynamodb = self._session.resource("dynamodb")
                table = dynamodb.Table(config_table_name)
                response = table.scan(
                    FilterExpression="attribute_exists(s3ap_arn)",
                )
                for item in response.get("Items", []):
                    region = item.get("region")
                    arn = item.get("s3ap_arn")
                    if region and arn:
                        endpoints[region] = arn
            except Exception as e:
                logger.warning(
                    "Failed to discover endpoints from DynamoDB config table "
                    "'%s': %s",
                    config_table_name,
                    str(e),
                )

        logger.info(
            "Discovered regional endpoints: %s",
            list(endpoints.keys()),
        )
        return endpoints

    def access_with_failover(
        self, operation: str, **kwargs: Any
    ) -> dict[str, Any]:
        """S3 AP オペレーションを自動フェイルオーバー付きで実行する。

        フロー:
          1. プライマリリージョンでオペレーションを試行
          2. プライマリ失敗時（timeout, 5xx, connection_error）:
             a. CrossRegionFailoverCount メトリクスを出力
             b. セカンダリリージョンでオペレーションを試行
          3. セカンダリも失敗した場合、CrossRegionClientError を raise

        Args:
            operation: S3 オペレーション名 (例: "get_object", "list_objects_v2")
            **kwargs: S3 オペレーションに渡すパラメータ

        Returns:
            dict: オペレーション結果 + メタデータ
                {
                    "response": <S3 レスポンス>,
                    "region_served": <実際にレスポンスを返したリージョン>,
                    "latency_ms": <レイテンシ（ミリ秒）>,
                    "is_failover": <フェイルオーバーが発生したか>
                }

        Raises:
            CrossRegionClientError: 全リージョンでオペレーションが失敗した場合
        """
        metrics = EmfMetrics(
            namespace="FSxN-S3AP-Patterns",
            service="CrossRegionClient",
        )
        metrics.set_dimension("Operation", operation)

        # プライマリリージョンで試行
        start_time = time.time()
        try:
            response = self._execute_s3_operation(
                self._primary_region, operation, **kwargs
            )
            latency_ms = (time.time() - start_time) * 1000

            metrics.put_metric("CrossRegionLatency", latency_ms, "Milliseconds")
            metrics.put_metric("CrossRegionRequestCount", 1.0, "Count")
            metrics.set_property("region_served", self._primary_region)
            metrics.flush()

            return {
                "response": response,
                "region_served": self._primary_region,
                "latency_ms": latency_ms,
                "is_failover": False,
            }

        except _FAILOVER_EXCEPTIONS as primary_error:
            logger.warning(
                "Primary region '%s' failed for operation '%s': %s. "
                "Attempting failover to '%s'.",
                self._primary_region,
                operation,
                str(primary_error),
                self._secondary_region,
            )
            if not self._failover_enabled:
                raise CrossRegionClientError(
                    f"Primary region '{self._primary_region}' failed and "
                    f"failover is disabled: {primary_error}",
                    target_region=self._primary_region,
                    service_name="s3",
                    original_error=primary_error,
                ) from primary_error

        except ClientError as primary_error:
            http_code = primary_error.response.get("ResponseMetadata", {}).get(
                "HTTPStatusCode", 0
            )
            if http_code not in _FAILOVER_HTTP_CODES:
                # 4xx エラーはフェイルオーバー対象外（クライアントエラー）
                raise CrossRegionClientError(
                    f"S3 operation '{operation}' failed in primary region "
                    f"'{self._primary_region}' with HTTP {http_code}: "
                    f"{primary_error}",
                    target_region=self._primary_region,
                    service_name="s3",
                    original_error=primary_error,
                ) from primary_error

            logger.warning(
                "Primary region '%s' returned HTTP %d for operation '%s'. "
                "Attempting failover to '%s'.",
                self._primary_region,
                http_code,
                operation,
                self._secondary_region,
            )
            if not self._failover_enabled:
                raise CrossRegionClientError(
                    f"Primary region '{self._primary_region}' returned HTTP "
                    f"{http_code} and failover is disabled: {primary_error}",
                    target_region=self._primary_region,
                    service_name="s3",
                    original_error=primary_error,
                ) from primary_error

        # セカンダリリージョンで試行（フェイルオーバー）
        start_time = time.time()
        try:
            response = self._execute_s3_operation(
                self._secondary_region, operation, **kwargs
            )
            latency_ms = (time.time() - start_time) * 1000

            metrics.put_metric("CrossRegionLatency", latency_ms, "Milliseconds")
            metrics.put_metric("CrossRegionRequestCount", 1.0, "Count")
            metrics.put_metric("CrossRegionFailoverCount", 1.0, "Count")
            metrics.set_property("region_served", self._secondary_region)
            metrics.set_property("is_failover", True)
            metrics.flush()

            return {
                "response": response,
                "region_served": self._secondary_region,
                "latency_ms": latency_ms,
                "is_failover": True,
            }

        except Exception as secondary_error:
            metrics.put_metric("CrossRegionFailoverCount", 1.0, "Count")
            metrics.put_metric("CrossRegionRequestCount", 1.0, "Count")
            metrics.flush()

            raise CrossRegionClientError(
                f"S3 operation '{operation}' failed in both primary "
                f"'{self._primary_region}' and secondary "
                f"'{self._secondary_region}' regions: {secondary_error}",
                target_region=self._secondary_region,
                service_name="s3",
                original_error=secondary_error,
            ) from secondary_error

    def _get_s3_client(self, region: str) -> boto3.client:
        """指定リージョンの S3 クライアントを取得（キャッシュ付き）。

        Args:
            region: AWS リージョンコード

        Returns:
            boto3.client: S3 クライアント
        """
        if region not in self._s3_clients:
            boto_config = Config(
                connect_timeout=self._config.connect_timeout,
                read_timeout=self._config.read_timeout,
                retries={"max_attempts": 1},
            )
            self._s3_clients[region] = self._session.client(
                "s3",
                region_name=region,
                config=boto_config,
            )
        return self._s3_clients[region]

    def _execute_s3_operation(
        self, region: str, operation: str, **kwargs: Any
    ) -> dict:
        """指定リージョンで S3 オペレーションを実行する。

        Args:
            region: AWS リージョンコード
            operation: S3 オペレーション名
            **kwargs: オペレーションパラメータ

        Returns:
            dict: S3 オペレーションレスポンス

        Raises:
            ClientError: S3 API エラー
            ConnectTimeoutError: 接続タイムアウト
            ReadTimeoutError: 読み取りタイムアウト
            EndpointConnectionError: エンドポイント接続エラー
        """
        client = self._get_s3_client(region)
        method = getattr(client, operation, None)
        if method is None:
            raise CrossRegionClientError(
                f"Unknown S3 operation: '{operation}'",
                target_region=region,
                service_name="s3",
            )
        return method(**kwargs)
