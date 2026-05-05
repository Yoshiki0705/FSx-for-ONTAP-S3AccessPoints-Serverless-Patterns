"""クロスリージョン API クライアント

ap-northeast-1 非対応の AWS サービス（Textract, Comprehend Medical）を
対応リージョン（デフォルト: us-east-1）にルーティングするクライアントラッパー。

Lambda 実行ロールの認証情報をそのまま使用し、追加の認証設定は不要。
TLS 検証はデフォルトで有効。

Key patterns:
- CrossRegionConfig: dataclass ベースの設定（to_dict / from_dict round-trip 対応）
- CrossRegionClient: 許可リスト制御付きの boto3 クライアントファクトリ
- analyze_document(): Textract AnalyzeDocument のクロスリージョン実行
- detect_entities_v2(): Comprehend Medical DetectEntitiesV2 のクロスリージョン実行
- 許可リスト外サービス要求時に CrossRegionClientError を raise
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field

import boto3
from botocore.config import Config

from shared.exceptions import CrossRegionClientError

logger = logging.getLogger(__name__)


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
    ):
        self._config = config
        self._session = session or boto3.Session()
        self._clients: dict[str, boto3.client] = {}

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
