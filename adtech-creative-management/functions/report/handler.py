"""広告・マーケティング業界 (UC19) Report Lambda ハンドラ

クリエイティブアセットカタログを JSON および CSV 形式で生成する。
各アセットに対して 1 レコードを出力し、モデレーション不合格アセットを
"requires-review" としてフラグ付けする。

処理フロー:
    1. Visual Analyzer / Text Compliance の結果を受信
    2. アセットカタログ生成（JSON + CSV、1 レコード/アセット）
    3. モデレーション不合格フラグ付け（確信度 ≥ 80%）
    4. S3 出力バケットに書き出し
    5. EMF メトリクス出力 (ProcessingDuration, SuccessCount, ErrorCount)

Requirements: 3.5, 3.6, 3.8, 3.9, 13.7

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用)
    OUTPUT_BUCKET: 出力バケット名
    SNS_TOPIC_ARN: 通知先 SNS トピック ARN
    MODERATION_CONFIDENCE_THRESHOLD: モデレーション確信度閾値 (デフォルト: 80)
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import xray_subsegment, EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)

# CSV カラム定義
CSV_COLUMNS = [
    "asset_key",
    "status",
    "review_status",
    "violation_category",
    "violation_confidence",
    "tags",
    "tag_count",
    "compliance_status",
    "moderation_labels",
    "text_compliance_status",
    "processing_timestamp",
]


def get_moderation_threshold() -> float:
    """モデレーション確信度閾値を環境変数から取得する。

    Returns:
        float: 確信度閾値 (デフォルト: 80.0)
    """
    try:
        return float(os.environ.get("MODERATION_CONFIDENCE_THRESHOLD", "80"))
    except (ValueError, TypeError):
        return 80.0


def generate_report_id() -> str:
    """一意のレポート ID を生成する。"""
    return str(uuid.uuid4())


def evaluate_moderation_status(
    moderation_labels: list[dict[str, Any]],
    threshold: float,
) -> dict[str, Any]:
    """モデレーションラベルを評価し、フラグ付けが必要か判定する。

    Requirement 3.6: Rekognition moderation label confidence ≥ 80% の場合、
    "requires-review" としてフラグ付け。

    Args:
        moderation_labels: モデレーションラベルのリスト
        threshold: 確信度閾値 (%)

    Returns:
        dict: 評価結果
            {
                "review_status": "requires-review" | "approved",
                "violation_category": str | None,
                "violation_confidence": float | None,
            }
    """
    for label in moderation_labels:
        confidence = label.get("confidence", 0.0)
        if confidence >= threshold:
            return {
                "review_status": "requires-review",
                "violation_category": label.get("name", "Unknown"),
                "violation_confidence": confidence,
            }

    return {
        "review_status": "approved",
        "violation_category": None,
        "violation_confidence": None,
    }


def build_catalog_record(
    asset_result: dict[str, Any],
    text_result: dict[str, Any] | None,
    threshold: float,
) -> dict[str, Any]:
    """1 アセットに対するカタログレコードを構築する。

    Requirement 3.5: 1 record per processed asset

    Args:
        asset_result: Visual Analyzer の処理結果
        text_result: Text Compliance の処理結果 (Optional)
        threshold: モデレーション確信度閾値

    Returns:
        dict: カタログレコード
    """
    asset_key = asset_result.get("key", "")
    status = asset_result.get("status", "unknown")
    moderation_labels = asset_result.get("moderation_labels", [])
    tags = asset_result.get("tags", [])
    tag_count = asset_result.get("tag_count", len(tags))
    compliance = asset_result.get("compliance", {})
    processing_timestamp = asset_result.get("processing_timestamp", datetime.now(timezone.utc).isoformat())

    # Requirement 3.6: モデレーション評価
    moderation_eval = evaluate_moderation_status(moderation_labels, threshold)

    # Text Compliance 結果の統合
    text_compliance_status = "not_checked"
    if text_result and text_result.get("status") == "success":
        text_compliance_status = text_result.get("compliance_result", "not_checked")

    record = {
        "asset_key": asset_key,
        "status": status,
        "review_status": moderation_eval["review_status"],
        "violation_category": moderation_eval["violation_category"],
        "violation_confidence": moderation_eval["violation_confidence"],
        "source_file_path": asset_key,
        "tags": tags,
        "tag_count": tag_count,
        "compliance_status": compliance.get("status", "unknown"),
        "compliance_violations": compliance.get("violations", []),
        "moderation_labels": moderation_labels,
        "text_compliance_status": text_compliance_status,
        "processing_timestamp": processing_timestamp,
    }

    return record


def generate_csv_content(catalog_records: list[dict[str, Any]]) -> str:
    """カタログレコードを CSV 形式に変換する。

    Args:
        catalog_records: カタログレコードのリスト

    Returns:
        str: CSV 文字列
    """
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()

    for record in catalog_records:
        row = {
            "asset_key": record.get("asset_key", ""),
            "status": record.get("status", ""),
            "review_status": record.get("review_status", ""),
            "violation_category": record.get("violation_category", ""),
            "violation_confidence": record.get("violation_confidence", ""),
            "tags": ";".join(record.get("tags", [])),
            "tag_count": record.get("tag_count", 0),
            "compliance_status": record.get("compliance_status", ""),
            "moderation_labels": ";".join(
                f"{l.get('name', '')}({l.get('confidence', 0):.1f}%)" for l in record.get("moderation_labels", [])
            ),
            "text_compliance_status": record.get("text_compliance_status", ""),
            "processing_timestamp": record.get("processing_timestamp", ""),
        }
        writer.writerow(row)

    return output.getvalue()


def aggregate_results(event: dict[str, Any]) -> tuple[list[dict], list[dict]]:
    """Step Functions から渡された結果を集約する。

    Args:
        event: Step Functions イベント

    Returns:
        tuple: (visual_results, text_results)
    """
    visual_results = event.get("visual_results", [])
    text_results = event.get("text_results", [])

    # Step Functions Map State の結果は配列
    if not isinstance(visual_results, list):
        visual_results = []
    if not isinstance(text_results, list):
        text_results = []

    return visual_results, text_results


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """Report Lambda ハンドラ

    Step Functions の最終ステップとして呼び出され、アセットカタログを生成する。

    Event 形式 (Step Functions から渡される):
        {
            "visual_results": [...],   # Visual Analyzer 結果 (Map State)
            "text_results": [...],     # Text Compliance 結果 (Map State)
            "discovery": {...}         # Discovery 結果
        }

    Processing Flow:
        1. 結果集約
        2. カタログレコード生成（1 レコード/アセット）
        3. モデレーション不合格フラグ付け
        4. JSON + CSV 出力
        5. EMF メトリクス出力

    Returns:
        dict: レポート生成結果
    """
    start_time = time.time()

    logger.info("Report Lambda started: event_keys=%s", list(event.keys()))

    # 環境設定
    output_bucket = os.environ.get("OUTPUT_BUCKET", "")
    sns_topic_arn = os.environ.get("SNS_TOPIC_ARN", "")
    moderation_threshold = get_moderation_threshold()
    s3_client = boto3.client("s3")

    report_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    report_id = generate_report_id()

    success_count = 0
    error_count = 0
    requires_review_count = 0

    try:
        # Step 1: 結果集約
        with xray_subsegment(
            name="aggregate_results",
            annotations={
                "service_name": "report",
                "operation": "AggregateResults",
                "use_case": "adtech-creative-management",
            },
        ):
            visual_results, text_results = aggregate_results(event)

        # text_results をキーでインデックス化
        text_result_map: dict[str, dict] = {}
        for tr in text_results:
            if isinstance(tr, dict):
                key = tr.get("key", "")
                if key:
                    text_result_map[key] = tr

        # Step 2-3: カタログレコード生成
        catalog_records: list[dict[str, Any]] = []

        with xray_subsegment(
            name="build_catalog",
            annotations={
                "service_name": "report",
                "operation": "BuildCatalog",
                "use_case": "adtech-creative-management",
            },
        ):
            for vr in visual_results:
                if not isinstance(vr, dict):
                    error_count += 1
                    continue

                asset_key = vr.get("key", "")
                status = vr.get("status", "unknown")

                if status == "error":
                    error_count += 1
                else:
                    success_count += 1

                # 対応する text_compliance 結果を取得
                text_result = text_result_map.get(asset_key)

                record = build_catalog_record(
                    asset_result=vr,
                    text_result=text_result,
                    threshold=moderation_threshold,
                )
                catalog_records.append(record)

                if record["review_status"] == "requires-review":
                    requires_review_count += 1

        # visual_results がない場合（全エラー）
        if not visual_results:
            error_count = max(error_count, 1)

        total_processed = success_count + error_count

        # Step 4: カタログ出力 (JSON + CSV)
        catalog_json = {
            "report_id": report_id,
            "use_case": "adtech-creative-management",
            "report_type": "asset_catalog",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "report_date": report_date,
            "moderation_threshold": moderation_threshold,
            "summary": {
                "total_assets": total_processed,
                "success_count": success_count,
                "error_count": error_count,
                "requires_review_count": requires_review_count,
                "approved_count": total_processed - error_count - requires_review_count,
            },
            "assets": catalog_records,
        }

        csv_content = generate_csv_content(catalog_records)

        if output_bucket:
            date_prefix = datetime.now(timezone.utc).strftime("%Y/%m/%d")

            # JSON 出力
            json_key = f"reports/catalog/{date_prefix}/{report_id}.json"
            with xray_subsegment(
                name="write_json_catalog",
                annotations={
                    "service_name": "s3",
                    "operation": "PutObject",
                    "use_case": "adtech-creative-management",
                },
            ):
                s3_client.put_object(
                    Bucket=output_bucket,
                    Key=json_key,
                    Body=json.dumps(catalog_json, default=str, ensure_ascii=False),
                    ContentType="application/json",
                )

            # CSV 出力
            csv_key = f"reports/catalog/{date_prefix}/{report_id}.csv"
            with xray_subsegment(
                name="write_csv_catalog",
                annotations={
                    "service_name": "s3",
                    "operation": "PutObject",
                    "use_case": "adtech-creative-management",
                },
            ):
                s3_client.put_object(
                    Bucket=output_bucket,
                    Key=csv_key,
                    Body=csv_content.encode("utf-8"),
                    ContentType="text/csv; charset=utf-8",
                )

            logger.info(
                "Catalog written: json=%s, csv=%s",
                json_key,
                csv_key,
            )

        # SNS 通知（requires-review が存在する場合）
        if requires_review_count > 0 and sns_topic_arn:
            with xray_subsegment(
                name="publish_review_alert",
                annotations={
                    "service_name": "sns",
                    "operation": "Publish",
                    "use_case": "adtech-creative-management",
                },
            ):
                sns_client = boto3.client("sns")
                review_assets = [r for r in catalog_records if r.get("review_status") == "requires-review"]
                subject = f"[REVIEW] {requires_review_count} assets require moderation review"
                if len(subject) > 100:
                    subject = subject[:97] + "..."

                message = {
                    "alert_type": "moderation_review_required",
                    "report_id": report_id,
                    "report_date": report_date,
                    "requires_review_count": requires_review_count,
                    "assets": [
                        {
                            "key": a["asset_key"],
                            "violation_category": a["violation_category"],
                            "violation_confidence": a["violation_confidence"],
                        }
                        for a in review_assets[:20]
                    ],
                }
                try:
                    sns_client.publish(
                        TopicArn=sns_topic_arn,
                        Subject=subject,
                        Message=json.dumps(message, default=str, ensure_ascii=False),
                    )
                    logger.info(
                        "Review alert published to SNS: %d assets flagged",
                        requires_review_count,
                    )
                except Exception as e:
                    logger.error("Failed to publish SNS alert: %s", str(e))

    except Exception as e:
        logger.error("Report generation failed: %s", str(e))
        error_count = max(error_count, 1)
        raise
    finally:
        # Step 5: EMF メトリクス出力 (Requirement 13.7)
        processing_duration_ms = (time.time() - start_time) * 1000

        metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="report")
        metrics.set_dimension("UseCase", "adtech-creative-management")
        metrics.put_metric("ProcessingDuration", processing_duration_ms, "Milliseconds")
        metrics.put_metric("SuccessCount", float(success_count), "Count")
        metrics.put_metric("ErrorCount", float(error_count), "Count")
        metrics.put_metric("RequiresReviewCount", float(requires_review_count), "Count")
        metrics.flush()

        logger.info(
            "Report Lambda metrics emitted: ProcessingDuration=%.2fms, "
            "SuccessCount=%d, ErrorCount=%d, RequiresReview=%d",
            processing_duration_ms,
            success_count,
            error_count,
            requires_review_count,
        )

    result = {
        "status": "success",
        "report_id": report_id,
        "report_date": report_date,
        "json_key": json_key if output_bucket else "",
        "csv_key": csv_key if output_bucket else "",
        "total_assets": total_processed,
        "success_count": success_count,
        "error_count": error_count,
        "requires_review_count": requires_review_count,
        "processing_duration_ms": round(processing_duration_ms, 2),
    }

    logger.info(
        "Report Lambda completed: total=%d, success=%d, error=%d, review=%d",
        total_processed,
        success_count,
        error_count,
        requires_review_count,
    )

    return result
