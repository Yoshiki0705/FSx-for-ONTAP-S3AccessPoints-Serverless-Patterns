"""DemoMode 用モックデータローダー

operations/ パターン群で DemoMode=true の場合に、ONTAP REST API / CloudWatch
の代わりにモックデータを返す共通モジュール。

データソース:
    - test-data/ops/ ディレクトリの JSON fixtures (ローカルテスト時)
    - S3 バケット内の JSON fixtures (Lambda デプロイ時)

Usage:
    from shared.demo_data_loader import DemoDataLoader

    loader = DemoDataLoader(source="local", base_path="test-data/ops")
    volumes = loader.load_volume_space(fs_id="fs-demo01")

    # Lambda (S3 source)
    loader = DemoDataLoader(source="s3", bucket="my-bucket", prefix="demo-data/ops")
    volumes = loader.load_volume_space(fs_id="fs-demo01")
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class DemoDataLoader:
    """DemoMode 用のモックデータを読み込むクラス。

    ローカルファイルシステム or S3 からモック JSON を読み込み、
    OntapMetricsCollector と同じ形式のデータを返す。
    """

    def __init__(
        self,
        source: str = "local",
        base_path: str = "test-data/ops",
        bucket: str | None = None,
        prefix: str = "demo-data/ops",
    ) -> None:
        """Initialize DemoDataLoader.

        Args:
            source: データソース ("local" or "s3")
            base_path: ローカルファイルのベースパス (source="local" 時)
            bucket: S3 バケット名 (source="s3" 時)
            prefix: S3 プレフィックス (source="s3" 時)
        """
        self._source = source
        self._base_path = Path(base_path)
        self._bucket = bucket
        self._prefix = prefix

    def load_volume_space(self, fs_id: str = "fs-demo01") -> list[dict[str, Any]]:
        """ボリューム容量のモックデータを読み込む。

        Args:
            fs_id: デモ用ファイルシステム ID

        Returns:
            list[dict]: VolumeSpaceMetric 形式のデータリスト
        """
        data = self._load_fixture("volume_space.json")
        # Inject fs_id into each record
        for record in data:
            record["fs_id"] = fs_id
        return data

    def load_aggregate_space(self, fs_id: str = "fs-demo01") -> list[dict[str, Any]]:
        """アグリゲート容量のモックデータを読み込む。

        Args:
            fs_id: デモ用ファイルシステム ID

        Returns:
            list[dict]: AggregateSpaceMetric 形式のデータリスト
        """
        data = self._load_fixture("aggregate_space.json")
        for record in data:
            record["fs_id"] = fs_id
        return data

    def load_cloudwatch_metrics(self, fs_id: str = "fs-demo01") -> dict[str, Any]:
        """CloudWatch メトリクスのモックデータを読み込む。

        Args:
            fs_id: デモ用ファイルシステム ID

        Returns:
            dict: CloudWatchFsMetric 形式のデータ
        """
        data = self._load_fixture("cloudwatch_metrics.json")
        data["fs_id"] = fs_id
        return data

    def load_efficiency(self, fs_id: str = "fs-demo01") -> list[dict[str, Any]]:
        """ストレージ効率のモックデータを読み込む。

        Args:
            fs_id: デモ用ファイルシステム ID

        Returns:
            list[dict]: EfficiencyMetric 形式のデータリスト
        """
        data = self._load_fixture("efficiency.json")
        for record in data:
            record["fs_id"] = fs_id
        return data

    def load_tiering(self, fs_id: str = "fs-demo01") -> list[dict[str, Any]]:
        """ティアリングのモックデータを読み込む。

        Args:
            fs_id: デモ用ファイルシステム ID

        Returns:
            list[dict]: TieringMetric 形式のデータリスト
        """
        data = self._load_fixture("tiering.json")
        for record in data:
            record["fs_id"] = fs_id
        return data

    def load_snapshots(self, fs_id: str = "fs-demo01") -> list[dict[str, Any]]:
        """スナップショットのモックデータを読み込む。

        Args:
            fs_id: デモ用ファイルシステム ID

        Returns:
            list[dict]: SnapshotMetric 形式のデータリスト
        """
        data = self._load_fixture("snapshots.json")
        for record in data:
            record["fs_id"] = fs_id
        return data

    def _load_fixture(self, filename: str) -> Any:
        """JSON fixture ファイルを読み込む。

        Args:
            filename: フィクスチャファイル名

        Returns:
            パース済み JSON データ

        Raises:
            FileNotFoundError: ローカルファイルが見つからない場合
            RuntimeError: S3 からの読み込みに失敗した場合
        """
        if self._source == "local":
            return self._load_local(filename)
        elif self._source == "s3":
            return self._load_s3(filename)
        else:
            raise ValueError(f"Unknown source: {self._source}")

    def _load_local(self, filename: str) -> Any:
        """ローカルファイルシステムから JSON を読み込む。"""
        filepath = self._base_path / filename
        if not filepath.exists():
            logger.warning("Demo fixture not found: %s, returning empty list", filepath)
            return []

        with open(filepath, encoding="utf-8") as f:
            return json.load(f)

    def _load_s3(self, filename: str) -> Any:
        """S3 から JSON を読み込む。"""
        import boto3

        if not self._bucket:
            raise RuntimeError("S3 bucket not configured for DemoDataLoader")

        s3_key = f"{self._prefix}/{filename}"
        logger.info("Loading demo fixture from s3://%s/%s", self._bucket, s3_key)

        try:
            s3 = boto3.client("s3")
            response = s3.get_object(Bucket=self._bucket, Key=s3_key)
            body = response["Body"].read().decode("utf-8")
            return json.loads(body)
        except Exception as e:
            logger.warning("Failed to load demo fixture from S3: %s, returning empty", e)
            return []
