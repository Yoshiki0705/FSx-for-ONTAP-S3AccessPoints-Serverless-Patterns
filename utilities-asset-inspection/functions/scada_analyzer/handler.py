"""電力・ユーティリティ (UC25) SCADA Analyzer Lambda ハンドラ

SCADA ログの時系列データを解析し、異常パターンを検出する。

異常検知閾値:
    - 電圧偏差: 公称値の ±5% (VOLTAGE_DEVIATION_PERCENT)
    - 負荷不均衡: 相間 10% 超 (LOAD_IMBALANCE_PERCENT)
    - 周波数偏差: 50/60 Hz から ±0.5 Hz (FREQUENCY_DEVIATION_HZ)

AI/ML サービス:
    - Amazon Athena: 時系列クエリ

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用)
    VOLTAGE_DEVIATION_PERCENT: 電圧偏差閾値 (default: 5.0)
    LOAD_IMBALANCE_PERCENT: 負荷不均衡閾値 (default: 10.0)
    FREQUENCY_DEVIATION_HZ: 周波数偏差閾値 (default: 0.5)
    ATHENA_DATABASE: Athena データベース名
    ATHENA_OUTPUT_LOCATION: Athena クエリ結果出力先
"""

from __future__ import annotations

import logging
import os
import time

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler
from shared.retry_handler import retry_with_backoff, RetryConfig, categorize_error

logger = logging.getLogger(__name__)

# SCADA 異常検知閾値 (デフォルト値)
SCADA_THRESHOLDS = {
    "voltage_deviation_percent": 5.0,
    "load_imbalance_percent": 10.0,
    "frequency_deviation_hz": 0.5,
}

# 異常タイプ
ANOMALY_VOLTAGE = "voltage_deviation"
ANOMALY_LOAD_IMBALANCE = "load_imbalance"
ANOMALY_FREQUENCY = "frequency_deviation"


def get_thresholds() -> dict[str, float]:
    """環境変数から閾値を取得する。

    Returns:
        dict: 閾値設定
    """
    return {
        "voltage_deviation_percent": float(
            os.environ.get("VOLTAGE_DEVIATION_PERCENT", SCADA_THRESHOLDS["voltage_deviation_percent"])
        ),
        "load_imbalance_percent": float(
            os.environ.get("LOAD_IMBALANCE_PERCENT", SCADA_THRESHOLDS["load_imbalance_percent"])
        ),
        "frequency_deviation_hz": float(
            os.environ.get("FREQUENCY_DEVIATION_HZ", SCADA_THRESHOLDS["frequency_deviation_hz"])
        ),
    }


def check_voltage_anomaly(
    voltage: float,
    nominal_voltage: float,
    threshold_percent: float,
) -> dict | None:
    """電圧偏差の異常チェック。

    Args:
        voltage: 測定電圧
        nominal_voltage: 公称電圧
        threshold_percent: 偏差閾値 (%)

    Returns:
        dict | None: 異常検出結果 or None
    """
    if nominal_voltage == 0:
        return None

    deviation_percent = abs(voltage - nominal_voltage) / nominal_voltage * 100

    if deviation_percent > threshold_percent:
        return {
            "anomaly_type": ANOMALY_VOLTAGE,
            "measured_value": voltage,
            "nominal_value": nominal_voltage,
            "deviation_percent": round(deviation_percent, 2),
            "threshold_percent": threshold_percent,
            "severity": "critical" if deviation_percent > threshold_percent * 2 else "major",
        }
    return None


def check_load_imbalance(
    phase_loads: list[float],
    threshold_percent: float,
) -> dict | None:
    """負荷不均衡の異常チェック。

    3 相の負荷不均衡を検出する。不均衡率 = (max - min) / avg * 100

    Args:
        phase_loads: 各相の負荷値リスト (3 相)
        threshold_percent: 不均衡閾値 (%)

    Returns:
        dict | None: 異常検出結果 or None
    """
    if not phase_loads or len(phase_loads) < 2:
        return None

    avg_load = sum(phase_loads) / len(phase_loads)
    if avg_load == 0:
        return None

    max_load = max(phase_loads)
    min_load = min(phase_loads)
    imbalance_percent = (max_load - min_load) / avg_load * 100

    if imbalance_percent > threshold_percent:
        return {
            "anomaly_type": ANOMALY_LOAD_IMBALANCE,
            "phase_loads": phase_loads,
            "imbalance_percent": round(imbalance_percent, 2),
            "threshold_percent": threshold_percent,
            "severity": "critical" if imbalance_percent > threshold_percent * 2 else "major",
        }
    return None


