"""エネルギー / 石油・ガス SEG-Y メタデータ抽出 Lambda ハンドラ

S3ApHelper の streaming_download_range で SEG-Y ファイルヘッダー（先頭 3600 バイト）を
取得し、テキストヘッダーおよびバイナリヘッダーからメタデータを抽出する。

SEG-Y ファイル構造:
    - Bytes 0-3199: Textual File Header (3200 bytes, EBCDIC or ASCII)
    - Bytes 3200-3599: Binary File Header (400 bytes)

バイナリヘッダーの主要フィールド（ビッグエンディアン）:
    - Offset 12-13: データトレース数/アンサンブル (int16)
    - Offset 16-17: サンプル間隔（マイクロ秒） (int16)
    - Offset 20-21: データトレースあたりのサンプル数 (int16)
    - Offset 24-25: データサンプルフォーマットコード (int16)
    - Offset 54-55: 測定系 (int16): 1=meters, 2=feet

パース失敗時は status: "INVALID" で返却する。

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    OUTPUT_DESTINATION: 出力先タイプ (STANDARD_S3 / FSXN_S3AP)
    OUTPUT_BUCKET: STANDARD_S3 モード時の出力バケット名
    OUTPUT_S3AP_ALIAS: FSXN_S3AP モード時の S3AP Alias or ARN
    OUTPUT_S3AP_PREFIX: FSXN_S3AP モード時のプレフィックス
"""

from __future__ import annotations

import logging
import os
import struct
from datetime import datetime, timezone
from pathlib import PurePosixPath

from shared.exceptions import lambda_error_handler
from shared.output_writer import OutputWriter
from shared.s3ap_helper import S3ApHelper
from shared.observability import EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)

# SEG-Y ヘッダーサイズ
TEXTUAL_HEADER_SIZE = 3200
BINARY_HEADER_SIZE = 400
TOTAL_HEADER_SIZE = TEXTUAL_HEADER_SIZE + BINARY_HEADER_SIZE  # 3600 bytes

# データサンプルフォーマットコードのマッピング
DATA_FORMAT_CODES = {
    1: "IBM floating-point (4 bytes)",
    2: "Two's complement integer (4 bytes)",
    3: "Two's complement integer (2 bytes)",
    4: "Fixed-point with gain (4 bytes)",
    5: "IEEE floating-point (4 bytes)",
}

# 測定系のマッピング
MEASUREMENT_SYSTEMS = {
    1: "meters",
    2: "feet",
}

# EBCDIC → ASCII 変換テーブル
EBCDIC_TO_ASCII = bytes(range(256))
try:
    import codecs
    _ebcdic_codec = codecs.lookup("cp500")
except LookupError:
    _ebcdic_codec = None


def _decode_textual_header(raw_bytes: bytes) -> str:
    """テキストヘッダーをデコードする（EBCDIC または ASCII）

    Args:
        raw_bytes: テキストヘッダーの生バイト列 (3200 bytes)

    Returns:
        str: デコードされたテキストヘッダー
    """
    # EBCDIC 判定: 先頭バイトが 0xC3 ('C' in EBCDIC) の場合は EBCDIC
    if raw_bytes and raw_bytes[0] == 0xC3:
        try:
            return raw_bytes.decode("cp500")
        except (UnicodeDecodeError, LookupError):
            pass

    # ASCII としてデコード
    try:
        return raw_bytes.decode("ascii", errors="replace")
    except Exception:
        return raw_bytes.decode("latin-1", errors="replace")


