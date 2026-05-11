"""自動運転 / ADAS 点群 QC Lambda ハンドラ

LiDAR 点群データの品質チェックを実行する。
PCD (Point Cloud Data) ファイルのヘッダーメタデータ（point_count,
coordinate_bounds, point_density）を抽出し、データ整合性
（NaN 座標なし、ヘッダー point_count 一致）を検証する。

PASS/FAIL ステータスと詳細メトリクスを JSON 出力する。

PCD フォーマット:
    # .PCD v0.7
    VERSION 0.7
    FIELDS x y z intensity
    SIZE 4 4 4 4
    TYPE F F F F
    COUNT 1 1 1 1
    WIDTH 1000
    HEIGHT 1
    VIEWPOINT 0 0 0 1 0 0 0
    POINTS 1000
    DATA ascii

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    OUTPUT_DESTINATION: `STANDARD_S3` or `FSXN_S3AP` (デフォルト: `STANDARD_S3`)
    OUTPUT_BUCKET: STANDARD_S3 モードの出力バケット名
    OUTPUT_S3AP_ALIAS: FSXN_S3AP モードの S3AP Alias or ARN
    OUTPUT_S3AP_PREFIX: FSXN_S3AP モードの出力プレフィックス (デフォルト: `ai-outputs/`)
"""

from __future__ import annotations

import logging
import math
import os
from datetime import datetime, timezone
from pathlib import PurePosixPath


from shared.exceptions import lambda_error_handler
from shared.output_writer import OutputWriter
from shared.s3ap_helper import S3ApHelper
from shared.observability import EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)


class PcdParseError(Exception):
    """PCD ファイルパースエラー"""



def parse_pcd_header(data: str | bytes) -> dict:
    """PCD ファイルヘッダーをパースする

    Args:
        data: PCD ファイルの内容（文字列またはバイト列）

    Returns:
        dict: パースされたヘッダー情報
            - version: PCD バージョン
            - fields: フィールド名リスト
            - size: 各フィールドのバイトサイズ
            - type: 各フィールドの型
            - count: 各フィールドのカウント
            - width: ポイント数（幅）
            - height: 高さ（1 = unorganized）
            - viewpoint: ビューポイント
            - points: 宣言されたポイント数
            - data_type: データ形式 (ascii/binary/binary_compressed)
            - header_end_offset: ヘッダー終了位置

    Raises:
        PcdParseError: ヘッダーのパースに失敗した場合
    """
    if isinstance(data, bytes):
        try:
            text = data.decode("utf-8", errors="replace")
        except Exception:
            raise PcdParseError("Failed to decode PCD file as UTF-8")
    else:
        text = data

    header = {
        "version": "",
        "fields": [],
        "size": [],
        "type": [],
        "count": [],
        "width": 0,
        "height": 1,
        "viewpoint": "0 0 0 1 0 0 0",
        "points": 0,
        "data_type": "ascii",
        "header_end_offset": 0,
    }

    lines = text.split("\n")
    header_line_count = 0

    for i, line in enumerate(lines):
        line = line.strip()

        # コメント行をスキップ
        if line.startswith("#"):
            header_line_count += 1
            continue

        # 空行をスキップ
        if not line:
            header_line_count += 1
            continue

        parts = line.split()
        if len(parts) < 2:
            header_line_count += 1
            continue

        keyword = parts[0].upper()

        if keyword == "VERSION":
            header["version"] = parts[1]
        elif keyword == "FIELDS":
            header["fields"] = parts[1:]
        elif keyword == "SIZE":
            try:
                header["size"] = [int(x) for x in parts[1:]]
            except ValueError:
                raise PcdParseError(f"Invalid SIZE values: {line}")
        elif keyword == "TYPE":
            header["type"] = parts[1:]
        elif keyword == "COUNT":
            try:
                header["count"] = [int(x) for x in parts[1:]]
            except ValueError:
                raise PcdParseError(f"Invalid COUNT values: {line}")
        elif keyword == "WIDTH":
            try:
                header["width"] = int(parts[1])
            except ValueError:
                raise PcdParseError(f"Invalid WIDTH value: {line}")
        elif keyword == "HEIGHT":
            try:
                header["height"] = int(parts[1])
            except ValueError:
                raise PcdParseError(f"Invalid HEIGHT value: {line}")
        elif keyword == "VIEWPOINT":
            header["viewpoint"] = " ".join(parts[1:])
        elif keyword == "POINTS":
            try:
                header["points"] = int(parts[1])
            except ValueError:
                raise PcdParseError(f"Invalid POINTS value: {line}")
        elif keyword == "DATA":
            header["data_type"] = parts[1].lower()
            header_line_count += 1
            break

        header_line_count += 1

    # ヘッダー終了位置を計算
    offset = 0
    for j in range(header_line_count):
        if j < len(lines):
            offset += len(lines[j]) + 1  # +1 for newline
    header["header_end_offset"] = offset

    # バリデーション
    if not header["fields"]:
        raise PcdParseError("Missing FIELDS in PCD header")
    if header["points"] <= 0 and header["width"] > 0:
        # POINTS が未指定の場合、WIDTH * HEIGHT から計算
        header["points"] = header["width"] * header["height"]

    return header


