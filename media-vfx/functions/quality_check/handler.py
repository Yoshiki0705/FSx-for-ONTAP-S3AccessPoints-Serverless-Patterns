"""メディア VFX Quality Check Lambda ハンドラ

レンダリング完了後の出力情報を受け取り、Amazon Rekognition で
品質評価（解像度、アーティファクト、色一貫性）を実行する。

品質が閾値を超えた場合は S3 AP に PutObject で出力を書き込み、
閾値未満の場合は再レンダリングフラグを設定し SNS 通知を送信する。

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用、省略時は S3_ACCESS_POINT を使用)
    SNS_TOPIC_ARN: 品質不合格時の通知先 SNS Topic ARN
    QUALITY_THRESHOLD: 品質評価の閾値（デフォルト: 80.0）
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime

import boto3

from shared.exceptions import lambda_error_handler
from shared.s3ap_helper import S3ApHelper
from shared.observability import xray_subsegment, EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)


def evaluate_quality(labels: list[dict], threshold: float) -> dict:
    """Rekognition ラベルに基づいて品質評価を行う

    テスト可能なヘルパー関数として抽出。
    全ラベルの平均信頼度スコアを品質スコアとして使用する。

    Args:
        labels: Rekognition DetectLabels の結果ラベルリスト
        threshold: 品質合格の閾値 (0.0 - 100.0)

    Returns:
        dict: quality_score, passed, details
    """
    if not labels:
        return {
            "quality_score": 0.0,
            "passed": False,
            "details": "No labels detected — unable to assess quality",
        }

    # 全ラベルの平均信頼度を品質スコアとする
    avg_confidence = sum(label["Confidence"] for label in labels) / len(labels)

    passed = avg_confidence >= threshold

    return {
        "quality_score": round(avg_confidence, 2),
        "passed": passed,
        "details": (
            "Quality check passed"
            if passed
            else f"Quality score {avg_confidence:.1f} below threshold {threshold:.1f}"
        ),
    }


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """Quality Check Lambda

    レンダリング出力情報を受け取り、Rekognition で品質評価を実行する。
    合格時は S3 AP に PutObject、不合格時は SNS 通知を送信する。

    Args:
        event: 前ステップからの入力。以下のキーを含む:
            - job_id (str): Deadline Cloud ジョブ ID
            - asset_key (str): 元アセットの S3 キー
            - output_bucket (str): レンダリング出力バケット

    Returns:
        dict: asset_key, quality_score, passed, output_key, status
    """
    job_id = event.get("job_id", "unknown")
    asset_key = event.get("asset_key")
    if not asset_key:
        logger.warning("No asset_key in event — skipping quality check: %s", json.dumps(event)[:200])
        return {
            "status": "SKIPPED",
            "reason": "No asset_key provided (upstream step may have failed)",
        }
    threshold = float(os.environ.get("QUALITY_THRESHOLD", "80.0"))

    logger.info(
        "Quality Check started: job_id=%s, asset_key=%s, threshold=%.1f",
        job_id,
        asset_key,
        threshold,
    )

    # レンダリング出力を S3 AP から取得
    s3ap_output = S3ApHelper(
        os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ["S3_ACCESS_POINT"])
    )
    rendered_key = f"rendered/{asset_key.rsplit('/', 1)[-1]}"

    rendered_response = s3ap_output.get_object(rendered_key)
    rendered_bytes = rendered_response["Body"].read()

    logger.info(
        "Rendered output retrieved: key=%s, size=%d bytes",
        rendered_key,
        len(rendered_bytes),
    )

    # Rekognition DetectLabels で品質評価
    rekognition_client = boto3.client("rekognition")
    detect_response = rekognition_client.detect_labels(
        Image={"Bytes": rendered_bytes},
        MaxLabels=30,
        MinConfidence=10.0,
    )

    labels = detect_response.get("Labels", [])

    # 品質評価
    quality_result = evaluate_quality(labels, threshold)

    logger.info(
        "Quality evaluation: job_id=%s, score=%.1f, passed=%s",
        job_id,
        quality_result["quality_score"],
        quality_result["passed"],
    )

    result = {
        "job_id": job_id,
        "asset_key": asset_key,
        "quality_score": quality_result["quality_score"],
        "passed": quality_result["passed"],
        "details": quality_result["details"],
        "labels_count": len(labels),
        "evaluated_at": datetime.utcnow().isoformat(),
    }

    if quality_result["passed"]:
        # 品質合格: S3 AP に PutObject で出力を書き込み
        s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
        output_key = f"approved/{asset_key.rsplit('/', 1)[-1]}"
        s3ap.put_object(
            key=output_key,
            body=rendered_bytes,
            content_type="application/octet-stream",
        )

        result["output_key"] = output_key
        result["status"] = "APPROVED"

        logger.info(
            "Quality passed — output written to S3 AP: %s",
            output_key,
        )
    else:
        # 品質不合格: SNS 通知を送信
        sns_client = boto3.client("sns")
        sns_topic_arn = os.environ["SNS_TOPIC_ARN"]

        notification_message = {
            "event": "QUALITY_CHECK_FAILED",
            "job_id": job_id,
            "asset_key": asset_key,
            "quality_score": quality_result["quality_score"],
            "threshold": threshold,
            "details": quality_result["details"],
            "action_required": "Re-render the asset with adjusted parameters",
        }

        sns_client.publish(
            TopicArn=sns_topic_arn,
            Subject=f"VFX Quality Check Failed: {asset_key.rsplit('/', 1)[-1]}",
            Message=json.dumps(notification_message, indent=2),
        )

        result["status"] = "REJECTED"
        result["flagged_for_rerender"] = True

        logger.warning(
            "Quality failed — SNS notification sent: job_id=%s, score=%.1f",
            job_id,
            quality_result["quality_score"],
        )


    # EMF メトリクス出力
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="quality_check")
    metrics.set_dimension("UseCase", os.environ.get("USE_CASE", "media-vfx"))
    metrics.put_metric("FilesProcessed", 1.0, "Count")
    metrics.flush()

    return result
