"""旅行・ホスピタリティ業界 (UC20) Facility Inspector Lambda ハンドラ

施設点検画像を分析し、損傷検出・清潔度スコアリング (0-100) を行い、
Bedrock を使用してメンテナンス推奨事項を生成する。

処理フロー:
    1. S3 AP から画像取得
    2. Rekognition で損傷検出・ラベル抽出
    3. 清潔度スコア算出 (0-100)
    4. Bedrock でメンテナンス推奨生成

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用)
    BEDROCK_MODEL_ID: Bedrock モデル ID (default: "anthropic.claude-haiku-4-5-20251001-v1:0")
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import xray_subsegment, EmfMetrics, trace_lambda_handler
from shared.retry_handler import retry_with_backoff, RetryConfig
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)

# 損傷関連ラベル（Rekognition DetectLabels の結果から抽出）
DAMAGE_LABELS: frozenset[str] = frozenset(
    {
        "Crack",
        "Rust",
        "Mold",
        "Stain",
        "Damage",
        "Broken",
        "Deterioration",
        "Corrosion",
        "Leak",
        "Peeling",
        "Dent",
        "Scratch",
        "Discoloration",
        "Wear",
    }
)

# 清潔度に悪影響を与えるラベル
CLEANLINESS_NEGATIVE_LABELS: frozenset[str] = frozenset(
    {
        "Dirt",
        "Stain",
        "Mold",
        "Dust",
        "Debris",
        "Clutter",
        "Mess",
        "Garbage",
        "Trash",
        "Grime",
    }
)

# 良好な状態を示すラベル
CLEANLINESS_POSITIVE_LABELS: frozenset[str] = frozenset(
    {
        "Clean",
        "Tidy",
        "Organized",
        "Polished",
        "Pristine",
        "Maintained",
        "New",
        "Fresh",
    }
)

# 最低信頼度閾値
MIN_CONFIDENCE_THRESHOLD: float = 70.0


def calculate_cleanliness_score(labels: list[dict]) -> int:
    """Rekognition ラベルから清潔度スコアを算出する。

    スコア算出ロジック:
        - 基準スコア: 70
        - ネガティブラベル: 信頼度に応じて減点 (最大 -50)
        - ポジティブラベル: 信頼度に応じて加点 (最大 +30)
        - 最終スコア: 0-100 にクランプ

    Args:
        labels: Rekognition DetectLabels の結果ラベルリスト

    Returns:
        int: 清潔度スコア (0-100)
    """
    base_score: float = 70.0
    negative_penalty: float = 0.0
    positive_bonus: float = 0.0

    for label in labels:
        name = label.get("Name", "")
        confidence = label.get("Confidence", 0.0)

        if confidence < MIN_CONFIDENCE_THRESHOLD:
            continue

        # 信頼度に基づく重み付け (70-100% → 0.0-1.0)
        weight = (confidence - MIN_CONFIDENCE_THRESHOLD) / (100.0 - MIN_CONFIDENCE_THRESHOLD)

        if name in CLEANLINESS_NEGATIVE_LABELS:
            negative_penalty += weight * 15.0
        elif name in CLEANLINESS_POSITIVE_LABELS:
            positive_bonus += weight * 10.0

    # ダメージラベルも清潔度に影響
    for label in labels:
        name = label.get("Name", "")
        confidence = label.get("Confidence", 0.0)
        if confidence >= MIN_CONFIDENCE_THRESHOLD and name in DAMAGE_LABELS:
            weight = (confidence - MIN_CONFIDENCE_THRESHOLD) / (100.0 - MIN_CONFIDENCE_THRESHOLD)
            negative_penalty += weight * 10.0

    # スコア算出
    score = base_score - min(negative_penalty, 50.0) + min(positive_bonus, 30.0)
    return max(0, min(100, int(round(score))))


def detect_damage(labels: list[dict]) -> list[dict]:
    """ラベルから損傷を検出する。

    Args:
        labels: Rekognition ラベルリスト

    Returns:
        list[dict]: 検出された損傷リスト
    """
    damages: list[dict] = []
    for label in labels:
        name = label.get("Name", "")
        confidence = label.get("Confidence", 0.0)
        if name in DAMAGE_LABELS and confidence >= MIN_CONFIDENCE_THRESHOLD:
            damages.append(
                {
                    "type": name,
                    "confidence": round(confidence, 2),
                    "instances": label.get("Instances", []),
                }
            )
    return damages


def generate_maintenance_recommendations(
    damages: list[dict],
    cleanliness_score: int,
    bedrock_client,
    model_id: str,
) -> list[str]:
    """Bedrock でメンテナンス推奨事項を生成する。

    Args:
        damages: 検出された損傷リスト
        cleanliness_score: 清潔度スコア
        bedrock_client: Bedrock boto3 クライアント
        model_id: Bedrock モデル ID

    Returns:
        list[str]: メンテナンス推奨事項リスト
    """
    if not damages and cleanliness_score >= 80:
        return ["No immediate maintenance required. Continue regular inspection schedule."]

    damage_summary = (
        ", ".join([f"{d['type']} (confidence: {d['confidence']}%)" for d in damages])
        if damages
        else "No specific damage detected"
    )

    prompt = (
        "You are a facility maintenance expert for a hotel/hospitality property. "
        "Based on the following inspection findings, provide 3-5 concise maintenance "
        "recommendations in order of priority.\n\n"
        f"Damage detected: {damage_summary}\n"
        f"Cleanliness score: {cleanliness_score}/100\n\n"
        "Provide recommendations as a JSON array of strings. "
        "Each recommendation should be actionable and specific."
    )

    @retry_with_backoff(config=RetryConfig(max_attempts=3))
    def _invoke_bedrock():
        response = bedrock_client.invoke_model(
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
        return json.loads(response["body"].read())

    try:
        result = _invoke_bedrock()
        content = result.get("content", [{}])
        text = content[0].get("text", "[]") if content else "[]"

        # JSON 配列としてパース試行
        try:
            recommendations = json.loads(text)
            if isinstance(recommendations, list):
                return [str(r) for r in recommendations[:5]]
        except json.JSONDecodeError:
            pass

        # プレーンテキストの場合は行分割
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        return lines[:5] if lines else ["Schedule maintenance inspection."]

    except Exception as e:
        logger.warning("Bedrock recommendation generation failed: %s", str(e))
        recommendations = []
        if damages:
            recommendations.append(f"Priority repair needed: {damages[0]['type']} detected.")
        if cleanliness_score < 60:
            recommendations.append("Deep cleaning required for this area.")
        if not recommendations:
            recommendations.append("Schedule routine maintenance inspection.")
        return recommendations


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """Travel Facility Inspector Lambda

    施設点検画像を分析し、状態評価を行う。

    Input event:
        - Key: S3 オブジェクトキー
        - Size: ファイルサイズ
        - category: "facility_image"

    Returns:
        dict: status, key, cleanliness_score, damages, recommendations, errors
    """
    key = event.get("Key", "")
    category = event.get("category", "facility_image")

    logger.info("Processing facility inspection image: key=%s", key)

    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    s3ap_output = S3ApHelper(os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ["S3_ACCESS_POINT"]))
    model_id = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-haiku-4-5-20251001-v1:0")

    rekognition_client = boto3.client("rekognition")
    bedrock_client = boto3.client("bedrock-runtime")

    errors: list[dict] = []

    try:
        # Step 1: 画像取得
        with xray_subsegment(
            name="s3ap_get_image",
            annotations={
                "service_name": "s3",
                "operation": "GetObject",
                "use_case": "travel-document-processing",
            },
        ):
            image_bytes = s3ap.get_object_bytes(key=key)

        # Step 2: Rekognition ラベル検出
        with xray_subsegment(
            name="rekognition_detect_labels",
            annotations={
                "service_name": "rekognition",
                "operation": "DetectLabels",
                "use_case": "travel-document-processing",
            },
        ):

            @retry_with_backoff(config=RetryConfig(max_attempts=3))
            def _detect_labels():
                return rekognition_client.detect_labels(
                    Image={"Bytes": image_bytes},
                    MaxLabels=50,
                    MinConfidence=MIN_CONFIDENCE_THRESHOLD,
                )

            label_response = _detect_labels()

        labels = label_response.get("Labels", [])

        # Step 3: 損傷検出 + 清潔度スコア算出
        damages = detect_damage(labels)
        cleanliness_score = calculate_cleanliness_score(labels)

        logger.info(
            "Facility inspection analysis: key=%s, cleanliness=%d, damage_count=%d",
            key,
            cleanliness_score,
            len(damages),
        )

        # Step 4: Bedrock メンテナンス推奨生成
        with xray_subsegment(
            name="bedrock_recommendations",
            annotations={
                "service_name": "bedrock",
                "operation": "InvokeModel",
                "use_case": "travel-document-processing",
            },
        ):
            recommendations = generate_maintenance_recommendations(damages, cleanliness_score, bedrock_client, model_id)

        # 結果を S3 に出力
        result_key = f"results/facility/{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/{os.path.basename(key)}.json"
        result_data = {
            "source_key": key,
            "category": category,
            "cleanliness_score": cleanliness_score,
            "damages": damages,
            "recommendations": recommendations,
            "labels_detected": len(labels),
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }

        s3ap_output.put_object(
            key=result_key,
            body=json.dumps(result_data, ensure_ascii=False, default=str),
            content_type="application/json",
        )

        # EMF メトリクス
        metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="processing")
        metrics.set_dimension("UseCase", "travel-document-processing")
        metrics.set_dimension("Stage", "facility-inspector")
        metrics.put_metric("SuccessCount", 1.0, "Count")
        metrics.put_metric("CleanlinessScore", float(cleanliness_score), "None")
        metrics.put_metric("DamageCount", float(len(damages)), "Count")
        metrics.flush()

        return {
            "status": "success",
            "key": key,
            "category": category,
            "result_key": result_key,
            "cleanliness_score": cleanliness_score,
            "damages": damages,
            "recommendations": recommendations,
            "errors": [],
        }

    except Exception as e:
        # Requirement 4.6: エラー記録 + 継続
        error_detail = {
            "path": key,
            "category": category,
            "error_type": type(e).__name__,
            "details": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        errors.append(error_detail)

        logger.error(
            "Facility inspection failed: key=%s, error=%s",
            key,
            str(e),
        )

        # エラーを出力バケットに記録
        error_key = f"errors/facility/{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/{os.path.basename(key)}.json"
        try:
            s3ap_output.put_object(
                key=error_key,
                body=json.dumps(error_detail, ensure_ascii=False, default=str),
                content_type="application/json",
            )
        except Exception as write_err:
            logger.error("Failed to write error record: %s", str(write_err))

        # EMF メトリクス
        metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="processing")
        metrics.set_dimension("UseCase", "travel-document-processing")
        metrics.set_dimension("Stage", "facility-inspector")
        metrics.put_metric("ErrorCount", 1.0, "Count")
        metrics.flush()

        return {
            "status": "error",
            "key": key,
            "category": category,
            "errors": errors,
        }
