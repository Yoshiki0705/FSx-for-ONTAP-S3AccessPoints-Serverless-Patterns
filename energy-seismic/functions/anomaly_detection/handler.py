"""エネルギー / 石油・ガス 坑井ログ異常検知 Lambda ハンドラ

坑井ログファイル（LAS / CSV 形式）のセンサー読み取り値を統計的手法
（標準偏差閾値）で異常検知する。

LAS (Log ASCII Standard) ファイル構造:
    - ~V: バージョンセクション
    - ~W: 坑井情報セクション（坑井名、位置、座標）
    - ~C: カーブ情報セクション（カーブ名定義: DEPT, GR, NPHI, RHOB 等）
    - ~A: データセクション（スペース/タブ区切り数値データ）

異常検知アルゴリズム:
    各センサーカラムについて:
    1. 平均値と標準偏差を計算
    2. |value - mean| > threshold_std * std_dev の読み取り値をフラグ
    3. threshold_std は環境変数で設定可能（デフォルト: 3.0）

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    OUTPUT_BUCKET: S3 出力バケット名
    ANOMALY_THRESHOLD_STD: 異常検知閾値（標準偏差の倍数、デフォルト: 3.0）
"""

from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime, timezone
from pathlib import PurePosixPath

import boto3

from shared.exceptions import lambda_error_handler
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)

DEFAULT_ANOMALY_THRESHOLD_STD = 3.0


def _parse_las_file(content: str) -> tuple[list[str], list[list[float]]]:
    """LAS ファイルをパースしてカーブ名とデータを返す

    Args:
        content: LAS ファイルの文字列内容

    Returns:
        tuple: (curve_names, data_rows)
            - curve_names: カーブ名のリスト（例: ["DEPT", "GR", "NPHI", "RHOB"]）
            - data_rows: 数値データの行リスト

    Raises:
        ValueError: LAS ファイルのフォーマットが不正な場合
    """
    curve_names: list[str] = []
    data_rows: list[list[float]] = []
    current_section = ""

    lines = content.split("\n")

    for line in lines:
        stripped = line.strip()

        # 空行・コメント行をスキップ
        if not stripped or stripped.startswith("#"):
            continue

        # セクションヘッダー検出
        if stripped.startswith("~"):
            section_char = stripped[1:2].upper()
            current_section = section_char
            continue

        # カーブ情報セクション（~C）
        if current_section == "C":
            # フォーマット: MNEMONIC.UNIT  DATA : DESCRIPTION
            # 例: GR  .GAPI     : Gamma Ray
            parts = stripped.split(".")
            if parts:
                mnemonic = parts[0].strip()
                if mnemonic:
                    curve_names.append(mnemonic)

        # データセクション（~A）
        elif current_section == "A":
            # スペース/タブ区切りの数値データ
            values = stripped.split()
            row: list[float] = []
            for v in values:
                try:
                    val = float(v)
                    row.append(val)
                except ValueError:
                    row.append(float("nan"))
            if row:
                data_rows.append(row)

    if not curve_names:
        raise ValueError("No curve definitions found in LAS file (~C section)")
    if not data_rows:
        raise ValueError("No data found in LAS file (~A section)")

    return curve_names, data_rows


def _parse_csv_file(content: str) -> tuple[list[str], list[list[float]]]:
    """CSV ファイルをパースしてカラム名とデータを返す

    Args:
        content: CSV ファイルの文字列内容

    Returns:
        tuple: (column_names, data_rows)

    Raises:
        ValueError: CSV ファイルが空またはヘッダーがない場合
    """
    lines = content.strip().split("\n")
    if not lines:
        raise ValueError("CSV file is empty")

    # ヘッダー行
    header_line = lines[0].strip()
    column_names = [col.strip() for col in header_line.split(",")]

    if not column_names:
        raise ValueError("No column headers found in CSV file")

    # データ行
    data_rows: list[list[float]] = []
    for line in lines[1:]:
        stripped = line.strip()
        if not stripped:
            continue
        values = stripped.split(",")
        row: list[float] = []
        for v in values:
            try:
                val = float(v.strip())
                row.append(val)
            except ValueError:
                row.append(float("nan"))
        if row:
            data_rows.append(row)

    if not data_rows:
        raise ValueError("No data rows found in CSV file")

    return column_names, data_rows