def check_frequency_anomaly(
    frequency: float,
    nominal_frequency: float,
    threshold_hz: float,
) -> dict | None:
    """周波数偏差の異常チェック。

    Args:
        frequency: 測定周波数
        nominal_frequency: 公称周波数 (50 or 60 Hz)
        threshold_hz: 偏差閾値 (Hz)

    Returns:
        dict | None: 異常検出結果 or None
    """
    deviation = abs(frequency - nominal_frequency)

    if deviation > threshold_hz:
        return {
            "anomaly_type": ANOMALY_FREQUENCY,
            "measured_value": frequency,
            "nominal_value": nominal_frequency,
            "deviation_hz": round(deviation, 3),
            "threshold_hz": threshold_hz,
            "severity": "critical" if deviation > threshold_hz * 2 else "major",
        }
    return None


def analyze_scada_records(
    records: list[dict],
    thresholds: dict[str, float],
) -> list[dict]:
    """SCADA レコード群を解析し異常を検出する。

    Args:
        records: SCADA レコードのリスト
        thresholds: 閾値設定

    Returns:
        list[dict]: 検出された異常リスト
    """
    anomalies: list[dict] = []

    for record in records:
        timestamp = record.get("timestamp", "")
        equipment_id = record.get("equipment_id", "")

        # 電圧チェック
        voltage = record.get("voltage")
        nominal_voltage = record.get("nominal_voltage", 100.0)
        if voltage is not None:
            anomaly = check_voltage_anomaly(
                float(voltage),
                float(nominal_voltage),
                thresholds["voltage_deviation_percent"],
            )
            if anomaly:
                anomaly["timestamp"] = timestamp
                anomaly["equipment_id"] = equipment_id
                anomalies.append(anomaly)

        # 負荷不均衡チェック
        phase_loads = record.get("phase_loads")
        if phase_loads and isinstance(phase_loads, list):
            anomaly = check_load_imbalance(
                [float(x) for x in phase_loads],
                thresholds["load_imbalance_percent"],
            )
            if anomaly:
                anomaly["timestamp"] = timestamp
                anomaly["equipment_id"] = equipment_id
                anomalies.append(anomaly)

        # 周波数チェック
        frequency = record.get("frequency")
        nominal_frequency = record.get("nominal_frequency", 50.0)
        if frequency is not None:
            anomaly = check_frequency_anomaly(
                float(frequency),
                float(nominal_frequency),
                thresholds["frequency_deviation_hz"],
            )
            if anomaly:
                anomaly["timestamp"] = timestamp
                anomaly["equipment_id"] = equipment_id
                anomalies.append(anomaly)

    return anomalies