def validate_point_cloud(
    header: dict, data_lines: list[str]
) -> dict:
    """点群データの品質検証を実行する

    Args:
        header: パースされた PCD ヘッダー
        data_lines: データ行のリスト

    Returns:
        dict: 検証結果メトリクス
            - point_count: 実際のポイント数
            - coordinate_bounds: 座標範囲
            - point_density: ポイント密度
            - nan_coordinates: NaN 座標の数
            - header_point_count_match: ヘッダーのポイント数と一致するか
            - status: "PASS" or "FAIL"
            - failure_reasons: 失敗理由のリスト
    """
    declared_points = header["points"]
    fields = header["fields"]

    # x, y, z フィールドのインデックスを特定
    field_lower = [f.lower() for f in fields]
    x_idx = field_lower.index("x") if "x" in field_lower else None
    y_idx = field_lower.index("y") if "y" in field_lower else None
    z_idx = field_lower.index("z") if "z" in field_lower else None

    actual_point_count = 0
    nan_count = 0
    x_min = float("inf")
    x_max = float("-inf")
    y_min = float("inf")
    y_max = float("-inf")
    z_min = float("inf")
    z_max = float("-inf")

    for line in data_lines:
        line = line.strip()
        if not line:
            continue

        values = line.split()
        if len(values) < len(fields):
            continue

        actual_point_count += 1

        # 座標値を取得して検証
        try:
            if x_idx is not None:
                x_val = float(values[x_idx])
                if math.isnan(x_val):
                    nan_count += 1
                    continue
                x_min = min(x_min, x_val)
                x_max = max(x_max, x_val)

            if y_idx is not None:
                y_val = float(values[y_idx])
                if math.isnan(y_val):
                    nan_count += 1
                    continue
                y_min = min(y_min, y_val)
                y_max = max(y_max, y_val)

            if z_idx is not None:
                z_val = float(values[z_idx])
                if math.isnan(z_val):
                    nan_count += 1
                    continue
                z_min = min(z_min, z_val)
                z_max = max(z_max, z_val)
        except (ValueError, IndexError):
            # 数値変換失敗は NaN としてカウント
            nan_count += 1
            continue

    # 座標範囲の計算
    coordinate_bounds = {}
    if x_idx is not None and x_min != float("inf"):
        coordinate_bounds["x"] = {"min": x_min, "max": x_max}
    if y_idx is not None and y_min != float("inf"):
        coordinate_bounds["y"] = {"min": y_min, "max": y_max}
    if z_idx is not None and z_min != float("inf"):
        coordinate_bounds["z"] = {"min": z_min, "max": z_max}

    # ポイント密度の計算（ポイント数 / バウンディングボックス体積）
    point_density = 0.0
    if coordinate_bounds and actual_point_count > 0:
        x_range = coordinate_bounds.get("x", {}).get("max", 0) - coordinate_bounds.get("x", {}).get("min", 0)
        y_range = coordinate_bounds.get("y", {}).get("max", 0) - coordinate_bounds.get("y", {}).get("min", 0)
        z_range = coordinate_bounds.get("z", {}).get("max", 0) - coordinate_bounds.get("z", {}).get("min", 0)

        volume = max(x_range, 0.001) * max(y_range, 0.001) * max(z_range, 0.001)
        if volume > 0:
            point_density = actual_point_count / volume

    # ヘッダーポイント数との一致確認
    header_point_count_match = actual_point_count == declared_points

    # PASS/FAIL 判定
    failure_reasons = []
    if not header_point_count_match:
        failure_reasons.append(
            f"Point count mismatch: header={declared_points}, actual={actual_point_count}"
        )
    if nan_count > 0:
        failure_reasons.append(f"NaN coordinates found: {nan_count}")
    if point_density <= 0 and actual_point_count > 0:
        failure_reasons.append("Point density is zero or negative")

    status = "PASS" if not failure_reasons else "FAIL"

    return {
        "point_count": actual_point_count,
        "coordinate_bounds": coordinate_bounds,
        "point_density": round(point_density, 6),
        "nan_coordinates": nan_count,
        "header_point_count_match": header_point_count_match,
        "status": status,
        "failure_reasons": failure_reasons,
    }


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """LiDAR 点群データの品質チェック

    PCD ファイルのヘッダーメタデータを抽出し、データ整合性を検証する。

    Input:
        {"Key": "lidar/scan_001.pcd", "Size": 536870912, ...}

    Output:
        {
            "status": "PASS"|"FAIL",
            "file_key": "...",
            "metrics": {...},
            "output_key": "..."
        }
    """
    file_key = event["Key"]
    file_size = event.get("Size", 0)

    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    output_writer = OutputWriter.from_env()


    logger.info(
        "Point Cloud QC started: file_key=%s, size=%d",
        file_key,
        file_size,
    )

    # ファイル取得
    try:
        response = s3ap.get_object(file_key)
        body = response["Body"]
        file_content = body.read()
        body.close()
    except Exception as e:
        logger.error("Failed to read file %s: %s", file_key, e)
        return {
            "status": "FAIL",
            "file_key": file_key,
            "error": f"Failed to read file: {e}",
            "metrics": {},
        }

    # PCD ヘッダーパース
    try:
        if isinstance(file_content, bytes):
            text_content = file_content.decode("utf-8", errors="replace")
        else:
            text_content = file_content

        header = parse_pcd_header(text_content)
    except PcdParseError as e:
        logger.error("PCD header parse error for %s: %s", file_key, e)
        return {
            "status": "FAIL",
            "file_key": file_key,
            "error": f"PCD header parse error: {e}",
            "metrics": {},
        }

    # データ行を取得（ヘッダー以降）
    lines = text_content.split("\n")
    # DATA 行の次からデータ開始
    data_start = 0
    for i, line in enumerate(lines):
        if line.strip().upper().startswith("DATA"):
            data_start = i + 1
            break

    data_lines = lines[data_start:]

    # 品質検証実行
    metrics = validate_point_cloud(header, data_lines)
    status = metrics.pop("status")
    failure_reasons = metrics.pop("failure_reasons")

    # 出力キー生成
    now = datetime.now(timezone.utc)
    file_stem = PurePosixPath(file_key).stem
    output_key = f"qc/{now.strftime('%Y/%m/%d')}/{file_stem}_qc.json"

    # 結果を出力先（標準 S3 または FSxN S3AP）に書き込み
    result = {
        "status": status,
        "file_key": file_key,
        "metrics": metrics,
        "failure_reasons": failure_reasons if failure_reasons else None,
        "output_key": output_key,
    }

    output_writer.put_json(key=output_key, data=result)

    logger.info(
        "Point Cloud QC completed: file_key=%s, status=%s, points=%d",
        file_key,
        status,
        metrics.get("point_count", 0),
    )


    # EMF メトリクス出力
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="point_cloud_qc")
    metrics.set_dimension("UseCase", os.environ.get("USE_CASE", "autonomous-driving"))
    metrics.put_metric("FilesProcessed", 1.0, "Count")
    metrics.flush()

    return result
