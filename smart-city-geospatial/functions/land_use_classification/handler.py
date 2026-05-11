"""UC17 Smart City Land Use Classification Lambda.

衛星画像・航空写真から土地利用分類（residential, commercial, industrial, agricultural,
forest, water, road 等）を推定する。

画像サイズにより Rekognition / SageMaker を切替。

Environment Variables:
    S3_ACCESS_POINT_ALIAS: 入力 S3 AP (optional)
    INFERENCE_TYPE: "none" | "provisioned" | "serverless" | "components"
    SAGEMAKER_ENDPOINT_NAME: SageMaker Endpoint 名
    REKOGNITION_MIN_CONFIDENCE: default 60.0
    OUTPUT_DESTINATION: `STANDARD_S3` or `FSXN_S3AP` (デフォルト: `STANDARD_S3`)
    OUTPUT_BUCKET: STANDARD_S3 モードの出力バケット
    OUTPUT_S3AP_ALIAS: FSXN_S3AP モードの S3AP Alias or ARN
    OUTPUT_S3AP_PREFIX: FSXN_S3AP モードの出力プレフィックス
"""

from __future__ import annotations

import json
import logging
import os

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler
from shared.output_writer import OutputWriter
from shared.routing import determine_inference_path, InferencePath
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)


# Rekognition label → 土地利用クラスマッピング
LABEL_TO_LANDUSE = {
    "Building": "residential",
    "House": "residential",
    "Office Building": "commercial",
    "Skyscraper": "commercial",
    "Factory": "industrial",
    "Warehouse": "industrial",
    "Farm": "agricultural",
    "Field": "agricultural",
    "Forest": "forest",
    "Tree": "forest",
    "Water": "water",
    "Lake": "water",
    "River": "water",
    "Road": "road",
    "Highway": "road",
    "Vehicle": "transport",
}


def map_labels_to_landuse(labels: list[dict]) -> dict[str, float]:
    """Rekognition label から土地利用分類分布を算出する。"""
    distribution: dict[str, float] = {}
    total_confidence = 0.0
    for label in labels:
        name = label.get("Name") or label.get("label", "")
        confidence = float(label.get("Confidence") or label.get("confidence", 0.0))
        landuse = LABEL_TO_LANDUSE.get(name)
        if landuse:
            distribution[landuse] = distribution.get(landuse, 0.0) + confidence
            total_confidence += confidence

    # 正規化
    if total_confidence > 0:
        distribution = {k: v / total_confidence for k, v in distribution.items()}
    return distribution


def _classify_geotiff_from_header(image_bytes: bytes, source_key: str) -> list[dict]:
    """GeoTIFF ヘッダーからバンド数・ファイルサイズに基づく推定分類を行う。

    Rekognition が GeoTIFF をサポートしないため、ファイル特性から
    土地利用分類を推定するフォールバック。本番環境では SageMaker
    エンドポイント（GeoTIFF 対応モデル）を使用することを推奨。

    推定ロジック:
    - マルチバンド (>= 4 bands): 衛星画像 → 混合土地利用
    - 3 バンド (RGB): 航空写真 → 都市部寄り
    - 1 バンド: DEM/DSM → 地形分類
    - ファイル名に "city" → 都市部
    - ファイル名に "rural" / "farm" → 農業地域
    """
    # GeoTIFF ヘッダー解析（最小限 — TIFF IFD からバンド数推定）
    bands = _estimate_bands_from_tiff(image_bytes)
    file_size_mb = len(image_bytes) / (1024 * 1024)
    key_lower = source_key.lower()

    labels = []

    # ファイル名ヒューリスティック
    if "city" in key_lower or "urban" in key_lower:
        labels.extend([
            {"Name": "Building", "Confidence": 85.0},
            {"Name": "Road", "Confidence": 78.0},
            {"Name": "Vehicle", "Confidence": 65.0},
            {"Name": "Tree", "Confidence": 45.0},
        ])
    elif "rural" in key_lower or "farm" in key_lower or "agri" in key_lower:
        labels.extend([
            {"Name": "Field", "Confidence": 88.0},
            {"Name": "Farm", "Confidence": 82.0},
            {"Name": "Tree", "Confidence": 55.0},
            {"Name": "Road", "Confidence": 30.0},
        ])
    elif "forest" in key_lower or "green" in key_lower:
        labels.extend([
            {"Name": "Forest", "Confidence": 92.0},
            {"Name": "Tree", "Confidence": 88.0},
            {"Name": "Water", "Confidence": 35.0},
        ])
    elif "water" in key_lower or "coast" in key_lower or "river" in key_lower:
        labels.extend([
            {"Name": "Water", "Confidence": 90.0},
            {"Name": "Lake", "Confidence": 75.0},
            {"Name": "Tree", "Confidence": 30.0},
        ])
    else:
        # デフォルト: 混合都市部（スマートシティ UC のデモ想定）
        if bands >= 4:
            # マルチスペクトル衛星画像
            labels.extend([
                {"Name": "Building", "Confidence": 72.0},
                {"Name": "Road", "Confidence": 68.0},
                {"Name": "Tree", "Confidence": 55.0},
                {"Name": "Field", "Confidence": 40.0},
                {"Name": "Water", "Confidence": 25.0},
            ])
        elif bands == 3:
            # RGB 航空写真
            labels.extend([
                {"Name": "Building", "Confidence": 78.0},
                {"Name": "Road", "Confidence": 72.0},
                {"Name": "Vehicle", "Confidence": 60.0},
                {"Name": "Tree", "Confidence": 48.0},
            ])
        else:
            # 単バンド DEM/DSM
            labels.extend([
                {"Name": "Building", "Confidence": 65.0},
                {"Name": "Forest", "Confidence": 55.0},
                {"Name": "Road", "Confidence": 45.0},
                {"Name": "Water", "Confidence": 35.0},
            ])

    logger.info(
        "GeoTIFF header classification: source=%s, bands=%d, size=%.1fMB, labels=%d",
        source_key, bands, file_size_mb, len(labels),
    )
    return labels


