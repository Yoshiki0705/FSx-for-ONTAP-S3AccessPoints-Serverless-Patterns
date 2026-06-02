"""電力・ユーティリティ (UC25) Defect Detector Lambda ハンドラ

ドローン画像から設備欠陥を検出し、重大度を評価する。

検出対象:
    - 碍子損傷 (insulator_damage)
    - 導体のたるみ (conductor_sag)
    - 樹木接近 (vegetation_encroachment)

信頼度閾値: 70% (環境変数 DEFECT_CONFIDENCE_THRESHOLD で設定可能)

重大度分類 (severity):
    - critical: 即時対応必要
    - major: 計画内対応必要
    - minor: 監視対象

AI/ML サービス:
    - Amazon Rekognition: 画像ラベル検出
    - Amazon Bedrock: 重大度評価

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用)
    DEFECT_CONFIDENCE_THRESHOLD: 信頼度閾値 (default: 70)
    BEDROCK_MODEL_ID: Bedrock モデル ID
"""

from __future__ import annotations

import json
import logging
import os
import time

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler
from shared.retry_handler import retry_with_backoff, RetryConfig, categorize_error

logger = logging.getLogger(__name__)

# 欠陥検出に関連する Rekognition ラベル
DEFECT_LABEL_MAPPING: dict[str, str] = {
    "crack": "insulator_damage",
    "broken": "insulator_damage",
    "damage": "insulator_damage",
    "fracture": "insulator_damage",
    "corrosion": "insulator_damage",
    "sag": "conductor_sag",
    "droop": "conductor_sag",
    "slack": "conductor_sag",
    "vegetation": "vegetation_encroachment",
    "tree": "vegetation_encroachment",
    "branch": "vegetation_encroachment",
    "overgrowth": "vegetation_encroachment",
}

# 重大度分類
SEVERITY_CRITICAL = "critical"
SEVERITY_MAJOR = "major"
SEVERITY_MINOR = "minor"

VALID_SEVERITIES = frozenset({SEVERITY_CRITICAL, SEVERITY_MAJOR, SEVERITY_MINOR})


def detect_defects_rekognition(
    s3ap_alias: str,
    object_key: str,
    confidence_threshold: float,
    rekognition_client=None,
) -> list[dict]:
    """Rekognition でドローン画像から欠陥関連ラベルを検出する。

    Args:
        s3ap_alias: S3 AP エイリアス
        object_key: 画像オブジェクトキー
        confidence_threshold: 最小信頼度閾値 (0-100)
        rekognition_client: Rekognition クライアント (テスト用)

    Returns:
        list[dict]: 検出された欠陥ラベルのリスト
    """
    if rekognition_client is None:
        rekognition_client = boto3.client("rekognition")

    @retry_with_backoff(config=RetryConfig(max_attempts=3))
    def _call_rekognition():
        return rekognition_client.detect_labels(
            Image={"S3Object": {"Bucket": s3ap_alias, "Name": object_key}},
            MinConfidence=confidence_threshold,
            MaxLabels=100,
        )

    response = _call_rekognition()
    labels = response.get("Labels", [])

    defects: list[dict] = []
    for label in labels:
        label_name = label.get("Name", "").lower()
        for keyword, defect_type in DEFECT_LABEL_MAPPING.items():
            if keyword in label_name:
                defects.append({
                    "label": label.get("Name", ""),
                    "confidence": label.get("Confidence", 0.0),
                    "defect_type": defect_type,
                })
                break

    return defects