def _extract_survey_name(textual_header: str) -> str:
    """テキストヘッダーから調査名を抽出する

    CLIENT または SURVEY キーワードを含む行から調査名を取得する。
    見つからない場合は空文字列を返す。

    Args:
        textual_header: デコード済みテキストヘッダー

    Returns:
        str: 調査名
    """
    lines = textual_header.split("\n")
    if len(lines) <= 1:
        # 改行がない場合は 80 文字ごとに分割（SEG-Y 標準: 40 行 × 80 文字）
        lines = [textual_header[i:i + 80] for i in range(0, len(textual_header), 80)]

    for line in lines:
        line_upper = line.upper()
        for keyword in ("CLIENT", "SURVEY", "SURVEY NAME", "PROJECT"):
            if keyword in line_upper:
                # キーワードの後の値を抽出
                idx = line_upper.find(keyword)
                remainder = line[idx + len(keyword):].strip()
                # コロンや等号の後の値を取得
                for sep in (":", "=", " "):
                    if sep in remainder:
                        value = remainder.split(sep, 1)[1].strip()
                        # 末尾の空白やパディングを除去
                        value = value.rstrip()
                        if value:
                            return value
                # セパレータがない場合は残り全体を返す
                if remainder:
                    return remainder.rstrip()

    return ""


def _extract_coordinate_system(textual_header: str) -> str:
    """テキストヘッダーから座標系を抽出する

    COORDINATE, DATUM, CRS キーワードを含む行から座標系を取得する。
    見つからない場合は "unknown" を返す。

    Args:
        textual_header: デコード済みテキストヘッダー

    Returns:
        str: 座標系名
    """
    lines = textual_header.split("\n")
    if len(lines) <= 1:
        lines = [textual_header[i:i + 80] for i in range(0, len(textual_header), 80)]

    for line in lines:
        line_upper = line.upper()
        for keyword in ("COORDINATE", "DATUM", "CRS", "PROJECTION"):
            if keyword in line_upper:
                idx = line_upper.find(keyword)
                remainder = line[idx + len(keyword):].strip()
                for sep in (":", "=", " "):
                    if sep in remainder:
                        value = remainder.split(sep, 1)[1].strip().rstrip()
                        if value:
                            return value
                if remainder:
                    return remainder.rstrip()

    return "unknown"