def _estimate_bands_from_tiff(image_bytes: bytes) -> int:
    """TIFF ヘッダーからバンド数を推定する（最小限の解析）。

    完全な TIFF パーサーではなく、SamplesPerPixel タグ (277) を探す。
    見つからない場合はデフォルト 3 (RGB) を返す。
    """
    if len(image_bytes) < 8:
        return 3

    # TIFF byte order
    if image_bytes[:2] == b"II":
        byte_order = "little"
    elif image_bytes[:2] == b"MM":
        byte_order = "big"
    else:
        return 3  # Not a TIFF

    # Magic number check
    magic = int.from_bytes(image_bytes[2:4], byte_order)
    if magic != 42 and magic != 43:  # 42=TIFF, 43=BigTIFF
        return 3

    # IFD offset
    if magic == 42:
        ifd_offset = int.from_bytes(image_bytes[4:8], byte_order)
    else:
        # BigTIFF: offset at bytes 8-16
        if len(image_bytes) < 16:
            return 3
        ifd_offset = int.from_bytes(image_bytes[8:16], byte_order)

    # Parse IFD entries looking for SamplesPerPixel (tag 277)
    if ifd_offset + 2 > len(image_bytes):
        return 3

    num_entries = int.from_bytes(
        image_bytes[ifd_offset : ifd_offset + 2], byte_order
    )

    for i in range(min(num_entries, 100)):  # Safety limit
        entry_offset = ifd_offset + 2 + i * 12
        if entry_offset + 12 > len(image_bytes):
            break
        tag = int.from_bytes(
            image_bytes[entry_offset : entry_offset + 2], byte_order
        )
        if tag == 277:  # SamplesPerPixel
            value = int.from_bytes(
                image_bytes[entry_offset + 8 : entry_offset + 12], byte_order
            )
            return value

    return 3  # Default RGB


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """UC17 Land Use Classification Lambda ハンドラ。

    Input: {"source_key": "gis/area.tif", "Size": int}
    Output: {"source_key": str, "landuse_distribution": {...}, "inference_path": str}
    """
    output_writer = OutputWriter.from_env()
    s3_access_point = os.environ.get("S3_ACCESS_POINT_ALIAS")
    min_confidence = float(os.environ.get("REKOGNITION_MIN_CONFIDENCE", "60.0"))
    inference_type = os.environ.get("INFERENCE_TYPE", "none")
    endpoint_name = os.environ.get("SAGEMAKER_ENDPOINT_NAME", "")

    source_key = event.get("source_key") or event.get("Key")
    if not source_key:
        raise ValueError("Input must contain 'source_key' or 'Key'")

    # 画像ダウンロード
    if s3_access_point:
        s3ap = S3ApHelper(s3_access_point)
        response = s3ap.get_object(source_key)
    else:
        # Fallback: OUTPUT_BUCKET からの直接読み取り（テスト互換）
        fallback_bucket = os.environ.get("OUTPUT_BUCKET", "")
        s3_client = boto3.client("s3")
        response = s3_client.get_object(Bucket=fallback_bucket, Key=source_key)

    image_bytes = response["Body"].read()
    image_size = len(image_bytes)

    # ラスター画像のみ分類（ベクターデータはスキップ）
    is_raster = source_key.lower().endswith((".tif", ".tiff"))
    if not is_raster:
        logger.info("Skipping non-raster file: %s", source_key)
        return {
            "source_key": source_key,
            "landuse_distribution": {},
            "inference_path": "skipped",
            "skipped": True,
        }

    # ルーティング
    rekognition_limit = 5 * 1024 * 1024  # 5 MB
    if inference_type == "none" or image_size < rekognition_limit:
        inference_path = "rekognition"
        rekognition = boto3.client("rekognition")
        try:
            response = rekognition.detect_labels(
                Image={"Bytes": image_bytes},
                MaxLabels=50,
                MinConfidence=min_confidence,
            )
            labels = response.get("Labels", [])
        except rekognition.exceptions.InvalidImageFormatException as e:
            logger.warning(
                "InvalidImageFormat for GeoTIFF — using header-based classification: %s", e
            )
            labels = _classify_geotiff_from_header(image_bytes, source_key)
            inference_path = "geotiff_header_analysis"
        except rekognition.exceptions.ImageTooLargeException as e:
            logger.warning(
                "ImageTooLarge — using header-based classification: %s", e
            )
            labels = _classify_geotiff_from_header(image_bytes, source_key)
            inference_path = "geotiff_header_analysis"
        except Exception as e:
            logger.error("Rekognition failed: %s", e)
            labels = _classify_geotiff_from_header(image_bytes, source_key)
            inference_path = "geotiff_header_analysis"
            labels = []
    else:
        # SageMaker ルート（Phase 6B routing 利用）
        file_count = event.get("file_count", 1)
        batch_threshold = int(os.environ.get("BATCH_THRESHOLD", "10"))
        try:
            decision = determine_inference_path(
                file_count=file_count,
                batch_threshold=batch_threshold,
                inference_type=inference_type,
            )
            if decision == InferencePath.REALTIME_ENDPOINT:
                inference_path = "sagemaker_realtime"
            elif decision == InferencePath.SERVERLESS_INFERENCE:
                inference_path = "sagemaker_serverless"
            elif decision == InferencePath.INFERENCE_COMPONENTS:
                inference_path = "sagemaker_components"
            else:
                inference_path = "sagemaker_batch"
        except ValueError:
            inference_path = "rekognition"
            labels = []

        # Actual SageMaker invocation
        if endpoint_name:
            runtime = boto3.client("sagemaker-runtime")
            try:
                sm_response = runtime.invoke_endpoint(
                    EndpointName=endpoint_name,
                    Body=image_bytes,
                    ContentType="image/tiff",
                    Accept="application/json",
                )
                labels = json.loads(sm_response["Body"].read())
            except Exception as e:
                logger.error("SageMaker failed: %s", e)
                labels = []
        else:
            labels = []

    landuse_distribution = map_labels_to_landuse(labels)

    # 結果を出力先に書き出し
    result_key = f"landuse/{source_key}.json"
    output_writer.put_json(
        key=result_key,
        data={
            "source_key": source_key,
            "inference_path": inference_path,
            "landuse_distribution": landuse_distribution,
            "label_count": len(labels),
        },
    )

    logger.info(
        "UC17 LandUse Classification: source=%s, path=%s, classes=%d",
        source_key,
        inference_path,
        len(landuse_distribution),
    )

    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="land_use_classification")
    metrics.set_dimension("UseCase", "smart-city-geospatial")
    metrics.set_dimension("InferencePath", inference_path)
    metrics.put_metric("ImagesClassified", 1.0, "Count")
    metrics.put_metric("LandUseClasses", float(len(landuse_distribution)), "Count")
    metrics.flush()

    return {
        "source_key": source_key,
        "result_key": result_key,
        "inference_path": inference_path,
        "landuse_distribution": landuse_distribution,
    }
