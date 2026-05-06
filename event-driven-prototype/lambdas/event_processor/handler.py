"""Event-Driven Prototype: イベント処理 Lambda ハンドラ

S3 Event Notification → EventBridge → Step Functions 経由で呼び出される。
UC11 (Retail Catalog) と同一の処理ロジックを実装:
  1. S3 から画像を取得
  2. Rekognition DetectLabels で画像タグ付け
  3. Bedrock でカタログメタデータ生成
  4. 結果を S3 出力バケットに書き込み

このプロトタイプは通常の S3 バケットを使用して、
将来の FSx ONTAP S3 AP ネイティブ通知動作をシミュレートする。

Environment Variables:
    SOURCE_BUCKET: S3 ソースバケット名
    OUTPUT_BUCKET: S3 出力バケット名
    CONFIDENCE_THRESHOLD: Rekognition 信頼度閾値 (デフォルト: 70)
    BEDROCK_MODEL_ID: Bedrock モデル ID
    USE_CASE: ユースケース名 (event-driven-prototype)
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import PurePosixPath

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)


def detect_labels(rekognition_client, image_bytes: bytes, max_labels: int = 20) -> list[dict]:
    """Rekognition DetectLabels でラベル検出を実行する。

    Args:
        rekognition_client: boto3 Rekognition クライアント
        image_bytes: 画像バイナリデータ
        max_labels: 最大ラベル数

    Returns:
        list[dict]: 検出されたラベルのリスト [{"name": str, "confidence": float}]
    """
    response = rekognition_client.detect_labels(
        Image={"Bytes": image_bytes},
        MaxLabels=max_labels,
    )

    labels = []
    for label in response.get("Labels", []):
        labels.append({
            "name": label["Name"],
            "confidence": round(label["Confidence"], 2),
        })

    return labels


def evaluate_confidence(labels: list[dict], threshold: float) -> tuple[float, bool]:
    """ラベルの最大信頼度を評価し、閾値との比較結果を返す。

    Args:
        labels: 検出されたラベルのリスト
        threshold: 信頼度閾値 (0-100)

    Returns:
        tuple: (max_confidence, above_threshold)
    """
    if not labels:
        return 0.0, False

    max_confidence = max(label["confidence"] for label in labels)
    above_threshold = max_confidence >= threshold

    return max_confidence, above_threshold


def generate_catalog_metadata(
    bedrock_client, model_id: str, file_key: str, labels: list[dict]
) -> dict:
    """Bedrock を使用してカタログメタデータを生成する。

    Args:
        bedrock_client: boto3 Bedrock Runtime クライアント
        model_id: Bedrock モデル ID
        file_key: ファイルキー
        labels: 検出されたラベルのリスト

    Returns:
        dict: 生成されたカタログメタデータ
    """
    label_text = ", ".join([f"{l['name']} ({l['confidence']}%)" for l in labels[:10]])
    prompt = (
        f"Generate product catalog metadata for an image with the following detected labels: "
        f"{label_text}. "
        f"File path: {file_key}. "
        f"Return a JSON object with fields: title, description, category, tags."
    )

    body = json.dumps({
        "inputText": prompt,
        "textGenerationConfig": {
            "maxTokenCount": 512,
            "temperature": 0.3,
        },
    })

    try:
        response = bedrock_client.invoke_model(
            modelId=model_id,
            body=body,
            contentType="application/json",
            accept="application/json",
        )
        response_body = json.loads(response["body"].read())
        generated_text = response_body.get("results", [{}])[0].get("outputText", "")

        # Try to parse as JSON, fallback to raw text
        try:
            metadata = json.loads(generated_text)
        except (json.JSONDecodeError, TypeError):
            metadata = {
                "title": PurePosixPath(file_key).stem,
                "description": generated_text[:500] if generated_text else "",
                "category": "uncategorized",
                "tags": [l["name"] for l in labels[:5]],
            }
    except Exception as e:
        logger.warning("Bedrock invocation failed: %s. Using fallback metadata.", str(e))
        metadata = {
            "title": PurePosixPath(file_key).stem,
            "description": f"Auto-generated from {len(labels)} detected labels",
            "category": "uncategorized",
            "tags": [l["name"] for l in labels[:5]],
        }

    return metadata


def process_image(
    s3_client,
    rekognition_client,
    bedrock_client,
    source_bucket: str,
    output_bucket: str,
    file_key: str,
    confidence_threshold: float,
    bedrock_model_id: str,
    event_time: str | None = None,
) -> dict:
    """画像処理のコアロジック。

    UC11 (Retail Catalog) と同一の処理フロー:
    1. S3 から画像取得
    2. Rekognition でラベル検出
    3. Bedrock でメタデータ生成
    4. 結果を S3 出力バケットに書き込み

    Args:
        s3_client: boto3 S3 クライアント
        rekognition_client: boto3 Rekognition クライアント
        bedrock_client: boto3 Bedrock Runtime クライアント
        source_bucket: ソースバケット名
        output_bucket: 出力バケット名
        file_key: ファイルキー
        confidence_threshold: 信頼度閾値
        bedrock_model_id: Bedrock モデル ID
        event_time: イベント発生時刻 (ISO 8601)

    Returns:
        dict: 処理結果
    """
    processing_start = time.time()

    # 1. S3 から画像を取得
    response = s3_client.get_object(Bucket=source_bucket, Key=file_key)
    image_bytes = response["Body"].read()
    file_size = len(image_bytes)

    # 2. Rekognition DetectLabels 実行
    labels = detect_labels(rekognition_client, image_bytes)

    # 3. 信頼度評価
    max_confidence, above_threshold = evaluate_confidence(labels, confidence_threshold)
    status = "SUCCESS" if above_threshold else "MANUAL_REVIEW"

    # 4. Bedrock でカタログメタデータ生成
    catalog_metadata = generate_catalog_metadata(
        bedrock_client, bedrock_model_id, file_key, labels
    )

    # 5. 出力キー生成（日付パーティション付き）
    now = datetime.now(timezone.utc)
    file_stem = PurePosixPath(file_key).stem
    tags_output_key = f"tags/{now.strftime('%Y/%m/%d')}/{file_stem}.json"
    metadata_output_key = f"metadata/{now.strftime('%Y/%m/%d')}/{file_stem}.json"

    # 6. タグ結果を S3 出力バケットに書き込み
    tags_data = {
        "file_key": file_key,
        "status": status,
        "labels": labels,
        "max_confidence": max_confidence,
        "above_threshold": above_threshold,
        "confidence_threshold": confidence_threshold,
        "tagged_at": now.isoformat(),
        "trigger_mode": "event-driven",
    }

    s3_client.put_object(
        Bucket=output_bucket,
        Key=tags_output_key,
        Body=json.dumps(tags_data, default=str).encode("utf-8"),
        ContentType="application/json",
    )

    # 7. カタログメタデータを S3 出力バケットに書き込み
    metadata_data = {
        "file_key": file_key,
        "catalog_metadata": catalog_metadata,
        "labels": labels,
        "generated_at": now.isoformat(),
        "trigger_mode": "event-driven",
    }

    s3_client.put_object(
        Bucket=output_bucket,
        Key=metadata_output_key,
        Body=json.dumps(metadata_data, default=str).encode("utf-8"),
        ContentType="application/json",
    )

    processing_end = time.time()
    processing_duration_ms = (processing_end - processing_start) * 1000

    # レイテンシ計算
    event_to_processing_ms = None
    if event_time:
        try:
            event_dt = datetime.fromisoformat(event_time.replace("Z", "+00:00"))
            event_to_processing_ms = (processing_start - event_dt.timestamp()) * 1000
        except (ValueError, TypeError):
            pass

    return {
        "status": status,
        "file_key": file_key,
        "file_size": file_size,
        "labels": labels,
        "max_confidence": max_confidence,
        "above_threshold": above_threshold,
        "catalog_metadata": catalog_metadata,
        "tags_output_key": tags_output_key,
        "metadata_output_key": metadata_output_key,
        "processing_duration_ms": round(processing_duration_ms, 2),
        "event_to_processing_ms": round(event_to_processing_ms, 2) if event_to_processing_ms else None,
        "event_time": event_time,
        "processed_at": now.isoformat(),
    }


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """Event-Driven Prototype イベント処理 Lambda。

    EventBridge 経由で S3 Event Notification を受信し、
    UC11 互換の画像処理パイプラインを実行する。

    Args:
        event: EventBridge からの S3 イベント or Step Functions 入力
            {
                "detail": {
                    "bucket": {"name": "..."},
                    "object": {"key": "...", "size": ...},
                    ...
                },
                "time": "2024-01-15T10:30:00Z"
            }

    Returns:
        dict: 処理結果
    """
    source_bucket = os.environ["SOURCE_BUCKET"]
    output_bucket = os.environ["OUTPUT_BUCKET"]
    confidence_threshold = float(os.environ.get("CONFIDENCE_THRESHOLD", "70"))
    bedrock_model_id = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")

    # EventBridge イベントからファイル情報を抽出
    detail = event.get("detail", {})
    file_key = detail.get("object", {}).get("key", "")
    event_time = event.get("time")

    if not file_key:
        # Step Functions 直接呼び出しの場合
        file_key = event.get("Key", event.get("file_key", ""))
        event_time = event.get("event_time")

    if not file_key:
        raise ValueError("No file key found in event")

    logger.info(
        "Event processing started: file_key=%s, event_time=%s",
        file_key,
        event_time,
    )

    # AWS クライアント初期化
    s3_client = boto3.client("s3")
    rekognition_client = boto3.client("rekognition")
    bedrock_client = boto3.client("bedrock-runtime")

    # 画像処理実行
    result = process_image(
        s3_client=s3_client,
        rekognition_client=rekognition_client,
        bedrock_client=bedrock_client,
        source_bucket=source_bucket,
        output_bucket=output_bucket,
        file_key=file_key,
        confidence_threshold=confidence_threshold,
        bedrock_model_id=bedrock_model_id,
        event_time=event_time,
    )

    logger.info(
        "Event processing completed: file_key=%s, status=%s, "
        "processing_duration_ms=%.2f",
        file_key,
        result["status"],
        result["processing_duration_ms"],
    )

    return result