def _detect_anomalies(
    curve_names: list[str],
    data_rows: list[list[float]],
    threshold_std: float,
) -> list[dict]:
    """統計的手法で異常値を検出する

    各センサーカラムについて平均値と標準偏差を計算し、
    閾値を超える読み取り値を異常としてフラグする。

    Args:
        curve_names: カーブ/カラム名のリスト
        data_rows: 数値データの行リスト
        threshold_std: 標準偏差の閾値倍数

    Returns:
        list[dict]: 検出された異常のリスト
    """
    anomalies: list[dict] = []

    if not data_rows or not curve_names:
        return anomalies

    num_columns = len(curve_names)

    # 最初のカラムは深度（DEPT）と仮定
    depth_col_idx = 0

    # 各センサーカラムについて統計計算と異常検知
    for col_idx in range(1, min(num_columns, len(data_rows[0]))):
        # 有効な値のみ収集（NaN を除外）
        valid_values: list[float] = []
        for row in data_rows:
            if col_idx < len(row) and not math.isnan(row[col_idx]):
                valid_values.append(row[col_idx])

        if len(valid_values) < 2:
            continue

        # 平均値と標準偏差を計算
        mean = sum(valid_values) / len(valid_values)
        variance = sum((v - mean) ** 2 for v in valid_values) / (len(valid_values) - 1)
        std_dev = math.sqrt(variance)

        if std_dev == 0:
            continue

        threshold_value = threshold_std * std_dev

        # 異常値検出
        sensor_name = curve_names[col_idx] if col_idx < len(curve_names) else f"col_{col_idx}"

        for row in data_rows:
            if col_idx >= len(row) or math.isnan(row[col_idx]):
                continue

            value = row[col_idx]
            deviation = abs(value - mean)

            if deviation > threshold_value:
                # 深度値の取得
                depth = row[depth_col_idx] if depth_col_idx < len(row) else 0.0

                std_deviations = round(deviation / std_dev, 1)
                anomalies.append({
                    "depth": depth,
                    "sensor": sensor_name,
                    "value": round(value, 1),
                    "threshold": round(mean + threshold_value, 1),
                    "std_deviations": std_deviations,
                })

    return anomalies


@lambda_error_handler
def handler(event, context):
    """エネルギー / 石油・ガス 坑井ログ異常検知 Lambda

    坑井ログファイル（LAS / CSV）を読み込み、センサー読み取り値の
    統計的異常検知を実行する。

    Args:
        event: Map ステートからの入力
            {"Key": "wells/well_A1.las", "Size": 5242880, ...}

    Returns:
        dict: status, file_key, anomalies, total_anomalies, output_key
    """
    file_key = event["Key"]
    file_size = event.get("Size", 0)

    logger.info(
        "Anomaly Detection started: key=%s, size=%d",
        file_key,
        file_size,
    )

    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    output_bucket = os.environ["OUTPUT_BUCKET"]
    threshold_std = float(
        os.environ.get("ANOMALY_THRESHOLD_STD", DEFAULT_ANOMALY_THRESHOLD_STD)
    )

    # ファイル取得
    try:
        response = s3ap.get_object(file_key)
        content = response["Body"].read().decode("utf-8", errors="replace")
    except Exception as e:
        logger.error("Failed to download file %s: %s", file_key, e)
        return {
            "status": "INVALID",
            "file_key": file_key,
            "error": f"Failed to download file: {e}",
            "error_type": "DownloadError",
        }

    # ファイル形式に応じたパース
    file_ext = PurePosixPath(file_key).suffix.lower()

    try:
        if file_ext == ".las":
            curve_names, data_rows = _parse_las_file(content)
        elif file_ext == ".csv":
            curve_names, data_rows = _parse_csv_file(content)
        else:
            return {
                "status": "INVALID",
                "file_key": file_key,
                "error": f"Unsupported file format: {file_ext}",
                "error_type": "UnsupportedFormat",
            }
    except ValueError as e:
        logger.error("Failed to parse file %s: %s", file_key, e)
        return {
            "status": "INVALID",
            "file_key": file_key,
            "error": f"File parse error: {e}",
            "error_type": "ParseError",
        }

    # 異常検知実行
    anomalies = _detect_anomalies(curve_names, data_rows, threshold_std)

    # 日付パーティション付き出力キー生成
    now = datetime.now(timezone.utc)
    file_stem = PurePosixPath(file_key).stem
    output_key = (
        f"anomalies/{now.strftime('%Y/%m/%d')}/{file_stem}.json"
    )

    # 結果を S3 に書き出し
    output_data = {
        "file_key": file_key,
        "file_size": file_size,
        "threshold_std": threshold_std,
        "curve_names": curve_names,
        "total_data_rows": len(data_rows),
        "anomalies": anomalies,
        "total_anomalies": len(anomalies),
        "detected_at": now.isoformat(),
        "execution_id": context.aws_request_id,
    }

    s3_client = boto3.client("s3")
    s3_client.put_object(
        Bucket=output_bucket,
        Key=output_key,
        Body=json.dumps(output_data, default=str, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json; charset=utf-8",
    )

    logger.info(
        "Anomaly Detection completed: key=%s, anomalies=%d, output=%s",
        file_key,
        len(anomalies),
        output_key,
    )

    return {
        "status": "SUCCESS",
        "file_key": file_key,
        "anomalies": anomalies,
        "total_anomalies": len(anomalies),
        "output_key": output_key,
    }