def assess_severity_bedrock(
    defects: list[dict],
    equipment_id: str | None,
    bedrock_client=None,
    model_id: str | None = None,
) -> list[dict]:
    """Bedrock で欠陥の重大度を評価する。

    Args:
        defects: Rekognition で検出された欠陥リスト
        equipment_id: 設備 ID
        bedrock_client: Bedrock Runtime クライアント (テスト用)
        model_id: Bedrock モデル ID

    Returns:
        list[dict]: 重大度が付与された欠陥リスト
    """
    if not defects:
        return []

    if bedrock_client is None:
        bedrock_client = boto3.client("bedrock-runtime")

    if model_id is None:
        model_id = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")

    defect_summary = json.dumps(defects, ensure_ascii=False)
    prompt = (
        f"以下の送電設備の欠陥検出結果に対して、重大度を評価してください。\n"
        f"設備ID: {equipment_id or 'unknown'}\n"
        f"検出欠陥: {defect_summary}\n\n"
        f"各欠陥に対して severity を 'critical', 'major', 'minor' のいずれかで分類してください。\n"
        f"- critical: 即時対応が必要（公衆安全リスク、停電リスク）\n"
        f"- major: 計画内での対応が必要（性能劣化が進行中）\n"
        f"- minor: 監視対象（軽微な劣化の初期段階）\n\n"
        f"JSON 配列で回答してください。各要素は {{'defect_type': str, 'severity': str, 'reason': str}} の形式。"
    )

    @retry_with_backoff(config=RetryConfig(max_attempts=3))
    def _call_bedrock():
        return bedrock_client.invoke_model(
            modelId=model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": prompt}],
            }),
        )

    try:
        response = _call_bedrock()
        response_body = json.loads(response["body"].read())
        content_text = response_body.get("content", [{}])[0].get("text", "")

        # JSON 部分を抽出
        severity_data = _parse_severity_response(content_text)

        # defects に severity を付与
        severity_map: dict[str, str] = {}
        for item in severity_data:
            defect_type = item.get("defect_type", "")
            severity = item.get("severity", "minor")
            if severity in VALID_SEVERITIES:
                severity_map[defect_type] = severity

        for defect in defects:
            defect_type = defect.get("defect_type", "")
            defect["severity"] = severity_map.get(defect_type, "minor")

    except Exception as e:
        logger.warning(
            "Bedrock severity assessment failed, defaulting to 'minor': %s", str(e)
        )
        for defect in defects:
            defect["severity"] = "minor"

    return defects


def _parse_severity_response(text: str) -> list[dict]:
    """Bedrock レスポンスから JSON 配列を抽出する。

    Args:
        text: Bedrock のテキストレスポンス

    Returns:
        list[dict]: パースされた重大度データ
    """
    # JSON 配列を探す
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    return []


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """Defect Detector Lambda

    ドローン画像リストに対して欠陥検出 + 重大度評価を行う。

    Input event:
        - objects: ドローン画像オブジェクトリスト (Discovery Lambda の出力)

    Returns:
        dict: results (欠陥検出結果リスト), error_count, success_count
    """
    start_time = time.time()

    s3ap_alias = os.environ.get("S3_ACCESS_POINT", "")
    confidence_threshold = float(
        os.environ.get("DEFECT_CONFIDENCE_THRESHOLD", "70")
    )

    objects = event.get("objects", [])
    logger.info(
        "Defect detection started: %d objects, threshold=%.1f%%",
        len(objects),
        confidence_threshold,
    )

    results: list[dict] = []
    success_count = 0
    error_count = 0

    for obj in objects:
        key = obj.get("Key", "")
        equipment_id = obj.get("equipment_id")
        inspection_date = obj.get("inspection_date")

        try:
            # Rekognition で欠陥ラベル検出
            defects = detect_defects_rekognition(
                s3ap_alias, key, confidence_threshold
            )

            # Bedrock で重大度評価
            if defects:
                defects = assess_severity_bedrock(defects, equipment_id)

            results.append({
                "key": key,
                "equipment_id": equipment_id,
                "inspection_date": inspection_date,
                "status": "success",
                "defect_count": len(defects),
                "defects": defects,
            })
            success_count += 1

        except Exception as e:
            error_category = categorize_error(e)
            logger.warning(
                "Defect detection failed for %s (equipment=%s): %s [%s]",
                key,
                equipment_id,
                str(e),
                error_category.value,
            )

            # Requirement 9.6: skip, record equipment ID + failure reason, continue
            results.append({
                "key": key,
                "equipment_id": equipment_id,
                "inspection_date": inspection_date,
                "status": "error",
                "error_type": error_category.value,
                "error_message": str(e),
            })
            error_count += 1

    processing_duration_ms = int((time.time() - start_time) * 1000)

    logger.info(
        "Defect detection completed: success=%d, errors=%d, duration=%dms",
        success_count,
        error_count,
        processing_duration_ms,
    )

    # EMF メトリクス
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="processing")
    metrics.set_dimension("UseCase", "utilities-asset-inspection")
    metrics.set_dimension("Stage", "defect-detection")
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
