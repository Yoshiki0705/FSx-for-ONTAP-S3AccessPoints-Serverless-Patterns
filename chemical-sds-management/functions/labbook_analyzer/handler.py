"""化学・素材 (UC28) Lab Book Analyzer Lambda ハンドラ

ラボノート画像から実験パラメータ、結果、観察事項を抽出する。

Requirement 12.3:
    - Textract + Rekognition で構造化抽出

AI/ML サービス:
    - Amazon Textract: テキスト抽出
    - Amazon Rekognition: 画像ラベル検出

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN
    TEXTRACT_REGION: Textract リージョン (default: us-east-1)
"""

from __future__ import annotations

import logging
import os
import time

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler
from shared.retry_handler import RetryConfig, categorize_error, retry_with_backoff

logger = logging.getLogger(__name__)


def extract_text_textract(
    s3ap_alias: str,
    object_key: str,
    textract_client=None,
) -> str:
    """Textract でラボノート画像からテキストを抽出する。"""
    if textract_client is None:
        textract_region = os.environ.get("TEXTRACT_REGION", "us-east-1")
        textract_client = boto3.client("textract", region_name=textract_region)

    @retry_with_backoff(config=RetryConfig(max_attempts=3))
    def _call_textract():
        return textract_client.detect_document_text(
            Document={"S3Object": {"Bucket": s3ap_alias, "Name": object_key}},
        )

    response = _call_textract()
    blocks = response.get("Blocks", [])

    lines: list[str] = []
    for block in blocks:
        if block.get("BlockType") == "LINE":
            text = block.get("Text", "")
            if text:
                lines.append(text)

    return "\n".join(lines)


def detect_labels_rekognition(
    s3ap_alias: str,
    object_key: str,
    rekognition_client=None,
) -> list[dict]:
    """Rekognition でラボノート画像のラベルを検出する。"""
    if rekognition_client is None:
        rekognition_client = boto3.client("rekognition")

    @retry_with_backoff(config=RetryConfig(max_attempts=3))
    def _call_rekognition():
        return rekognition_client.detect_labels(
            Image={"S3Object": {"Bucket": s3ap_alias, "Name": object_key}},
            MinConfidence=70,
            MaxLabels=50,
        )

    response = _call_rekognition()
    return [
        {"name": label.get("Name", ""), "confidence": label.get("Confidence", 0.0)}
        for label in response.get("Labels", [])
    ]


def parse_experiment_data(text: str) -> dict:
    """テキストから実験パラメータ・結果・観察事項を抽出する。

    Args:
        text: Textract 抽出テキスト

    Returns:
        dict: parameters, results, observations
    """
    lines = text.split("\n")
    parameters: list[str] = []
    results: list[str] = []
    observations: list[str] = []

    # キーワードベースで分類
    param_keywords = {"温度", "圧力", "濃度", "pH", "時間", "量", "mol", "temp", "pressure"}
    result_keywords = {"結果", "収率", "yield", "output", "生成", "result"}
    obs_keywords = {"観察", "observation", "note", "色", "変化", "反応", "備考"}

    current_section = None

    for line in lines:
        line_lower = line.lower()

        if any(kw in line_lower for kw in param_keywords):
            parameters.append(line.strip())
            current_section = "parameters"
        elif any(kw in line_lower for kw in result_keywords):
            results.append(line.strip())
            current_section = "results"
        elif any(kw in line_lower for kw in obs_keywords):
            observations.append(line.strip())
            current_section = "observations"
        elif current_section and line.strip():
            # 前のセクションに継続
            if current_section == "parameters":
                parameters.append(line.strip())
            elif current_section == "results":
                results.append(line.strip())
            elif current_section == "observations":
                observations.append(line.strip())

    return {
        "parameters": parameters[:20],
        "results": results[:20],
        "observations": observations[:20],
    }


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """Lab Book Analyzer Lambda

    Input event:
        - objects: ラボノート画像オブジェクトリスト

    Returns:
        dict: results, success_count, error_count
    """
    start_time = time.time()

    s3ap_alias = os.environ.get("S3_ACCESS_POINT", "")

    objects = event.get("objects", [])
    logger.info("Lab book analysis started: %d images", len(objects))

    results: list[dict] = []
    success_count = 0
    error_count = 0

    for obj in objects:
        key = obj.get("Key", "")
        substance_id = obj.get("substance_id")

        try:
            # Textract でテキスト抽出
            text = extract_text_textract(s3ap_alias, key)

            # Rekognition でラベル検出
            labels = detect_labels_rekognition(s3ap_alias, key)

            # 実験データ解析
            experiment_data = parse_experiment_data(text)

            results.append({
                "key": key,
                "substance_id": substance_id,
                "status": "success",
                "experiment_data": experiment_data,
                "labels": labels[:10],
                "text_length": len(text),
            })
            success_count += 1

        except Exception as e:
            error_category = categorize_error(e)
            logger.warning(
                "Lab book analysis failed for %s: %s [%s]",
                key,
                str(e),
                error_category.value,
            )
            results.append({
                "key": key,
                "substance_id": substance_id,
                "status": "error",
                "error_type": error_category.value,
                "error_message": str(e),
            })
            error_count += 1

    processing_duration_ms = int((time.time() - start_time) * 1000)

    logger.info(
        "Lab book analysis completed: success=%d, errors=%d",
        success_count,
        error_count,
    )

    # EMF メトリクス
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="processing")
    metrics.set_dimension("UseCase", "chemical-sds-management")
    metrics.set_dimension("Stage", "labbook-analysis")
    metrics.put_metric("ProcessingDuration", float(processing_duration_ms), "Milliseconds")
    metrics.put_metric("SuccessCount", float(success_count), "Count")
    metrics.put_metric("ErrorCount", float(error_count), "Count")
    metrics.flush()

    return {
        "results": results,
        "success_count": success_count,
        "error_count": error_count,
        "processing_duration_ms": processing_duration_ms,
    }
