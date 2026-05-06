"""半導体 / EDA メタデータ抽出 Lambda ハンドラ

GDS/OASIS 設計ファイルからヘッダーメタデータを抽出する。
S3 Access Point 経由でファイルの先頭部分を Range リクエストで取得し、
バイナリヘッダーをパースしてメタデータを JSON 形式で S3 に出力する。

GDSII フォーマット:
    - マジックバイト: レコードヘッダー 0x0006 0x0002 (HEADER record)
    - HEADER, BGNLIB, LIBNAME, UNITS レコードを順次パース
    - バージョン 6.0 (600) をサポート

OASIS フォーマット:
    - マジックバイト: "%% SEMI-OASIS\\r\\n"
    - START レコードからバージョンとテーブルオフセットを取得

破損ファイルや非対応バージョンは status: "INVALID" で返却し、
ワークフローを継続する（Step Functions Map ステートの Catch で処理）。

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    OUTPUT_BUCKET: S3 出力バケット名
"""

from __future__ import annotations

import json
import logging
import os
import struct
from datetime import datetime, timezone
from pathlib import PurePosixPath

import boto3

from shared.exceptions import lambda_error_handler
from shared.s3ap_helper import S3ApHelper
from shared.observability import xray_subsegment, EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)

# GDSII レコードタイプ定数
GDSII_HEADER = 0x0002
GDSII_BGNLIB = 0x0102
GDSII_LIBNAME = 0x0206
GDSII_UNITS = 0x0305
GDSII_ENDLIB = 0x0400
GDSII_BGNSTR = 0x0502
GDSII_BOUNDARY = 0x0800
GDSII_SREF = 0x0A00
GDSII_AREF = 0x0B00

# OASIS マジックバイト
OASIS_MAGIC = b"%SEMI-OASIS\r\n"


class GdsiiParseError(Exception):
    """GDSII パースエラー"""
    pass


class OasisParseError(Exception):
    """OASIS パースエラー"""
    pass


def _read_gdsii_record(data: bytes, offset: int) -> tuple[int, int, bytes]:
    """GDSII レコードを1つ読み取る

    GDSII レコード構造:
        - 2 bytes: レコード長（ヘッダー含む）
        - 2 bytes: レコードタイプ (上位バイト) + データタイプ (下位バイト)
        - N bytes: レコードデータ

    Args:
        data: バイナリデータ
        offset: 読み取り開始位置

    Returns:
        tuple: (record_type_with_datatype, next_offset, record_data)

    Raises:
        GdsiiParseError: レコード読み取りに失敗した場合
    """
    if offset + 4 > len(data):
        raise GdsiiParseError(
            f"Insufficient data for record header at offset {offset}"
        )

    record_length = struct.unpack(">H", data[offset:offset + 2])[0]
    record_type = struct.unpack(">H", data[offset + 2:offset + 4])[0]

    if record_length < 4:
        raise GdsiiParseError(
            f"Invalid record length {record_length} at offset {offset}"
        )

    data_start = offset + 4
    data_end = offset + record_length
    if data_end > len(data):
        raise GdsiiParseError(
            f"Record data extends beyond buffer at offset {offset}: "
            f"need {data_end}, have {len(data)}"
        )

    record_data = data[data_start:data_end]
    return record_type, data_end, record_data


