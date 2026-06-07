"""電力・ユーティリティ (UC25) Thermal Analyzer Lambda ハンドラ

FLIR サーマルデータを処理し、ホットスポットを分類する。

ホットスポット判定:
    隣接コンポーネントベースラインからの温度差が 10°C 以上の場合にホットスポットと分類。
    (THERMAL_DIFFERENTIAL_THRESHOLD 環境変数で設定可能)

分類:
    - hot_spot: ≥10°C 差分 (デフォルト)
    - severe_hot_spot: ≥20°C 差分

AI/ML サービス:
    - Amazon Bedrock: サーマルデータ解釈

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用)
    THERMAL_DIFFERENTIAL_THRESHOLD: 温度差閾値 (default: 10.0)
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

# ホットスポット分類
CLASSIFICATION_HOT_SPOT = "hot_spot"
CLASSIFICATION_SEVERE_HOT_SPOT = "severe_hot_spot"
CLASSIFICATION_NORMAL = "normal"


def classify_thermal_differential(
    temperature_differential: float,
    threshold: float,
) -> str:
    """温度差分に基づきホットスポットを分類する。

    Args:
        temperature_differential: コンポーネント間の温度差 (°C)
        threshold: ホットスポット閾値 (°C)

    Returns:
        str: 分類結果
    """
    if temperature_differential >= threshold * 2:
        return CLASSIFICATION_SEVERE_HOT_SPOT
    if temperature_differential >= threshold:
        return CLASSIFICATION_HOT_SPOT
    return CLASSIFICATION_NORMAL


def extract_thermal_data(
    thermal_metadata: dict,
) -> list[dict]:
    """サーマルメタデータから温度差分データを抽出する。

    FLIR ファイルから抽出されたメタデータを解析し、
    各コンポーネントの温度差分を計算する。

    Args:
        thermal_metadata: サーマル画像のメタデータ

    Returns:
        list[dict]: コンポーネント別温度データ
    """
    components: list[dict] = []

    # コンポーネント温度データ
    measurements = thermal_metadata.get("measurements", [])
    for measurement in measurements:
        component_id = measurement.get("component_id", "unknown")
        max_temp = measurement.get("max_temperature")
        ambient_temp = measurement.get("ambient_temperature")
        baseline_temp = measurement.get("baseline_temperature")

        if max_temp is not None and baseline_temp is not None:
            differential = float(max_temp) - float(baseline_temp)
            components.append(
                {
                    "component_id": component_id,
                    "max_temperature": float(max_temp),
                    "baseline_temperature": float(baseline_temp),
                    "ambient_temperature": float(ambient_temp) if ambient_temp else None,
                    "temperature_differential": round(differential, 1),
                }
            )
        elif max_temp is not None and ambient_temp is not None:
            # ベースラインがない場合は環境温度をベースラインとする
            differential = float(max_temp) - float(ambient_temp)
            components.append(
                {
                    "component_id": component_id,
                    "max_temperature": float(max_temp),
                    "baseline_temperature": float(ambient_temp),
                    "ambient_temperature": float(ambient_temp),
                    "temperature_differential": round(differential, 1),
                }
            )

    return components


def analyze_thermal_with_bedrock(
    hot_spots: list[dict],
    equipment_id: str | None,
    bedrock_client=None,
    model_id: str | None = None,
) -> list[dict]:
    """Bedrock でサーマルホットスポットの解釈を行う。

    Args:
        hot_spots: ホットスポットデータリスト
        equipment_id: 設備 ID
        bedrock_client: Bedrock Runtime クライアント (テスト用)
        model_id: Bedrock モデル ID

    Returns:
        list[dict]: 解釈結果が付与されたホットスポットリスト
    """
    if not hot_spots:
        return []

    if bedrock_client is None:
        bedrock_client = boto3.client("bedrock-runtime")

    if model_id is None:
        model_id = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")

    hot_spot_summary = json.dumps(hot_spots, ensure_ascii=False)
    prompt = (
        f"以下の送電設備のサーマル検査データを解釈してください。\n"
        f"設備ID: {equipment_id or 'unknown'}\n"
        f"ホットスポットデータ: {hot_spot_summary}\n\n"
        f"各ホットスポットについて以下を分析してください:\n"
        f"1. 推定原因 (接続不良、過負荷、劣化等)\n"
        f"2. 推奨アクション (即時対応、計画的保守、監視継続)\n"
        f"3. 緊急度 (high/medium/low)\n\n"
        f"JSON 配列で回答してください。"
    )

    @retry_with_backoff(config=RetryConfig(max_attempts=3))
    def _call_bedrock():
        return bedrock_client.invoke_model(
            modelId=model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(
                {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": prompt}],
                }
            ),
        )

    try:
        response = _call_bedrock()
        response_body = json.loads(response["body"].read())
        content_text = response_body.get("content", [{}])[0].get("text", "")

        # JSON 配列抽出
        interpretations = _parse_json_array(content_text)

        # ホットスポットに解釈を付与
        for i, hot_spot in enumerate(hot_spots):
            if i < len(interpretations):
                hot_spot["interpretation"] = interpretations[i]

    except Exception as e:
        logger.warning("Bedrock thermal interpretation failed: %s", str(e))

    return hot_spots


def _parse_json_array(text: str) -> list[dict]:
    """テキストから JSON 配列を抽出する。"""
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    return []


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """Thermal Analyzer Lambda

    FLIR サーマルデータを処理し、ホットスポットを分類する。

    Input event:
        - objects: サーマル画像オブジェクトリスト (Discovery Lambda の出力)

    Returns:
        dict: results, hot_spots, hot_spot_count, success_count, error_count
    """
    start_time = time.time()

    thermal_threshold = float(os.environ.get("THERMAL_DIFFERENTIAL_THRESHOLD", "10.0"))

    objects = event.get("objects", [])
    logger.info(
        "Thermal analysis started: %d objects, threshold=%.1f°C",
        len(objects),
        thermal_threshold,
    )

    results: list[dict] = []
    all_hot_spots: list[dict] = []
    success_count = 0
    error_count = 0

    for obj in objects:
        key = obj.get("Key", "")
        equipment_id = obj.get("equipment_id")
        inspection_date = obj.get("inspection_date")

        try:
            # サーマルメタデータ抽出
            # 実環境では S3 からファイルを取得し FLIR SDK で解析
            # ここではメタデータ形式でのサーマルデータ処理を実装
            thermal_metadata = obj.get("thermal_metadata", {})

            # 温度差分データ抽出
            components = extract_thermal_data(thermal_metadata)

            # ホットスポット分類
            hot_spots: list[dict] = []
            for component in components:
                differential = component["temperature_differential"]
                classification = classify_thermal_differential(differential, thermal_threshold)
                component["classification"] = classification
                if classification != CLASSIFICATION_NORMAL:
                    hot_spots.append(component)

            # Bedrock でホットスポット解釈
            if hot_spots:
                hot_spots = analyze_thermal_with_bedrock(hot_spots, equipment_id)

            results.append(
                {
                    "key": key,
                    "equipment_id": equipment_id,
                    "inspection_date": inspection_date,
                    "status": "success",
                    "component_count": len(components),
                    "hot_spot_count": len(hot_spots),
                    "hot_spots": hot_spots,
                }
            )
            all_hot_spots.extend(hot_spots)
            success_count += 1

        except Exception as e:
            error_category = categorize_error(e)
            logger.warning(
                "Thermal analysis failed for %s (equipment=%s): %s [%s]",
                key,
                equipment_id,
                str(e),
                error_category.value,
            )

            # Requirement 9.6: skip, record equipment ID + failure reason, continue
            results.append(
                {
                    "key": key,
                    "equipment_id": equipment_id,
                    "inspection_date": inspection_date,
                    "status": "error",
                    "error_type": error_category.value,
                    "error_message": str(e),
                }
            )
            error_count += 1

    processing_duration_ms = int((time.time() - start_time) * 1000)

    logger.info(
        "Thermal analysis completed: success=%d, errors=%d, hot_spots=%d, duration=%dms",
        success_count,
        error_count,
        len(all_hot_spots),
        processing_duration_ms,
    )

    # EMF メトリクス
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="processing")
    metrics.set_dimension("UseCase", "utilities-asset-inspection")
    metrics.set_dimension("Stage", "thermal-analysis")
    metrics.put_metric("ProcessingDuration", float(processing_duration_ms), "Milliseconds")
    metrics.put_metric("SuccessCount", float(success_count), "Count")
    metrics.put_metric("ErrorCount", float(error_count), "Count")
    metrics.put_metric("HotSpotCount", float(len(all_hot_spots)), "Count")
    metrics.flush()

    return {
        "results": results,
        "hot_spots": all_hot_spots,
        "hot_spot_count": len(all_hot_spots),
        "success_count": success_count,
        "error_count": error_count,
        "processing_duration_ms": processing_duration_ms,
    }
