"""shared.observability - X-Ray トレーシング + CloudWatch EMF ヘルパーモジュール

AWS X-Ray カスタムサブセグメントと CloudWatch Embedded Metric Format (EMF) の
ヘルパーを提供する。全 UC 横断で可観測性を統一的に適用するための共通モジュール。

設計方針:
- X-Ray SDK が未インストールまたは ENABLE_XRAY=false の場合は no-op パススルー
- EMF は X-Ray とは独立して動作（X-Ray 無効時も EMF メトリクスは出力可能）
- 機密データ（ファイル内容、PII、認証情報）を含めない

Usage:
    from shared.observability import xray_subsegment, EmfMetrics, trace_lambda_handler
"""

from __future__ import annotations

import functools
import json
import logging
import os
import re
import time
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger(__name__)

# Metric name validation: max 256 chars, only alphanumeric + underscore
_METRIC_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]+$")
_METRIC_NAME_MAX_LENGTH = 256

# Valid EMF metric units
_VALID_UNITS = {"Count", "Milliseconds", "Bytes", "None"}


def _is_xray_enabled() -> bool:
    """X-Ray が有効かどうかを判定する。"""
    return os.environ.get("ENABLE_XRAY", "true").lower() != "false"


@contextmanager
def xray_subsegment(
    name: str,
    annotations: dict | None = None,
    metadata: dict | None = None,
):
    """X-Ray カスタムサブセグメントのコンテキストマネージャ。

    X-Ray SDK が未インストールまたは ENABLE_XRAY=false の場合は
    no-op パススルーとして動作する（エラーなし）。

    Args:
        name: サブセグメント名
        annotations: X-Ray アノテーション (service_name, operation, use_case 等)
        metadata: X-Ray メタデータ
    """
    if not _is_xray_enabled():
        yield
        return

    try:
        from aws_xray_sdk.core import xray_recorder  # noqa: F401

        subsegment = xray_recorder.begin_subsegment(name)
        try:
            if annotations:
                for key, value in annotations.items():
                    subsegment.put_annotation(key, value)
            if metadata:
                for key, value in metadata.items():
                    subsegment.put_metadata(key, value)
            yield subsegment
        except Exception as e:
            subsegment.add_exception(e)
            raise
        finally:
            xray_recorder.end_subsegment()
    except ImportError:
        logger.debug("aws_xray_sdk not installed, X-Ray subsegment '%s' skipped", name)
        yield