def _parse_gdsii_header(data: bytes) -> dict:
    """GDSII バイナリヘッダーからメタデータを抽出する

    HEADER → BGNLIB → LIBNAME → UNITS の順にレコードをパースし、
    ライブラリ名、ユニット情報、作成日時を取得する。
    さらに BGNSTR レコードをカウントしてセル数を推定する。

    Args:
        data: GDSII ファイルの先頭バイナリデータ

    Returns:
        dict: 抽出されたメタデータ

    Raises:
        GdsiiParseError: パースに失敗した場合
    """
    metadata = {
        "file_format": "GDSII",
        "library_name": "",
        "units": {"user_unit": 0.0, "db_unit": 0.0},
        "cell_count": 0,
        "bounding_box": {"min_x": 0, "min_y": 0, "max_x": 0, "max_y": 0},
        "creation_date": None,
        "file_version": "",
    }

    offset = 0

    # HEADER レコード読み取り
    record_type, offset, record_data = _read_gdsii_record(data, offset)
    if record_type != GDSII_HEADER:
        raise GdsiiParseError(
            f"Expected HEADER record (0x0002), got 0x{record_type:04X}"
        )

    if len(record_data) >= 2:
        version = struct.unpack(">H", record_data[:2])[0]
        if version < 0 or version > 700:
            raise GdsiiParseError(f"Unsupported GDS version: {version}")
        # バージョン 600 → "6.0", 700 → "7.0" 等
        metadata["file_version"] = f"{version // 100}.{version % 100}"

    # 残りのレコードをパース
    cell_count = 0
    while offset < len(data):
        try:
            record_type, next_offset, record_data = _read_gdsii_record(
                data, offset
            )
        except GdsiiParseError:
            # データ末尾に到達した場合は終了
            break

        if record_type == GDSII_BGNLIB:
            # BGNLIB: 作成日時（12 個の 2 バイト整数: year, month, day, hour, min, sec × 2）
            if len(record_data) >= 24:
                values = struct.unpack(">12H", record_data[:24])
                year, month, day, hour, minute, second = values[:6]
                # 年が 2 桁の場合は 1900 を加算
                if year < 100:
                    year += 1900
                try:
                    creation_dt = datetime(
                        year, month, day, hour, minute, second,
                        tzinfo=timezone.utc,
                    )
                    metadata["creation_date"] = creation_dt.isoformat()
                except (ValueError, OverflowError):
                    logger.warning(
                        "Invalid BGNLIB date: %d-%d-%d %d:%d:%d",
                        year, month, day, hour, minute, second,
                    )

        elif record_type == GDSII_LIBNAME:
            # LIBNAME: ライブラリ名（ASCII 文字列、NULL パディング）
            metadata["library_name"] = (
                record_data.rstrip(b"\x00").decode("ascii", errors="replace")
            )

        elif record_type == GDSII_UNITS:
            # UNITS: 2 つの 8 バイト浮動小数点数 (user_unit, db_unit)
            if len(record_data) >= 16:
                user_unit = _gdsii_real8_to_float(record_data[:8])
                db_unit = _gdsii_real8_to_float(record_data[8:16])
                metadata["units"] = {
                    "user_unit": user_unit,
                    "db_unit": db_unit,
                }

        elif record_type == GDSII_BGNSTR:
            # BGNSTR: セル（構造体）の開始
            cell_count += 1

        elif record_type == GDSII_ENDLIB:
            break

        offset = next_offset

    metadata["cell_count"] = cell_count
    return metadata


def _gdsii_real8_to_float(data: bytes) -> float:
    """GDSII 8 バイト実数を IEEE 754 浮動小数点数に変換する

    GDSII は IBM 形式の浮動小数点数を使用する:
        - ビット 0: 符号 (0=正, 1=負)
        - ビット 1-7: 指数 (excess-64, 基数 16)
        - ビット 8-63: 仮数部 (56 ビット)

    Args:
        data: 8 バイトのバイナリデータ

    Returns:
        float: 変換された浮動小数点数
    """
    if len(data) != 8:
        return 0.0

    byte0 = data[0]
    sign = -1.0 if (byte0 & 0x80) else 1.0
    exponent = (byte0 & 0x7F) - 64

    # 仮数部を 56 ビット整数として読み取り
    mantissa = 0
    for i in range(1, 8):
        mantissa = (mantissa << 8) | data[i]

    if mantissa == 0:
        return 0.0

    # 仮数部を [0, 1) の範囲に正規化
    mantissa_float = mantissa / (2.0 ** 56)

    return sign * mantissa_float * (16.0 ** exponent)


def _parse_oasis_header(data: bytes) -> dict:
    """OASIS ファイルヘッダーからメタデータを抽出する

    OASIS フォーマット:
        - マジックバイト: "%SEMI-OASIS\\r\\n"
        - START レコード: バージョン文字列とテーブルオフセット

    Args:
        data: OASIS ファイルの先頭バイナリデータ

    Returns:
        dict: 抽出されたメタデータ

    Raises:
        OasisParseError: パースに失敗した場合
    """
    # マジックバイト検証
    if not data.startswith(OASIS_MAGIC):
        raise OasisParseError(
            "Invalid OASIS magic bytes: expected '%SEMI-OASIS\\r\\n'"
        )

    metadata = {
        "file_format": "OASIS",
        "library_name": "",
        "units": {"user_unit": 0.001, "db_unit": 1e-09},
        "cell_count": 0,
        "bounding_box": {"min_x": 0, "min_y": 0, "max_x": 0, "max_y": 0},
        "creation_date": None,
        "file_version": "1.0",
    }

    offset = len(OASIS_MAGIC)

    # START レコード: レコードID (1 byte) = 1
    if offset < len(data):
        record_id = data[offset]
        if record_id == 1:  # START record
            offset += 1
            # バージョン文字列の読み取り（長さプレフィックス付き）
            if offset < len(data):
                version_len = data[offset]
                offset += 1
                if offset + version_len <= len(data):
                    version_str = data[offset:offset + version_len].decode(
                        "ascii", errors="replace"
                    )
                    metadata["file_version"] = version_str
                    offset += version_len

    # OASIS ではヘッダーだけからセル数を正確に取得するのは困難
    # ファイル全体をパースせずにヘッダー情報のみ返す
    return metadata


