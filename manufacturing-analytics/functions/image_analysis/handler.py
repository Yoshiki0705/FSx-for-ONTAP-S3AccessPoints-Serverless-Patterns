"""製造業 Image Analysis Lambda ハンドラ

Map ステートから画像ファイル情報を受け取り、Amazon Rekognition で
欠陥検出を実行する。検出結果を JSON 形式で S3 AP に書き出し、
信頼度スコアが閾値未満の場合は手動レビューフラグを設定する。

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用、省略時は S3_ACCESS_POINT を使用)
    CONFIDENCE_THRESHOLD: 欠陥検出の信頼度閾値（デフォルト: 80.0）
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime

import boto3

from shared.exceptions import lambda_error_handler
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)


def should_flag_for_review(confidence: float, threshold: float) -> bool:
    """信頼度スコアに基づいて手動レビューフラグを判定する

    テスト可能なヘルパー関数として抽出。
    信頼度が閾値未満の場合は手動レビューが必要と判定する。

    Args:
        confidence: Rekognition の信頼度スコア (0.0 - 100.0)
        threshold: 手動レビュー判定の閾値

    Returns:
        bool: True の場合、手動レビューが必要
    """
    return confidence < threshold


@lambda_error_handler
def handler(event, context):
    """Image Analysis Lambda

    Map ステートから画像ファイル情報を受け取り、
    Rekognition DetectLabels で欠陥検出を実行する。

    Args:
        event: Map ステートからの入力。以下のキーを含む:
            - Key (str): 画像ファイルの S3 キー
            - Size (int): ファイルサイズ

    Returns:
        dict: output_bucket, output_key, original_key, labels,
              flagged_for_review, status
    """
    image_key = event["Key"]
    threshold = float(os.environ.get("CONFIDENCE_THRESHOLD", "80.0"))

    logger.info(
        "Image Analysis started: image_key=%s, threshold=%.1f",
        image_key,
        threshold,
    )

    # S3 AP から画像ファイルを取得
    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    response = s3ap.get_object(image_key)
    image_bytes = response["Body"].read()

    logger.info(
        "Image file retrieved: key=%s, size=%d bytes",
        image_key,
        len(image_bytes),
    )

    # Rekognition DetectLabels で欠陥検出
    rekognition_client = boto3.client("rekognition")
    detect_response = rekognition_client.detect_labels(
        Image={"Bytes": image_bytes},
        MaxLabels=20,
        MinConfidence=10.0,
    )

    labels = detect_response.get("Labels", [])

    # 最低信頼度スコアを取得（ラベルがない場合は 0.0）
    min_confidence = (
        min(label["Confidence"] for label in labels) if labels else 0.0
    )

    # 手動レビューフラグ判定
    flagged = should_flag_for_review(min_confidence, threshold)

    # 結果 JSON を構築
    result = {
        "image_key": image_key,
        "analyzed_at": datetime.utcnow().isoformat(),
        "labels": [
            {
                "name": label["Name"],
                "confidence": label["Confidence"],
                "instances": [
                    {
                        "bounding_box": inst.get("BoundingBox", {}),
                        "confidence": inst.get("Confidence", 0.0),
                    }
                    for inst in label.get("Instances", [])
                ],
            }
            for label in labels
        ],
        "min_confidence": min_confidence,
        "threshold": threshold,
        "flagged_for_review": flagged,
    }

    # 結果 JSON を S3 AP に書き出し
    s3ap_output = S3ApHelper(
        os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ["S3_ACCESS_POINT"])
    )
    output_key = (
        f"image-analysis/{datetime.utcnow().strftime('%Y/%m/%d')}"
        f"/{image_key.rsplit('/', 1)[-1]}.json"
    )

    s3ap_output.put_object(
        key=output_key,
        body=json.dumps(result, default=str),
        content_type="application/json",
    )

    logger.info(
        "Image Analysis completed: key=%s, labels=%d, "
        "min_confidence=%.1f, flagged=%s, output=%s",
        image_key,
        len(labels),
        min_confidence,
        flagged,
        output_key,
    )

    return {
        "output_key": output_key,
        "original_key": image_key,
        "labels": len(labels),
        "flagged_for_review": flagged,
        "status": "SUCCESS",
    }