class EmfMetrics:
    """CloudWatch Embedded Metric Format (EMF) メトリクス出力クラス。

    CloudWatch EMF 仕様に準拠した構造化 JSON ログ行を stdout に出力する。
    CloudWatch Logs が自動的にメトリクスを抽出する。

    Usage:
        metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="discovery")
        metrics.set_dimension("UseCase", "retail-catalog")
        metrics.put_metric("FilesProcessed", 42, "Count")
        metrics.flush()
    """

    def __init__(
        self,
        namespace: str = "FSxN-S3AP-Patterns",
        service: str | None = None,
    ):
        """EmfMetrics を初期化する。

        Args:
            namespace: CloudWatch メトリクス名前空間
            service: サービス名（FunctionName ディメンションに使用）
        """
        self._namespace = namespace
        self._service = service
        self._metrics: list[dict[str, Any]] = []
        self._dimensions: dict[str, str] = {}
        self._properties: dict[str, Any] = {}

        # デフォルトディメンション設定
        if service:
            self._dimensions["FunctionName"] = service
        environment = os.environ.get("ENVIRONMENT", "dev")
        self._dimensions["Environment"] = environment

    def put_metric(self, name: str, value: float, unit: str = "None") -> None:
        """メトリクスを追加する。

        Args:
            name: メトリクス名 (max 256 chars, alphanumeric + underscore only)
            value: メトリクス値
            unit: 単位 (Count, Milliseconds, Bytes, None)

        Raises:
            ValueError: メトリクス名が不正な場合
        """
        self._validate_metric_name(name)
        if unit not in _VALID_UNITS:
            raise ValueError(
                f"Invalid unit '{unit}'. Must be one of: {', '.join(sorted(_VALID_UNITS))}"
            )
        self._metrics.append({"Name": name, "Unit": unit, "Value": value})

    def set_dimension(self, name: str, value: str) -> None:
        """ディメンションを設定する。

        Args:
            name: ディメンション名 (UseCase, FunctionName, Environment)
            value: ディメンション値
        """
        self._dimensions[name] = value

    def set_property(self, name: str, value: Any) -> None:
        """追加プロパティを設定する（メトリクスではない）。

        Args:
            name: プロパティ名
            value: プロパティ値
        """
        self._properties[name] = value

    def flush(self) -> None:
        """EMF 仕様準拠の構造化 JSON ログ行を stdout に出力する。

        出力フォーマット:
        {
            "_aws": {
                "Timestamp": <epoch_ms>,
                "CloudWatchMetrics": [{
                    "Namespace": "<namespace>",
                    "Dimensions": [["dim1", "dim2", ...]],
                    "Metrics": [{"Name": "metric1", "Unit": "Count"}, ...]
                }]
            },
            "dim1": "val1",
            "metric1": value1,
            "prop1": "val1",
            ...
        }
        """
        if not self._metrics:
            return

        timestamp_ms = int(time.time() * 1000)

        # Build metrics definitions (without Value)
        metric_definitions = [
            {"Name": m["Name"], "Unit": m["Unit"]} for m in self._metrics
        ]

        # Build EMF structure
        emf_dict: dict[str, Any] = {
            "_aws": {
                "Timestamp": timestamp_ms,
                "CloudWatchMetrics": [
                    {
                        "Namespace": self._namespace,
                        "Dimensions": [list(self._dimensions.keys())],
                        "Metrics": metric_definitions,
                    }
                ],
            },
        }

        # Add dimensions as top-level keys
        for dim_name, dim_value in self._dimensions.items():
            emf_dict[dim_name] = dim_value

        # Add metric values as top-level keys
        for metric in self._metrics:
            emf_dict[metric["Name"]] = metric["Value"]

        # Add properties as top-level keys
        for prop_name, prop_value in self._properties.items():
            emf_dict[prop_name] = prop_value

        print(json.dumps(emf_dict))

        # Reset metrics after flush
        self._metrics = []
        self._properties = {}

    @staticmethod
    def _validate_metric_name(name: str) -> None:
        """メトリクス名のバリデーション。

        Args:
            name: メトリクス名

        Raises:
            ValueError: メトリクス名が不正な場合
        """
        if not name:
            raise ValueError("Metric name must not be empty")
        if len(name) > _METRIC_NAME_MAX_LENGTH:
            raise ValueError(
                f"Metric name exceeds {_METRIC_NAME_MAX_LENGTH} characters: "
                f"'{name[:50]}...' ({len(name)} chars)"
            )
        if not _METRIC_NAME_PATTERN.match(name):
            raise ValueError(
                f"Metric name contains invalid characters: '{name}'. "
                "Only alphanumeric and underscore allowed."
            )


def trace_lambda_handler(func):
    """Lambda ハンドラー用トレーシングデコレータ。

    X-Ray サブセグメントの自動作成と標準 EMF メトリクス出力を行う。
    X-Ray が無効の場合でも EMF メトリクスは出力される（独立動作）。

    出力メトリクス:
    - ProcessingDuration (Milliseconds): ハンドラー実行時間
    - ProcessingSuccess (Count): 成功回数 (1 or 0)
    - ProcessingErrors (Count): エラー回数 (1 or 0)

    アノテーション:
    - use_case: USE_CASE 環境変数から取得
    - service_name: 関数名
    - operation: "lambda_handler"
    """

    @functools.wraps(func)
    def wrapper(event, context):
        use_case = os.environ.get("USE_CASE", "unknown")
        function_name = str(getattr(context, "function_name", func.__name__))

        metrics = EmfMetrics(
            namespace="FSxN-S3AP-Patterns",
            service=function_name,
        )
        metrics.set_dimension("UseCase", use_case)

        start_time = time.time()
        success = False

        annotations = {
            "use_case": use_case,
            "service_name": function_name,
            "operation": "lambda_handler",
        }

        try:
            with xray_subsegment(
                name=f"{function_name}_handler",
                annotations=annotations,
            ):
                result = func(event, context)
                success = True
                return result
        except Exception:
            raise
        finally:
            duration_ms = (time.time() - start_time) * 1000
            metrics.put_metric("ProcessingDuration", duration_ms, "Milliseconds")
            metrics.put_metric("ProcessingSuccess", 1.0 if success else 0.0, "Count")
            metrics.put_metric("ProcessingErrors", 0.0 if success else 1.0, "Count")
            metrics.flush()

    return wrapper
