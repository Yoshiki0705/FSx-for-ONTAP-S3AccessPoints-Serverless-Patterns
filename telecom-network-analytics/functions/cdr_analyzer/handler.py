"""通信業界 (UC18) CDR Analyzer Lambda ハンドラ

CDR (Call Detail Record) ファイルをパースし、通話メタデータを抽出する。
CSV/ASN.1デコード済み/Parquet 形式に対応し、Athena を使用して
トラフィック統計（時間あたり通話量、平均通話時間、ピーク同時通話数）を計算する。

処理フロー:
    1. S3 AP からファイル取得
    2. ファイル形式に応じたパース (CSV / ASN.1 / Parquet)
    3. コールメタデータ抽出 (caller_id, callee_id, duration, timestamp, cell_tower_id)
    4. Athena による統計クエリ実行 (retry_handler 適用)
    5. 結果を S3 出力バケットに書き出し
    6. パース失敗時は errors/cdr/ プレフィックス下にエラー記録し継続

Requirements: 2.2, 2.5, 2.6, 13.6

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用)
    ATHENA_DATABASE: Athena データベース名
    ATHENA_WORKGROUP: Athena ワークグループ
    ATHENA_OUTPUT_LOCATION: Athena クエリ結果 S3 パス
    OUTPUT_BUCKET: 出力バケット名
    SNS_TOPIC_ARN: 通知先 SNS トピック ARN
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import xray_subsegment, EmfMetrics, trace_lambda_handler
from shared.retry_handler import execute_with_retry, RetryConfig, RetryExhaustedError
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)

# CDR メタデータフィールド定義
CDR_FIELDS = ["caller_id", "callee_id", "duration", "timestamp", "cell_tower_id"]

# CSV ヘッダーマッピング (よくある CDR CSV カラム名 → 標準フィールド名)
CSV_HEADER_MAP = {
    "caller_id": "caller_id",
    "calling_number": "caller_id",
    "a_number": "caller_id",
    "callee_id": "callee_id",
    "called_number": "callee_id",
    "b_number": "callee_id",
    "duration": "duration",
    "call_duration": "duration",
    "duration_seconds": "duration",
    "timestamp": "timestamp",
    "start_time": "timestamp",
    "call_start": "timestamp",
    "cell_tower_id": "cell_tower_id",
    "tower_id": "cell_tower_id",
    "cell_id": "cell_tower_id",
    "lac_ci": "cell_tower_id",
}

# デフォルト Athena リトライ設定
ATHENA_RETRY_CONFIG = RetryConfig(
    max_attempts=3,
    initial_interval_seconds=2.0,
    backoff_rate=2.0,
)


def parse_csv_cdr(content: str) -> list[dict[str, Any]]:
    """CSV 形式の CDR ファイルをパースする。

    Args:
        content: CSV ファイルの内容文字列

    Returns:
        list[dict]: パースされた CDR レコードのリスト

    Raises:
        ValueError: CSVパースに失敗した場合
    """
    records = []
    reader = csv.DictReader(io.StringIO(content))

    if not reader.fieldnames:
        raise ValueError("CSV file has no header row")

    # ヘッダーを正規化して標準フィールドにマッピング
    field_mapping = {}
    for header in reader.fieldnames:
        normalized = header.strip().lower().replace(" ", "_")
        if normalized in CSV_HEADER_MAP:
            field_mapping[header] = CSV_HEADER_MAP[normalized]

    for row in reader:
        record = {}
        for original_header, standard_field in field_mapping.items():
            value = row.get(original_header, "").strip()
            if standard_field == "duration":
                try:
                    record[standard_field] = float(value) if value else 0.0
                except (ValueError, TypeError):
                    record[standard_field] = 0.0
            else:
                record[standard_field] = value
        # 必須フィールドが少なくとも caller_id と timestamp があれば有効
        if record.get("caller_id") or record.get("timestamp"):
            records.append(record)

    return records


def parse_asn1_cdr(content: bytes) -> list[dict[str, Any]]:
    """ASN.1 デコード済みの CDR ファイルをパースする。

    ASN.1 デコード済みファイルは改行区切りの JSON Lines 形式を想定。
    各行は1つの CDR レコードを表す JSON オブジェクト。

    Args:
        content: ASN.1 デコード済みファイルの内容 (バイト列)

    Returns:
        list[dict]: パースされた CDR レコードのリスト

    Raises:
        ValueError: パースに失敗した場合
    """
    records = []
    text = content.decode("utf-8", errors="replace")

    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            record = {}
            for field in CDR_FIELDS:
                if field in obj:
                    record[field] = obj[field]
                # ASN.1 フィールド名のバリアント対応
                elif field == "caller_id" and "callingPartyNumber" in obj:
                    record[field] = obj["callingPartyNumber"]
                elif field == "callee_id" and "calledPartyNumber" in obj:
                    record[field] = obj["calledPartyNumber"]
                elif field == "duration" and "callDuration" in obj:
                    try:
                        record[field] = float(obj["callDuration"])
                    except (ValueError, TypeError):
                        record[field] = 0.0
                elif field == "timestamp" and "answerTime" in obj:
                    record[field] = obj["answerTime"]
                elif field == "cell_tower_id" and "cellId" in obj:
                    record[field] = obj["cellId"]

            if record.get("caller_id") or record.get("timestamp"):
                records.append(record)
        except json.JSONDecodeError:
            continue

    if not records:
        raise ValueError("No valid ASN.1 decoded CDR records found")

    return records


def parse_parquet_cdr(content: bytes) -> list[dict[str, Any]]:
    """Parquet 形式の CDR ファイルをパースする。

    pyarrow が利用可能であれば使用し、なければ簡易的なメタデータ抽出を行う。

    Args:
        content: Parquet ファイルのバイナリ内容

    Returns:
        list[dict]: パースされた CDR レコードのリスト

    Raises:
        ValueError: パースに失敗した場合
    """
    try:
        import pyarrow.parquet as pq

        buffer = io.BytesIO(content)
        table = pq.read_table(buffer)
        df_dict = table.to_pydict()

        # カラム名を正規化してマッピング
        column_mapping = {}
        for col in df_dict.keys():
            normalized = col.strip().lower().replace(" ", "_")
            if normalized in CSV_HEADER_MAP:
                column_mapping[col] = CSV_HEADER_MAP[normalized]

        num_rows = len(next(iter(df_dict.values()))) if df_dict else 0
        records = []
        for i in range(num_rows):
            record = {}
            for original_col, standard_field in column_mapping.items():
                value = df_dict[original_col][i]
                if standard_field == "duration":
                    try:
                        record[standard_field] = float(value) if value is not None else 0.0
                    except (ValueError, TypeError):
                        record[standard_field] = 0.0
                else:
                    record[standard_field] = str(value) if value is not None else ""
            if record.get("caller_id") or record.get("timestamp"):
                records.append(record)

        return records

    except ImportError:
        raise ValueError("pyarrow is not installed. Parquet file parsing requires pyarrow library.")
    except Exception as e:
        raise ValueError(f"Failed to parse Parquet CDR file: {e}") from e


def parse_cdr_file(key: str, content: bytes) -> list[dict[str, Any]]:
    """ファイル拡張子に基づいて適切なパーサーを選択し CDR をパースする。

    Args:
        key: S3 オブジェクトキー (拡張子判定に使用)
        content: ファイルの内容 (バイト列)

    Returns:
        list[dict]: パースされた CDR レコードのリスト

    Raises:
        ValueError: サポートされていない形式またはパース失敗
    """
    key_lower = key.lower()

    if key_lower.endswith(".csv"):
        text = content.decode("utf-8", errors="replace")
        return parse_csv_cdr(text)
    elif key_lower.endswith(".asn1"):
        return parse_asn1_cdr(content)
    elif key_lower.endswith(".parquet"):
        return parse_parquet_cdr(content)
    else:
        raise ValueError(f"Unsupported CDR file format: {key}")


def compute_traffic_statistics(records: list[dict[str, Any]]) -> dict[str, Any]:
    """ローカルでトラフィック統計を計算する。

    計算対象:
    - call_volume_per_hour: 時間帯別通話件数
    - average_duration: 平均通話時間（秒）
    - peak_concurrent_calls: ピーク同時通話数の推定値

    Args:
        records: CDR レコードのリスト

    Returns:
        dict: トラフィック統計
    """
    if not records:
        return {
            "call_volume_per_hour": {},
            "average_duration": 0.0,
            "peak_concurrent_calls": 0,
            "total_records": 0,
        }

    # 時間帯別通話件数
    hourly_volume: dict[str, int] = {}
    durations: list[float] = []

    for record in records:
        # timestamp から時間帯を抽出
        ts = record.get("timestamp", "")
        if ts:
            try:
                # 複数の日時フォーマットに対応
                for fmt in (
                    "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%dT%H:%M:%S",
                    "%Y-%m-%dT%H:%M:%SZ",
                    "%Y/%m/%d %H:%M:%S",
                ):
                    try:
                        dt = datetime.strptime(ts[:19], fmt[: len(ts[:19])])
                        hour_key = dt.strftime("%Y-%m-%d %H:00")
                        hourly_volume[hour_key] = hourly_volume.get(hour_key, 0) + 1
                        break
                    except ValueError:
                        continue
            except Exception:
                pass

        # 通話時間
        duration = record.get("duration", 0.0)
        if isinstance(duration, (int, float)) and duration >= 0:
            durations.append(float(duration))

    # 平均通話時間
    average_duration = sum(durations) / len(durations) if durations else 0.0

    # ピーク同時通話数の推定（最大時間帯の通話件数 / 60 を概算値として使用）
    peak_hourly = max(hourly_volume.values()) if hourly_volume else 0
    peak_concurrent_estimate = max(1, peak_hourly // 60) if peak_hourly > 0 else 0

    return {
        "call_volume_per_hour": hourly_volume,
        "average_duration": round(average_duration, 2),
        "peak_concurrent_calls": peak_concurrent_estimate,
        "total_records": len(records),
    }


def run_athena_traffic_query(
    athena_client,
    database: str,
    workgroup: str,
    output_location: str,
    file_key: str,
) -> dict[str, Any] | None:
    """Athena でトラフィック統計クエリを実行する（リトライ付き）。

    Args:
        athena_client: boto3 Athena クライアント
        database: Athena データベース名
        workgroup: Athena ワークグループ
        output_location: Athena クエリ結果出力先 S3 パス
        file_key: 対象ファイルキー

    Returns:
        dict | None: Athena クエリ結果 (利用可能な場合)。None の場合はローカル計算を使用。
    """
    query = f"""
    SELECT
        date_trunc('hour', from_iso8601_timestamp(timestamp)) AS hour_bucket,
        COUNT(*) AS call_count,
        AVG(duration) AS avg_duration,
        MAX(concurrent_calls) AS peak_concurrent
    FROM cdr_records
    WHERE file_key = '{file_key}'
    GROUP BY date_trunc('hour', from_iso8601_timestamp(timestamp))
    ORDER BY hour_bucket
    """

    def _start_query():
        return athena_client.start_query_execution(
            QueryString=query,
            QueryExecutionContext={"Database": database},
            WorkGroup=workgroup,
            ResultConfiguration={"OutputLocation": output_location},
        )

    try:
        response = execute_with_retry(_start_query, config=ATHENA_RETRY_CONFIG)
        query_execution_id = response["QueryExecutionId"]

        # クエリ完了を待機
        def _get_status():
            return athena_client.get_query_execution(QueryExecutionId=query_execution_id)

        # 簡易ポーリング (最大 30 秒)
        for _ in range(15):
            time.sleep(2)
            status_resp = _get_status()
            state = status_resp["QueryExecution"]["Status"]["State"]
            if state == "SUCCEEDED":
                return {"query_execution_id": query_execution_id, "status": "SUCCEEDED"}
            elif state in ("FAILED", "CANCELLED"):
                logger.warning(
                    "Athena query %s ended with state: %s",
                    query_execution_id,
                    state,
                )
                return None

        logger.warning("Athena query %s timed out", query_execution_id)
        return None

    except RetryExhaustedError as e:
        logger.error("Athena query failed after retries: %s", str(e))
        raise
    except Exception as e:
        logger.warning("Athena query skipped (non-retryable): %s", str(e))
        return None


def record_parse_error(
    s3_client,
    output_bucket: str,
    file_key: str,
    error_category: str,
    error_details: str,
) -> None:
    """CDR パースエラーを errors/cdr/ プレフィックス下に記録する。

    Requirement 2.5: パース失敗時はエラー記録して残ファイル処理を継続。

    Args:
        s3_client: boto3 S3 クライアント
        output_bucket: 出力バケット名
        file_key: 失敗したファイルのキー
        error_category: エラーカテゴリ (parse_error, unsupported_format, etc.)
        error_details: エラー詳細メッセージ
    """
    error_record = {
        "file_path": file_key,
        "error_category": error_category,
        "error_details": error_details,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # エラーキー生成: errors/cdr/{date}/{file_basename}.json
    date_prefix = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    file_basename = file_key.rsplit("/", 1)[-1] if "/" in file_key else file_key
    error_key = f"errors/cdr/{date_prefix}/{file_basename}.error.json"

    try:
        s3_client.put_object(
            Bucket=output_bucket,
            Key=error_key,
            Body=json.dumps(error_record, ensure_ascii=False),
            ContentType="application/json",
        )
        logger.info("Parse error recorded: %s → %s", file_key, error_key)
    except Exception as e:
        logger.error("Failed to record parse error for %s: %s", file_key, str(e))


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """CDR Analyzer Lambda ハンドラ

    Step Functions Map State から呼び出され、個々の CDR ファイルを処理する。

    Event 形式:
        {
            "key": "cdr/2026/06/02/morning.csv",
            "size": 1048576,
            "manifest_key": "manifests/2026/06/02/xxx.json"
        }

    Processing Flow:
        1. S3 AP からファイル取得
        2. CDR パース (CSV / ASN.1 / Parquet)
        3. メタデータ抽出
        4. トラフィック統計計算 (Athena またはローカル)
        5. 結果を S3 出力に書き出し
        6. パースエラー時は errors/cdr/ に記録して継続

    Returns:
        dict: 処理結果 (status, records_count, statistics, errors)
    """
    file_key = event.get("key", event.get("Key", ""))
    file_size = event.get("size", event.get("Size", 0))

    logger.info(
        "CDR Analyzer started: key=%s, size=%d",
        file_key,
        file_size,
    )

    # S3 AP / 出力設定
    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    output_bucket = os.environ.get("OUTPUT_BUCKET", "")
    s3_client = boto3.client("s3")

    # Athena 設定 (オプション)
    athena_database = os.environ.get("ATHENA_DATABASE", "")
    athena_workgroup = os.environ.get("ATHENA_WORKGROUP", "primary")
    athena_output_location = os.environ.get("ATHENA_OUTPUT_LOCATION", "")

    # Step 1: ファイル取得
    try:
        with xray_subsegment(
            name="s3ap_get_object",
            annotations={
                "service_name": "s3",
                "operation": "GetObject",
                "use_case": "telecom-network-analytics",
            },
        ):
            response = s3ap.get_object(file_key)
            content = response["Body"].read()
            response["Body"].close()
    except Exception as e:
        logger.error("Failed to retrieve file %s: %s", file_key, str(e))
        return {
            "key": file_key,
            "status": "error",
            "error_category": "retrieval_error",
            "error_details": str(e),
        }

    # Step 2: CDR パース
    try:
        with xray_subsegment(
            name="cdr_parse",
            annotations={
                "service_name": "cdr_parser",
                "operation": "Parse",
                "use_case": "telecom-network-analytics",
                "file_format": file_key.rsplit(".", 1)[-1] if "." in file_key else "unknown",
            },
        ):
            records = parse_cdr_file(file_key, content)
    except (ValueError, UnicodeDecodeError, Exception) as e:
        # Requirement 2.5: パース失敗時はエラー記録して継続
        error_category = "parse_error"
        if "Unsupported" in str(e):
            error_category = "unsupported_format"

        logger.warning(
            "CDR parse failed for %s (%s): %s",
            file_key,
            error_category,
            str(e),
        )

        if output_bucket:
            record_parse_error(
                s3_client=s3_client,
                output_bucket=output_bucket,
                file_key=file_key,
                error_category=error_category,
                error_details=str(e),
            )

        return {
            "key": file_key,
            "status": "parse_error",
            "error_category": error_category,
            "error_details": str(e),
            "records_count": 0,
        }

    # Step 3: トラフィック統計計算
    with xray_subsegment(
        name="compute_statistics",
        annotations={
            "service_name": "cdr_analyzer",
            "operation": "ComputeStatistics",
            "use_case": "telecom-network-analytics",
        },
    ):
        statistics = compute_traffic_statistics(records)

    # Step 4: Athena クエリ (設定がある場合のみ)
    athena_result = None
    if athena_database and athena_output_location:
        try:
            athena_client = boto3.client("athena")
            with xray_subsegment(
                name="athena_query",
                annotations={
                    "service_name": "athena",
                    "operation": "StartQueryExecution",
                    "use_case": "telecom-network-analytics",
                },
            ):
                athena_result = run_athena_traffic_query(
                    athena_client=athena_client,
                    database=athena_database,
                    workgroup=athena_workgroup,
                    output_location=athena_output_location,
                    file_key=file_key,
                )
        except RetryExhaustedError as e:
            # Requirement 2.6: リトライ使い果たした場合はエラー記録
            logger.error(
                "Athena query failed after all retries for %s: %s",
                file_key,
                str(e),
            )
            if output_bucket:
                record_parse_error(
                    s3_client=s3_client,
                    output_bucket=output_bucket,
                    file_key=file_key,
                    error_category="athena_retry_exhausted",
                    error_details=str(e),
                )

    # Step 5: 結果書き出し
    # PII 保護: caller_id/callee_id をマスクしてサンプル出力
    # (通信データは個人通信記録のため、生データの出力は禁止)
    masked_sample = []
    for record in records[:5]:
        masked = {
            "caller_id": "***MASKED***",
            "callee_id": "***MASKED***",
            "duration": record.get("duration"),
            "timestamp": record.get("timestamp"),
            "cell_tower_id": record.get("cell_tower_id"),
        }
        masked_sample.append(masked)

    result = {
        "key": file_key,
        "status": "success",
        "records_count": len(records),
        "statistics": statistics,
        "athena_result": athena_result,
        "metadata_sample": masked_sample,
        "processing_timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if output_bucket:
        date_prefix = datetime.now(timezone.utc).strftime("%Y/%m/%d")
        file_basename = file_key.rsplit("/", 1)[-1] if "/" in file_key else file_key
        result_key = f"results/cdr/{date_prefix}/{file_basename}.result.json"
        try:
            s3_client.put_object(
                Bucket=output_bucket,
                Key=result_key,
                Body=json.dumps(result, default=str, ensure_ascii=False),
                ContentType="application/json",
            )
        except Exception as e:
            logger.error("Failed to write result for %s: %s", file_key, str(e))

    # Step 6: EMF メトリクス
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="cdr_analyzer")
    metrics.set_dimension("UseCase", "telecom-network-analytics")
    metrics.put_metric("RecordsProcessed", float(len(records)), "Count")
    metrics.put_metric("FilesProcessed", 1.0, "Count")
    metrics.flush()

    logger.info(
        "CDR Analyzer completed: key=%s, records=%d, status=%s",
        file_key,
        len(records),
        result["status"],
    )

    return result