def query_athena_scada(
    equipment_id: str,
    start_date: str,
    end_date: str,
    athena_client=None,
) -> list[dict]:
    """Athena で SCADA 時系列データをクエリする。

    Args:
        equipment_id: 設備 ID
        start_date: 開始日 (YYYY-MM-DD)
        end_date: 終了日 (YYYY-MM-DD)
        athena_client: Athena クライアント (テスト用)

    Returns:
        list[dict]: クエリ結果レコード
    """
    if athena_client is None:
        athena_client = boto3.client("athena")

    database = os.environ.get("ATHENA_DATABASE", "scada_db")
    output_location = os.environ.get(
        "ATHENA_OUTPUT_LOCATION", "s3://athena-results/"
    )

    query = (
        f"SELECT timestamp, equipment_id, voltage, nominal_voltage, "
        f"phase_a_load, phase_b_load, phase_c_load, "
        f"frequency, nominal_frequency "
        f"FROM scada_readings "
        f"WHERE equipment_id = '{equipment_id}' "
        f"AND timestamp BETWEEN '{start_date}' AND '{end_date}' "
        f"ORDER BY timestamp"
    )

    @retry_with_backoff(config=RetryConfig(max_attempts=3))
    def _start_query():
        return athena_client.start_query_execution(
            QueryString=query,
            QueryExecutionContext={"Database": database},
            ResultConfiguration={"OutputLocation": output_location},
        )

    execution = _start_query()
    execution_id = execution["QueryExecutionId"]

    # クエリ完了待機
    @retry_with_backoff(config=RetryConfig(max_attempts=3))
    def _get_results():
        status_response = athena_client.get_query_execution(
            QueryExecutionId=execution_id
        )
        state = status_response["QueryExecution"]["Status"]["State"]
        if state in ("QUEUED", "RUNNING"):
            raise Exception(f"Query still {state}")  # noqa: TRY002
        if state == "FAILED":
            reason = status_response["QueryExecution"]["Status"].get(
                "StateChangeReason", "Unknown"
            )
            raise Exception(f"Athena query failed: {reason}")  # noqa: TRY002

        return athena_client.get_query_results(QueryExecutionId=execution_id)

    results_response = _get_results()
    rows = results_response.get("ResultSet", {}).get("Rows", [])

    # ヘッダー行をスキップしてレコードに変換
    if len(rows) <= 1:
        return []

    headers = [col.get("VarCharValue", "") for col in rows[0].get("Data", [])]
    records: list[dict] = []

    for row in rows[1:]:
        values = [col.get("VarCharValue", "") for col in row.get("Data", [])]
        record = dict(zip(headers, values))

        # phase_loads を統合
        phase_a = record.pop("phase_a_load", None)
        phase_b = record.pop("phase_b_load", None)
        phase_c = record.pop("phase_c_load", None)
        if phase_a and phase_b and phase_c:
            record["phase_loads"] = [
                float(phase_a), float(phase_b), float(phase_c)
            ]

        records.append(record)

    return records


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """SCADA Analyzer Lambda

    SCADA ログファイルの時系列データを解析し、異常パターンを検出する。

    Input event:
        - objects: SCADA ログオブジェクトリスト (Discovery Lambda の出力)
        - records: 直接レコードを渡す場合 (Athena クエリ済み)

    Returns:
        dict: results, anomalies, anomaly_count, success_count, error_count
    """
    start_time = time.time()

    thresholds = get_thresholds()

    objects = event.get("objects", [])
    direct_records = event.get("records", [])

    logger.info(
        "SCADA analysis started: %d objects, thresholds=%s",
        len(objects),
        thresholds,
    )

    results: list[dict] = []
    all_anomalies: list[dict] = []
    success_count = 0
    error_count = 0

    # 直接レコードが渡された場合はそのまま解析
    if direct_records:
        anomalies = analyze_scada_records(direct_records, thresholds)
        all_anomalies.extend(anomalies)
        success_count = len(direct_records)

    # オブジェクトリストからの処理
    for obj in objects:
        key = obj.get("Key", "")
        equipment_id = obj.get("equipment_id")
        inspection_date = obj.get("inspection_date")

        try:
            # Athena 経由でのデータ取得が可能な場合
            if equipment_id and inspection_date:
                records = query_athena_scada(
                    equipment_id, inspection_date, inspection_date
                )
                anomalies = analyze_scada_records(records, thresholds)
            else:
                anomalies = []
                records = []

            results.append({
                "key": key,
                "equipment_id": equipment_id,
                "inspection_date": inspection_date,
                "status": "success",
                "record_count": len(records),
                "anomaly_count": len(anomalies),
                "anomalies": anomalies,
            })
            all_anomalies.extend(anomalies)
            success_count += 1

        except Exception as e:
            error_category = categorize_error(e)
            logger.warning(
                "SCADA analysis failed for %s (equipment=%s): %s [%s]",
                key,
                equipment_id,
                str(e),
                error_category.value,
            )

            results.append({
                "key": key,
                "equipment_id": equipment_id,
                "inspection_date": inspection_date,
                "status": "error",
                "error_type": error_category.value,
                "error_message": str(e),
            })
            error_count += 1

    processing_duration_ms = int((time.time() - start_time) * 1000)

    logger.info(
        "SCADA analysis completed: success=%d, errors=%d, anomalies=%d, duration=%dms",
        success_count,
        error_count,
        len(all_anomalies),
        processing_duration_ms,
    )

    # EMF メトリクス
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="processing")
    metrics.set_dimension("UseCase", "utilities-asset-inspection")
    metrics.set_dimension("Stage", "scada-analysis")
    metrics.put_metric("ProcessingDuration", float(processing_duration_ms), "Milliseconds")
    metrics.put_metric("SuccessCount", float(success_count), "Count")
    metrics.put_metric("ErrorCount", float(error_count), "Count")
    metrics.put_metric("AnomalyCount", float(len(all_anomalies)), "Count")
    metrics.flush()

    return {
        "results": results,
        "anomalies": all_anomalies,
        "anomaly_count": len(all_anomalies),
        "success_count": success_count,
        "error_count": error_count,
        "processing_duration_ms": processing_duration_ms,
    }
