"""shared.integrations.lineage_integration — Data Lineage オプトイン統合ヘルパー

UC Processing Lambda が Data Lineage 記録にオプトインするためのヘルパーモジュール。
環境変数 LINEAGE_TABLE が設定されている場合のみ Lineage 記録を実行する。
書き込み失敗時はメイン処理を中断しない（Requirements 5.6, 13.2, 13.3）。

Usage (decorator):
    from shared.integrations.lineage_integration import track_lineage

    @track_lineage(uc_id="legal-compliance")
    def process_file(event, context):
        # ... メイン処理 ...
        return {
            "source_file_key": "/vol1/legal/contract.pdf",
            "output_keys": ["s3://bucket/output.json"],
            "status": "success",
        }

Usage (context manager):
    from shared.integrations.lineage_integration import LineageContext

    def process_file(event, context):
        with LineageContext(
            uc_id="legal-compliance",
            source_file_key="/vol1/legal/contract.pdf",
            execution_arn=event.get("execution_arn", ""),
        ) as lctx:
            # ... メイン処理 ...
            lctx.output_keys = ["s3://bucket/output.json"]
            lctx.status = "success"
            return result
"""

from __future__ import annotations

import functools
import logging
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Generator

logger = logging.getLogger(__name__)


def _is_lineage_enabled() -> bool:
    """環境変数 LINEAGE_TABLE が設定されているか確認する。"""
    table_name = os.environ.get("LINEAGE_TABLE", "")
    return bool(table_name.strip())


def _get_lineage_tracker():
    """LineageTracker インスタンスを生成する。

    Returns:
        LineageTracker instance or None if lineage is not enabled.
    """
    if not _is_lineage_enabled():
        return None

    try:
        from shared.lineage import LineageTracker

        table_name = os.environ["LINEAGE_TABLE"]
        return LineageTracker(table_name=table_name)
    except Exception as exc:
        logger.warning(
            "[LineageIntegration] Failed to create LineageTracker: %s. "
            "Lineage recording will be skipped.",
            exc,
        )
        return None


@dataclass
class LineageContext:
    """Data Lineage 記録用コンテキストマネージャー。

    コンテキスト内で処理結果を設定し、コンテキスト終了時に自動的に
    Lineage レコードを書き込む。書き込み失敗時はメイン処理を中断しない。

    Args:
        uc_id: UC 識別子
        source_file_key: ソースファイルキー
        execution_arn: Step Functions 実行 ARN
    """

    uc_id: str
    source_file_key: str
    execution_arn: str = ""
    output_keys: list[str] = field(default_factory=list)
    status: str = "success"
    metadata: dict[str, Any] | None = None

    _start_time_ns: int = field(default=0, init=False, repr=False)
    _lineage_id: str | None = field(default=None, init=False, repr=False)

    def __enter__(self) -> "LineageContext":
        self._start_time_ns = time.time_ns()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        # 例外が発生した場合、status を "failed" に設定
        if exc_type is not None:
            self.status = "failed"

        # Lineage 記録を試行（失敗してもメイン処理は中断しない）
        self._record_lineage()

        # 例外は伝播させる（メイン処理の例外を握りつぶさない）
        return False

    def _record_lineage(self) -> None:
        """Lineage レコードを書き込む。失敗時は警告ログのみ。"""
        tracker = _get_lineage_tracker()
        if tracker is None:
            return

        try:
            from shared.lineage import LineageRecord

            duration_ms = (time.time_ns() - self._start_time_ns) // 1_000_000
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

            record = LineageRecord(
                source_file_key=self.source_file_key,
                processing_timestamp=timestamp,
                step_functions_execution_arn=self.execution_arn,
                uc_id=self.uc_id,
                output_keys=self.output_keys,
                status=self.status,
                duration_ms=duration_ms,
                metadata=self.metadata,
            )
            self._lineage_id = tracker.record(record)
            logger.debug(
                "[LineageIntegration] Recorded lineage: %s", self._lineage_id
            )
        except Exception as exc:
            logger.warning(
                "[LineageIntegration] Failed to record lineage for uc=%s, "
                "source=%s: %s. Main processing continues.",
                self.uc_id,
                self.source_file_key,
                exc,
            )

    @property
    def lineage_id(self) -> str | None:
        """記録された lineage_id を返す。記録前は None。"""
        return self._lineage_id


