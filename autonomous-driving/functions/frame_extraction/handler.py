"""自動運転 / ADAS フレーム抽出 + Rekognition 物体検出 Lambda ハンドラ

ダッシュカム映像からキーフレームを設定可能な間隔で抽出し、
Amazon Rekognition DetectLabels で物体検出（車両、歩行者、交通標識、車線マーキング）
を実行する。

Lambda では実際の動画デコードが困難なため、ファイルメタデータベースのアプローチで
フレーム抽出をシミュレートし、先頭バイトを Rekognition に送信する。
本番環境では MediaConvert またはコンテナベースの処理を使用する。

非対応コーデック/破損時はエラーログ出力しワークフロー継続する。

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    OUTPUT_DESTINATION: `STANDARD_S3` or `FSXN_S3AP` (デフォルト: `STANDARD_S3`)
    OUTPUT_BUCKET: STANDARD_S3 モードの出力バケット名
    OUTPUT_S3AP_ALIAS: FSXN_S3AP モードの S3AP Alias or ARN
    OUTPUT_S3AP_PREFIX: FSXN_S3AP モードの出力プレフィックス (デフォルト: `ai-outputs/`)
    FRAME_INTERVAL: フレーム抽出間隔 (ミリ秒, デフォルト: 1000)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import PurePosixPath

import boto3

from shared.exceptions import lambda_error_handler
from shared.output_writer import OutputWriter
from shared.s3ap_helper import S3ApHelper
from shared.observability import xray_subsegment, EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)

# Rekognition で検出する自動運転関連ラベル
DRIVING_LABELS = {
    "Car", "Vehicle", "Automobile", "Truck", "Bus", "Motorcycle",
    "Pedestrian", "Person", "Human",
    "Traffic Sign", "Traffic Light", "Stop Sign",
    "Lane", "Road", "Highway",
}

# 動画ファイルのマジックバイト（ファイルタイプ検証用）
VIDEO_SIGNATURES = {
    b"\x00\x00\x00": "mp4/mov",  # ftyp box (offset 4)
    b"\x1a\x45\xdf\xa3": "mkv/webm",  # EBML header
    b"RIFF": "avi",  # AVI container
}


def _detect_video_format(header_bytes: bytes) -> str | None:
    """動画ファイルのフォーマットをマジックバイトから検出する

    Args:
        header_bytes: ファイル先頭バイト列

    Returns:
        str | None: 検出されたフォーマット名、または None（不明な場合）
    """
    if len(header_bytes) < 8:
        return None

    # MP4/MOV: offset 4 に 'ftyp' がある
    if header_bytes[4:8] == b"ftyp":
        return "mp4"

    # MKV/WebM: EBML header
    if header_bytes[:4] == b"\x1a\x45\xdf\xa3":
        return "mkv"

    # AVI: RIFF header
    if header_bytes[:4] == b"RIFF" and header_bytes[8:12] == b"AVI ":
        return "avi"

    return None


def _estimate_frame_count(file_size: int, frame_interval_ms: int) -> int:
    """ファイルサイズとフレーム間隔から推定フレーム数を計算する

    Lambda 環境では実際の動画デコードが困難なため、
    ファイルサイズベースの推定を行う。

    推定ロジック:
    - 平均ビットレート: 10 Mbps (1.25 MB/s)
    - 推定動画長 = file_size / bitrate
    - フレーム数 = 動画長 / フレーム間隔

    Args:
        file_size: ファイルサイズ (bytes)
        frame_interval_ms: フレーム抽出間隔 (ミリ秒)

    Returns:
        int: 推定フレーム数（最低 1）
    """
    avg_bitrate_bytes_per_sec = 1_250_000  # 10 Mbps
    estimated_duration_sec = file_size / avg_bitrate_bytes_per_sec
    estimated_duration_ms = estimated_duration_sec * 1000
    frame_count = int(estimated_duration_ms / frame_interval_ms)
    return max(1, frame_count)


def _run_rekognition_detection(
    rekognition_client, image_bytes: bytes
) -> list[dict]:
    """Rekognition DetectLabels を実行し、自動運転関連ラベルを抽出する

    Args:
        rekognition_client: boto3 Rekognition クライアント
        image_bytes: 画像バイト列

    Returns:
        list[dict]: 検出されたオブジェクトのリスト
    """
    try:
        with xray_subsegment(

            name="rekognition_detectlabels",

            annotations={"service_name": "rekognition", "operation": "DetectLabels", "use_case": "autonomous-driving"},

        ):

            response = rekognition_client.detect_labels(
            Image={"Bytes": image_bytes},
            MaxLabels=20,
            MinConfidence=50.0,
        )
    except Exception as e:
        logger.warning("Rekognition DetectLabels failed: %s", e)
        return []

    detections = []
    for label in response.get("Labels", []):
        label_name = label.get("Name", "")
        confidence = label.get("Confidence", 0.0)

        # バウンディングボックス情報を取得
        instances = label.get("Instances", [])
        for instance in instances:
            bbox = instance.get("BoundingBox", {})
            detections.append({
                "label": label_name,
                "confidence": round(confidence, 1),
                "bounding_box": {
                    "left": bbox.get("Left", 0.0),
                    "top": bbox.get("Top", 0.0),
                    "width": bbox.get("Width", 0.0),
                    "height": bbox.get("Height", 0.0),
                },
            })

        # インスタンスがない場合もラベルとして記録
        if not instances:
            detections.append({
                "label": label_name,
                "confidence": round(confidence, 1),
                "bounding_box": None,
            })

    return detections


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """ダッシュカム映像フレーム抽出 + Rekognition 物体検出

    Lambda 環境では実際の動画デコードが困難なため、メタデータベースの
    アプローチでフレーム抽出をシミュレートする。先頭バイトを Rekognition
    に送信して物体検出を実行する。

    Input:
        {"Key": "recordings/drive_20260115_001.mp4", "Size": 2147483648, ...}

    Output:
        {
            "status": "SUCCESS",
            "file_key": "...",
            "frames_extracted": 120,
            "detections": [...],
            "output_key": "..."
        }
    """
    file_key = event["Key"]
    file_size = event.get("Size", 0)

    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    output_writer = OutputWriter.from_env()

    frame_interval_ms = int(os.environ.get("FRAME_INTERVAL", "1000"))

    logger.info(
        "Frame extraction started: file_key=%s, size=%d, interval=%dms",
        file_key,
        file_size,
        frame_interval_ms,
    )

    # ファイル先頭を取得してフォーマット検証
    try:
        response = s3ap.get_object(file_key)
        # 先頭 64KB を読み取り（フォーマット検証 + Rekognition 用）
        body = response["Body"]
        header_bytes = body.read(65536)
        body.close()
    except Exception as e:
        logger.error("Failed to read file %s: %s", file_key, e)
        return {
            "status": "ERROR",
            "file_key": file_key,
            "error": f"Failed to read file: {e}",
            "frames_extracted": 0,
            "detections": [],
        }

    # フォーマット検証
    video_format = _detect_video_format(header_bytes)
    if video_format is None:
        logger.warning(
            "Unsupported or corrupted video format: %s", file_key
        )
        return {
            "status": "ERROR",
            "file_key": file_key,
            "error": "Unsupported video format or corrupted file",
            "frames_extracted": 0,
            "detections": [],
        }

    # フレーム数推定
    frames_extracted = _estimate_frame_count(file_size, frame_interval_ms)

    # Rekognition で物体検出（先頭バイトを画像として送信）
    # 注: 実際の動画フレームではなくファイルヘッダーを送信するため、
    # 検出結果はシミュレーション。本番では MediaConvert を使用する。
    rekognition_client = boto3.client("rekognition")
    detections = []

    # 先頭フレームの検出をシミュレート
    frame_detections = _run_rekognition_detection(
        rekognition_client, header_bytes[:4096]
    )
    if frame_detections:
        detections.append({
            "frame_index": 0,
            "timestamp_ms": 0,
            "objects": frame_detections,
        })

    # 出力キー生成
    now = datetime.now(timezone.utc)
    file_stem = PurePosixPath(file_key).stem
    output_key = f"detections/{now.strftime('%Y/%m/%d')}/{file_stem}_detections.json"

    # 結果を出力先（標準 S3 または FSxN S3AP）に書き込み
    result = {
        "status": "SUCCESS",
        "file_key": file_key,
        "video_format": video_format,
        "frames_extracted": frames_extracted,
        "detections": detections,
        "output_key": output_key,
    }

    output_writer.put_json(key=output_key, data=result)

    logger.info(
        "Frame extraction completed: file_key=%s, frames=%d, detections=%d",
        file_key,
        frames_extracted,
        len(detections),
    )


    # EMF メトリクス出力
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="frame_extraction")
    metrics.set_dimension("UseCase", os.environ.get("USE_CASE", "autonomous-driving"))
    metrics.put_metric("FilesProcessed", 1.0, "Count")
    metrics.flush()

    return result