def _parse_binary_header(binary_header: bytes) -> dict:
    """バイナリヘッダーからメタデータフィールドを抽出する

    Args:
        binary_header: バイナリヘッダーの生バイト列 (400 bytes)

    Returns:
        dict: 抽出されたメタデータフィールド

    Raises:
        ValueError: バイナリヘッダーのサイズが不正な場合
    """
    if len(binary_header) < BINARY_HEADER_SIZE:
        raise ValueError(
            f"Binary header too short: {len(binary_header)} bytes "
            f"(expected {BINARY_HEADER_SIZE})"
        )

    # ビッグエンディアンで各フィールドを抽出
    # Offset 12-13: Number of data traces per ensemble (int16)
    traces_per_ensemble = struct.unpack(">h", binary_header[12:14])[0]

    # Offset 16-17: Sample interval in microseconds (int16)
    sample_interval = struct.unpack(">h", binary_header[16:18])[0]

    # Offset 20-21: Number of samples per data trace (int16)
    samples_per_trace = struct.unpack(">h", binary_header[20:22])[0]

    # Offset 24-25: Data sample format code (int16)
    data_format_code = struct.unpack(">h", binary_header[24:26])[0]

    # Offset 54-55: Measurement system (int16): 1=meters, 2=feet
    measurement_system_code = struct.unpack(">h", binary_header[54:56])[0]

    # トレース数の推定（traces_per_ensemble が 0 の場合はファイルサイズから推定不可）
    trace_count = traces_per_ensemble if traces_per_ensemble > 0 else 0

    measurement_system = MEASUREMENT_SYSTEMS.get(
        measurement_system_code, "unknown"
    )

    return {
        "sample_interval": sample_interval,
        "samples_per_trace": samples_per_trace,
        "trace_count": trace_count,
        "data_format_code": data_format_code,
        "measurement_system": measurement_system,
    }


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """エネルギー / 石油・ガス SEG-Y メタデータ抽出 Lambda

    S3ApHelper streaming_download_range で SEG-Y ヘッダー（先頭 3600 バイト）を
    取得し、テキストヘッダーおよびバイナリヘッダーからメタデータを抽出する。
    パース失敗時は status: "INVALID" で返却する。

    Args:
        event: Map ステートからの入力
            {"Key": "surveys/north_sea_2026.segy", "Size": 10737418240, ...}

    Returns:
        dict: status, file_key, metadata, output_key
    """
    file_key = event["Key"]
    file_size = event.get("Size", 0)

    logger.info(
        "Seismic Metadata extraction started: key=%s, size=%d",
        file_key,
        file_size,
    )

    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    output_writer = OutputWriter.from_env()

    # ファイルサイズがヘッダーサイズ未満の場合は INVALID
    if file_size < TOTAL_HEADER_SIZE:
        logger.warning(
            "File too small for SEG-Y header: key=%s, size=%d", file_key, file_size
        )
        return {
            "status": "INVALID",
            "file_key": file_key,
            "error": f"File size ({file_size} bytes) is smaller than "
                     f"minimum SEG-Y header size ({TOTAL_HEADER_SIZE} bytes)",
            "error_type": "FileTooSmall",
        }

    try:
        # 先頭 3600 バイトを Range リクエストで取得
        header_data = s3ap.streaming_download_range(
            key=file_key, start=0, end=TOTAL_HEADER_SIZE - 1
        )
    except Exception as e:
        logger.error("Failed to download header for %s: %s", file_key, e)
        return {
            "status": "INVALID",
            "file_key": file_key,
            "error": f"Failed to download file header: {e}",
            "error_type": "DownloadError",
        }

    try:
        # テキストヘッダー（先頭 3200 バイト）のデコード
        textual_raw = header_data[:TEXTUAL_HEADER_SIZE]
        textual_header = _decode_textual_header(textual_raw)

        # バイナリヘッダー（3200-3599 バイト）のパース
        binary_raw = header_data[TEXTUAL_HEADER_SIZE:TOTAL_HEADER_SIZE]
        binary_fields = _parse_binary_header(binary_raw)

        # テキストヘッダーから調査名・座標系を抽出
        survey_name = _extract_survey_name(textual_header)
        if not survey_name:
            # ファイル名から調査名を推定
            stem = PurePosixPath(file_key).stem
            survey_name = stem.replace("_", " ").title()

        coordinate_system = _extract_coordinate_system(textual_header)

    except Exception as e:
        logger.error("Failed to parse SEG-Y header for %s: %s", file_key, e)
        return {
            "status": "INVALID",
            "file_key": file_key,
            "error": f"SEG-Y header parse error: {e}",
            "error_type": "ParseError",
        }

    # メタデータ構築
    metadata = {
        "survey_name": survey_name,
        "coordinate_system": coordinate_system,
        "sample_interval": binary_fields["sample_interval"],
        "trace_count": binary_fields["trace_count"],
        "data_format_code": binary_fields["data_format_code"],
        "measurement_system": binary_fields["measurement_system"],
    }

    # 日付パーティション付き出力キー生成
    now = datetime.now(timezone.utc)
    file_stem = PurePosixPath(file_key).stem
    output_key = (
        f"metadata/{now.strftime('%Y/%m/%d')}/{file_stem}.json"
    )

    # メタデータを S3 に書き出し
    output_data = {
        "file_key": file_key,
        "file_size": file_size,
        "metadata": metadata,
        "extracted_at": now.isoformat(),
        "execution_id": context.aws_request_id,
    }

    output_writer.put_json(key=output_key, data=output_data)

    logger.info(
        "Seismic Metadata extraction completed: key=%s, survey=%s, output=%s",
        file_key,
        survey_name,
        output_key,
    )


    # EMF メトリクス出力
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="seismic_metadata")
    metrics.set_dimension("UseCase", os.environ.get("USE_CASE", "energy-seismic"))
    metrics.put_metric("FilesProcessed", 1.0, "Count")
    metrics.flush()

    return {
        "status": "SUCCESS",
        "file_key": file_key,
        "metadata": metadata,
        "output_key": output_key,
    }