def track_lineage(
    uc_id: str,
    source_key_field: str = "source_file_key",
    execution_arn_field: str = "execution_arn",
    output_keys_field: str = "output_keys",
    status_field: str = "status",
) -> Callable:
    """Data Lineage 記録デコレータ。

    デコレートされた関数の戻り値から Lineage 情報を抽出し、
    DynamoDB に記録する。LINEAGE_TABLE 環境変数が未設定の場合はスキップ。
    書き込み失敗時はメイン処理を中断しない。

    Args:
        uc_id: UC 識別子
        source_key_field: 戻り値 dict から source_file_key を取得するキー名
        execution_arn_field: 戻り値 dict から execution_arn を取得するキー名
        output_keys_field: 戻り値 dict から output_keys を取得するキー名
        status_field: 戻り値 dict から status を取得するキー名

    Returns:
        デコレータ関数

    Example:
        @track_lineage(uc_id="legal-compliance")
        def handler(event, context):
            return {
                "source_file_key": "/vol1/legal/contract.pdf",
                "output_keys": ["s3://bucket/output.json"],
                "status": "success",
            }
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            start_ns = time.time_ns()
            result = None
            status = "success"

            try:
                result = func(*args, **kwargs)
                # 戻り値から status を取得
                if isinstance(result, dict):
                    status = result.get(status_field, "success")
                return result
            except Exception:
                status = "failed"
                raise
            finally:
                _record_from_result(
                    result=result,
                    uc_id=uc_id,
                    status=status,
                    start_ns=start_ns,
                    source_key_field=source_key_field,
                    execution_arn_field=execution_arn_field,
                    output_keys_field=output_keys_field,
                    args=args,
                    kwargs=kwargs,
                )

        return wrapper

    return decorator


def _record_from_result(
    result: Any,
    uc_id: str,
    status: str,
    start_ns: int,
    source_key_field: str,
    execution_arn_field: str,
    output_keys_field: str,
    args: tuple = (),
    kwargs: dict | None = None,
) -> None:
    """関数の戻り値から Lineage レコードを書き込む。

    失敗時は警告ログのみ出力し、例外を raise しない。
    status が "failed" の場合（例外発生時）は、result が None でも
    args/kwargs から source_file_key の抽出を試みる。
    """
    tracker = _get_lineage_tracker()
    if tracker is None:
        return

    if kwargs is None:
        kwargs = {}

    try:
        from shared.lineage import LineageRecord

        source_file_key = ""
        execution_arn = ""
        output_keys: list[str] = []

        if isinstance(result, dict):
            source_file_key = result.get(source_key_field, "")
            execution_arn = result.get(execution_arn_field, "")
            output_keys = result.get(output_keys_field, [])
        elif status == "failed":
            # 例外発生時は args から event dict を探す
            for arg in args:
                if isinstance(arg, dict):
                    source_file_key = arg.get(source_key_field, "")
                    execution_arn = arg.get(execution_arn_field, "")
                    output_keys = arg.get(output_keys_field, [])
                    if source_file_key:
                        break
            # kwargs からも探す
            if not source_file_key:
                source_file_key = kwargs.get(source_key_field, "")
                execution_arn = kwargs.get(execution_arn_field, "")
                output_keys = kwargs.get(output_keys_field, [])
        else:
            logger.debug(
                "[LineageIntegration] Result is not a dict, skipping lineage for uc=%s",
                uc_id,
            )
            return

        if not source_file_key:
            logger.debug(
                "[LineageIntegration] No source_file_key found, skipping lineage for uc=%s",
                uc_id,
            )
            return

        duration_ms = (time.time_ns() - start_ns) // 1_000_000
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

        record = LineageRecord(
            source_file_key=source_file_key,
            processing_timestamp=timestamp,
            step_functions_execution_arn=execution_arn,
            uc_id=uc_id,
            output_keys=output_keys,
            status=status,
            duration_ms=duration_ms,
        )
        tracker.record(record)
    except Exception as exc:
        logger.warning(
            "[LineageIntegration] Failed to record lineage from result for uc=%s: %s. "
            "Main processing continues.",
            uc_id,
            exc,
        )
