"""小売 / EC 画像品質チェック Lambda ハンドラ

画像品質メトリクス（最小解像度、ファイルサイズ範囲、アスペクト比）を検証し、
閾値未満の画像をフラグする。

品質基準:
- 最小解像度: 800x800 ピクセル
- ファイルサイズ: 100KB ～ 50MB
- アスペクト比: 0.5 ～ 2.0

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    OUTPUT_DESTINATION: `STANDARD_S3` or `FSXN_S3AP` (デフォルト: `STANDARD_S3`)
    OUTPUT_BUCKET: STANDARD_S3 モードの出力バケット名
    OUTPUT_S3AP_ALIAS: FSXN_S3AP モードの S3AP Alias or ARN
    OUTPUT_S3AP_PREFIX: FSXN_S3AP モードの出力プレフィックス (デフォルト: `ai-outputs/`)
    MIN_RESOLUTION: 最小解像度 (デフォルト: 800)
    MIN_FILE_SIZE: 最小ファイルサイズ bytes (デフォルト: 102400 = 100KB)
    MAX_FILE_SIZE: 最大ファイルサイズ bytes (デフォルト: 52428800 = 50MB)
    MIN_ASPECT_RATIO: 最小アスペクト比 (デフォルト: 0.5)
    MAX_ASPECT_RATIO: 最大アスペクト比 (デフォルト: 2.0)
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


def get_image_dimensions(image_bytes: bytes, file_key: str) -> tuple[int, int] | None:
    """画像のヘッダーから解像度（幅、高さ）を取得する

    JPEG, PNG, WebP のヘッダーをパースして画像サイズを取得する。
    パース失敗時は None を返す。

    Args:
        image_bytes: 画像バイナリデータ（先頭部分で十分）
        file_key: ファイルキー（拡張子判定用）

    Returns:
        tuple[int, int] | None: (width, height) or None
    """
    lower_key = file_key.lower()

    try:
        if lower_key.endswith((".jpg", ".jpeg")):
            return _get_jpeg_dimensions(image_bytes)
        elif lower_key.endswith(".png"):
            return _get_png_dimensions(image_bytes)
        elif lower_key.endswith(".webp"):
            return _get_webp_dimensions(image_bytes)
    except (struct.error, IndexError, ValueError):
        pass

    return None


def _get_jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    """JPEG ヘッダーから画像サイズを取得する"""
    if len(data) < 2 or data[0:2] != b"\xff\xd8":
        return None

    offset = 2
    while offset < len(data) - 1:
        if data[offset] != 0xFF:
            offset += 1
            continue

        marker = data[offset + 1]
        offset += 2

        # SOF markers (Start of Frame)
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                      0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            if offset + 7 <= len(data):
                height = struct.unpack(">H", data[offset + 3:offset + 5])[0]
                width = struct.unpack(">H", data[offset + 5:offset + 7])[0]
                return (width, height)
            return None

        # Skip non-SOF markers
        if marker == 0xD9:  # EOI
            return None
        if marker in (0xD0, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0x01):
            continue

        if offset + 2 <= len(data):
            segment_length = struct.unpack(">H", data[offset:offset + 2])[0]
            offset += segment_length
        else:
            return None

    return None


def _get_png_dimensions(data: bytes) -> tuple[int, int] | None:
    """PNG ヘッダーから画像サイズを取得する"""
    # PNG signature: 8 bytes, then IHDR chunk
    if len(data) < 24 or data[0:8] != b"\x89PNG\r\n\x1a\n":
        return None

    # IHDR chunk starts at offset 8 (4 bytes length + 4 bytes type + data)
    # Width at offset 16, Height at offset 20
    width = struct.unpack(">I", data[16:20])[0]
    height = struct.unpack(">I", data[20:24])[0]
    return (width, height)


def _get_webp_dimensions(data: bytes) -> tuple[int, int] | None:
    """WebP ヘッダーから画像サイズを取得する"""
    if len(data) < 30 or data[0:4] != b"RIFF" or data[8:12] != b"WEBP":
        return None

    # VP8 format
    if data[12:16] == b"VP8 ":
        if len(data) >= 30:
            # VP8 bitstream header at offset 26
            width = struct.unpack("<H", data[26:28])[0] & 0x3FFF
            height = struct.unpack("<H", data[28:30])[0] & 0x3FFF
            return (width, height)

    # VP8L format (lossless)
    elif data[12:16] == b"VP8L":
        if len(data) >= 25:
            # Signature byte at offset 21, then 4 bytes of width/height
            bits = struct.unpack("<I", data[21:25])[0]
            width = (bits & 0x3FFF) + 1
            height = ((bits >> 14) & 0x3FFF) + 1
            return (width, height)

    # VP8X format (extended)
    elif data[12:16] == b"VP8X":
        if len(data) >= 30:
            # Canvas width at offset 24 (3 bytes LE + 1)
            width = (data[24] | (data[25] << 8) | (data[26] << 16)) + 1
            height = (data[27] | (data[28] << 8) | (data[29] << 16)) + 1
            return (width, height)

    return None


def validate_quality(
    width: int | None,
    height: int | None,
    file_size: int,
    min_resolution: int = 800,
    min_file_size: int = 102400,
    max_file_size: int = 52428800,
    min_aspect_ratio: float = 0.5,
    max_aspect_ratio: float = 2.0,
) -> tuple[str, dict, list[str]]:
    """画像品質メトリクスを検証する

    Args:
        width: 画像幅 (ピクセル)
        height: 画像高さ (ピクセル)
        file_size: ファイルサイズ (バイト)
        min_resolution: 最小解像度 (幅・高さ両方)
        min_file_size: 最小ファイルサイズ (バイト)
        max_file_size: 最大ファイルサイズ (バイト)
        min_aspect_ratio: 最小アスペクト比 (width/height)
        max_aspect_ratio: 最大アスペクト比 (width/height)

    Returns:
        tuple: (status, quality_metrics, issues)
    """
    issues: list[str] = []
    quality_metrics: dict = {
        "width": width,
        "height": height,
        "file_size": file_size,
        "aspect_ratio": None,
    }

    # ファイルサイズチェック
    if file_size < min_file_size:
        issues.append(
            f"File size {file_size} bytes is below minimum {min_file_size} bytes"
        )
    if file_size > max_file_size:
        issues.append(
            f"File size {file_size} bytes exceeds maximum {max_file_size} bytes"
        )

    # 解像度チェック
    if width is not None and height is not None:
        if width < min_resolution:
            issues.append(
                f"Width {width}px is below minimum {min_resolution}px"
            )
        if height < min_resolution:
            issues.append(
                f"Height {height}px is below minimum {min_resolution}px"
            )

        # アスペクト比チェック
        if height > 0:
            aspect_ratio = round(width / height, 4)
            quality_metrics["aspect_ratio"] = aspect_ratio

            if aspect_ratio < min_aspect_ratio:
                issues.append(
                    f"Aspect ratio {aspect_ratio} is below minimum {min_aspect_ratio}"
                )
            if aspect_ratio > max_aspect_ratio:
                issues.append(
                    f"Aspect ratio {aspect_ratio} exceeds maximum {max_aspect_ratio}"
                )
    else:
        issues.append("Unable to determine image dimensions")

    status = "PASS" if not issues else "FAIL"
    return status, quality_metrics, issues


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """小売 / EC 画像品質チェック Lambda

    画像品質メトリクス（解像度、ファイルサイズ、アスペクト比）を検証し、
    閾値未満の画像をフラグする。

    Args:
        event: Map ステートからの入力
            {"Key": "products/SKU12345_front.jpg", "Size": 2097152, ...}

    Returns:
        dict: status, file_key, quality_metrics, issues
    """
    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    output_writer = OutputWriter.from_env()
    file_key = event["Key"]
    file_size = event.get("Size", 0)

    # 品質パラメータ
    min_resolution = int(os.environ.get("MIN_RESOLUTION", "800"))
    min_file_size = int(os.environ.get("MIN_FILE_SIZE", "102400"))
    max_file_size = int(os.environ.get("MAX_FILE_SIZE", "52428800"))
    min_aspect_ratio = float(os.environ.get("MIN_ASPECT_RATIO", "0.5"))
    max_aspect_ratio = float(os.environ.get("MAX_ASPECT_RATIO", "2.0"))

    logger.info(
        "Quality check started: file_key=%s, file_size=%d, output=%s",
        file_key,
        file_size,
        output_writer.target_description,
    )

    # 画像ヘッダーを取得して解像度を判定
    # ヘッダーパースには先頭数 KB で十分
    try:
        response = s3ap.get_object(file_key)
        # 先頭 64KB を読み取り（ヘッダー解析に十分）
        header_bytes = response["Body"].read(65536)
        dimensions = get_image_dimensions(header_bytes, file_key)
    except Exception as e:
        logger.warning("Failed to read image header for %s: %s", file_key, e)
        dimensions = None

    width = dimensions[0] if dimensions else None
    height = dimensions[1] if dimensions else None

    # 品質検証
    status, quality_metrics, issues = validate_quality(
        width=width,
        height=height,
        file_size=file_size,
        min_resolution=min_resolution,
        min_file_size=min_file_size,
        max_file_size=max_file_size,
        min_aspect_ratio=min_aspect_ratio,
        max_aspect_ratio=max_aspect_ratio,
    )

    # 出力キー生成（日付パーティション付き）
    now = datetime.now(timezone.utc)
    file_stem = PurePosixPath(file_key).stem
    output_key = f"quality/{now.strftime('%Y/%m/%d')}/{file_stem}_qc.json"

    # 品質チェック結果を出力先（標準 S3 または FSxN S3AP）に書き込み
    output_data = {
        "file_key": file_key,
        "status": status,
        "quality_metrics": quality_metrics,
        "issues": issues,
        "thresholds": {
            "min_resolution": min_resolution,
            "min_file_size": min_file_size,
            "max_file_size": max_file_size,
            "min_aspect_ratio": min_aspect_ratio,
            "max_aspect_ratio": max_aspect_ratio,
        },
        "checked_at": now.isoformat(),
    }

    output_writer.put_json(key=output_key, data=output_data)

    logger.info(
        "Quality check completed: file_key=%s, status=%s, issues=%d, output_uri=%s",
        file_key,
        status,
        len(issues),
        output_writer.build_s3_uri(output_key),
    )


    # EMF メトリクス出力
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="quality_check")
    metrics.set_dimension("UseCase", os.environ.get("USE_CASE", "retail-catalog"))
    metrics.put_metric("FilesProcessed", 1.0, "Count")
    metrics.flush()

    return {
        "status": status,
        "file_key": file_key,
        "quality_metrics": quality_metrics,
        "issues": issues,
    }