def _detect_file_format(key: str) -> str:
    """ファイル拡張子からフォーマットを判定する

    Args:
        key: オブジェクトキー

    Returns:
        str: "GDSII" or "OASIS"
    """
    lower_key = key.lower()
    if lower_key.endswith((".gds", ".gds2")):
        return "GDSII"
    elif lower_key.endswith((".oas", ".oasis")):
        return "OASIS"
    return "UNKNOWN"


def _extract_metadata(data: bytes, file_key: str) -> dict:
    """ファイルフォーマットに応じてメタデータを抽出する

    Args:
        data: ファイルの先頭バイナリデータ
        file_key: オブジェクトキー

    Returns:
        dict: 抽出されたメタデータ

    Raises:
        GdsiiParseError: GDSII パースに失敗した場合
        OasisParseError: OASIS パースに失敗した場合
        ValueError: 不明なファイルフォーマットの場合
    """
    file_format = _detect_file_format(file_key)

    if file_format == "GDSII":
        return _parse_gdsii_header(data)
    elif file_format == "OASIS":
        return _parse_oasis_header(data)
    else:
        raise ValueError(f"Unknown file format for key: {file_key}")


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """半導体 / EDA メタデータ抽出 Lambda

    GDS/OASIS ファイルからヘッダーメタデータを抽出し、
    日付パーティション付き JSON で S3 に出力する。

    破損ファイルや非対応バージョンは status: "INVALID" で返却し、
    ワークフローを継続する。

    Args:
        event: Map ステートからの入力
            {"Key": "designs/chip_v2.gds", "Size": 1073741824, ...}

    Returns:
        dict: status, file_key, metadata, output_key
              または status: "INVALID", file_key, error, error_type
    """
    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    output_bucket = os.environ["OUTPUT_BUCKET"]
    file_key = event["Key"]

    logger.info("Metadata extraction started: file_key=%s", file_key)

    try:
        # ヘッダーパースには先頭数 KB で十分
        # GDSII: HEADER + BGNLIB + LIBNAME + UNITS + 複数 BGNSTR で ~64KB
        # OASIS: マジック + START で ~1KB
        # 大規模ファイルでもヘッダーのみ取得するため Range リクエストを使用
        header_size = 64 * 1024  # 64 KB
        header_data = s3ap.streaming_download_range(
            key=file_key,
            start=0,
            end=header_size - 1,
        )

        metadata = _extract_metadata(header_data, file_key)

    except (GdsiiParseError, OasisParseError, ValueError) as e:
        logger.warning(
            "Failed to parse file %s: %s", file_key, str(e)
        )
        return {
            "status": "INVALID",
            "file_key": file_key,
            "error": str(e),
            "error_type": type(e).__name__,
        }
    except Exception as e:
        logger.error(
            "Unexpected error processing file %s: %s", file_key, str(e)
        )
        return {
            "status": "INVALID",
            "file_key": file_key,
            "error": str(e),
            "error_type": type(e).__name__,
        }

    # 日付パーティション付き出力キー生成
    now = datetime.now(timezone.utc)
    file_stem = PurePosixPath(file_key).stem
    output_key = (
        f"metadata/{now.strftime('%Y/%m/%d')}/{file_stem}.json"
    )

    # メタデータ JSON を S3 出力バケットに書き込み
    output_data = {
        "file_key": file_key,
        **metadata,
        "extracted_at": now.isoformat(),
    }

    s3_client = boto3.client("s3")
    s3_client.put_object(
        Bucket=output_bucket,
        Key=output_key,
        Body=json.dumps(output_data, default=str).encode("utf-8"),
        ContentType="application/json",
    )

    logger.info(
        "Metadata extraction completed: file_key=%s, output_key=%s, "
        "cell_count=%d, format=%s",
        file_key,
        output_key,
        metadata.get("cell_count", 0),
        metadata.get("file_format", "UNKNOWN"),
    )


    # EMF メトリクス出力
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="metadata_extraction")
    metrics.set_dimension("UseCase", os.environ.get("USE_CASE", "semiconductor-eda"))
    metrics.put_metric("FilesProcessed", 1.0, "Count")
    metrics.flush()

    return {
        "status": "SUCCESS",
        "file_key": file_key,
        "metadata": metadata,
        "output_key": output_key,
    }
