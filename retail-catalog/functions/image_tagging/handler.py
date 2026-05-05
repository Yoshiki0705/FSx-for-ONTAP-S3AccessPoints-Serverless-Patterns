"""小売 / EC 画像タグ付け Lambda ハンドラ

S3 Access Point 経由で商品画像を取得し、Amazon Rekognition DetectLabels で
ラベル検出と信頼度スコアを取得する。信頼度が設定可能な閾値（デフォルト: 70%）
未満の場合は手動レビューフラグを設定する。

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    OUTPUT_BUCKET: S3 出力バケット名
    CONFIDENCE_THRESHOLD: 信頼度閾値 (デフォルト: 70)
    SNS_TOPIC_ARN: SNS トピック ARN (手動レビュー通知用)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import PurePosixPath

import boto3

from shared.exceptions import lambda_error_handler
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)


def detect_labels(rekognition_client, image_bytes: bytes, max_labels: int = 20) -> list[dict]:
    """Rekognition DetectLabels でラベル検出を実行する

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
    """ラベルの最大信頼度を評価し、閾値との比較結果を返す

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


@lambda_error_handler
def handler(event, context):
    """小売 / EC 画像タグ付け Lambda

    商品画像に対して Rekognition DetectLabels を実行し、
    ラベルと信頼度スコアを取得する。閾値未満の場合は手動レビューフラグを設定する。

    Args:
        event: Map ステートからの入力
            {"Key": "products/SKU12345_front.jpg", "Size": 2097152, ...}

    Returns:
        dict: status, file_key, labels, max_confidence, above_threshold, output_key
    """
    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    output_bucket = os.environ["OUTPUT_BUCKET"]
    confidence_threshold = float(os.environ.get("CONFIDENCE_THRESHOLD", "70"))
    file_key = event["Key"]

    logger.info(
        "Image tagging started: file_key=%s, threshold=%.1f",
        file_key,
        confidence_threshold,
    )

    # S3 AP 経由で画像を取得
    response = s3ap.get_object(file_key)
    image_bytes = response["Body"].read()

    # Rekognition DetectLabels 実行
    rekognition_client = boto3.client("rekognition")
    labels = detect_labels(rekognition_client, image_bytes)

    # 信頼度評価
    max_confidence, above_threshold = evaluate_confidence(labels, confidence_threshold)

    # ステータス判定
    status = "SUCCESS" if above_threshold else "MANUAL_REVIEW"

    # 出力キー生成（日付パーティション付き）
    now = datetime.now(timezone.utc)
    file_stem = PurePosixPath(file_key).stem
    output_key = f"tags/{now.strftime('%Y/%m/%d')}/{file_stem}.json"

    # タグ結果を S3 出力バケットに書き込み
    output_data = {
        "file_key": file_key,
        "status": status,
        "labels": labels,
        "max_confidence": max_confidence,
        "above_threshold": above_threshold,
        "confidence_threshold": confidence_threshold,
        "tagged_at": now.isoformat(),
    }

    s3_client = boto3.client("s3")
    s3_client.put_object(
        Bucket=output_bucket,
        Key=output_key,
        Body=json.dumps(output_data, default=str).encode("utf-8"),
        ContentType="application/json",
    )

    logger.info(
        "Image tagging completed: file_key=%s, status=%s, "
        "max_confidence=%.2f, label_count=%d",
        file_key,
        status,
        max_confidence,
        len(labels),
    )

    return {
        "status": status,
        "file_key": file_key,
        "labels": labels,
        "max_confidence": max_confidence,
        "above_threshold": above_threshold,
        "output_key": output_key,
    }
