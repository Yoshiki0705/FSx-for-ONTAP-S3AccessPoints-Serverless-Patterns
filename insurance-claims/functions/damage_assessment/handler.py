"""保険 / 損害査定 損害評価 Lambda ハンドラ

Rekognition で損害検出（車両損害ラベル、重大度指標、影響箇所）を実行する。
Bedrock で構造化損害評価（damage_type, severity_level, affected_components）を生成する。
損害ラベル未検出時は手動レビューフラグと理由コードを設定する。

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    OUTPUT_BUCKET: S3 出力バケット名
    BEDROCK_MODEL_ID: Bedrock モデル ID (デフォルト: amazon.nova-lite-v1:0)
    LOG_PII_DATA: PII データのログ出力 (デフォルト: false)
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

# 損害関連ラベル
DAMAGE_LABELS = [
    "Damage", "Dent", "Scratch", "Crack", "Broken",
    "Collision", "Accident", "Wreck",
]

# 車両コンポーネントラベル
VEHICLE_COMPONENT_LABELS = [
    "Bumper", "Hood", "Fender", "Door", "Window", "Windshield",
    "Headlight", "Taillight", "Mirror", "Wheel", "Tire", "Roof",
]


def sanitize_for_logging(data: dict) -> dict:
    """PII データをログ出力用にサニタイズする"""
    log_pii = os.environ.get("LOG_PII_DATA", "false").lower() == "true"
    if log_pii:
        return data
    sanitized = {}
    pii_fields = {"name", "address", "phone", "email", "policy_number", "claimant"}
    for key, value in data.items():
        if any(pii in key.lower() for pii in pii_fields):
            sanitized[key] = "***REDACTED***"
        else:
            sanitized[key] = value
    return sanitized


def detect_damage_labels(
    rekognition_client, image_bytes: bytes, max_labels: int = 50
) -> list[dict]:
    """Rekognition DetectLabels で損害関連ラベルを検出する

    Args:
        rekognition_client: boto3 Rekognition クライアント
        image_bytes: 画像バイナリデータ
        max_labels: 最大ラベル数

    Returns:
        list[dict]: 検出されたラベルのリスト
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
            "instances": len(label.get("Instances", [])),
        })

    return labels


def classify_damage(labels: list[dict]) -> dict:
    """検出ラベルから損害を分類する

    Args:
        labels: 検出されたラベルのリスト

    Returns:
        dict: 損害分類結果
    """
    damage_detected = [
        l for l in labels
        if l["name"] in DAMAGE_LABELS and l["confidence"] >= 50.0
    ]
    components_detected = [
        l for l in labels
        if l["name"] in VEHICLE_COMPONENT_LABELS and l["confidence"] >= 60.0
    ]

    has_damage = len(damage_detected) > 0

    if not has_damage:
        return {
            "damage_detected": False,
            "damage_labels": [],
            "affected_components": [],
            "reason_code": "NO_DAMAGE_LABELS_DETECTED",
        }

    return {
        "damage_detected": True,
        "damage_labels": damage_detected,
        "affected_components": [c["name"].lower() for c in components_detected],
        "reason_code": None,
    }


def _assess_with_bedrock(
    bedrock_client, labels: list[dict], model_id: str
) -> dict:
    """Bedrock で構造化損害評価を生成する"""
    labels_text = json.dumps(labels[:20], ensure_ascii=False)
    prompt = f"""以下の画像認識結果から、車両損害の構造化評価を生成してください。

## 検出ラベル:
{labels_text}

## 出力 JSON フォーマット:
{{
    "damage_type": "collision|scratch|dent|crack|other",
    "severity_level": "minor|moderate|severe|total_loss",
    "affected_components": ["部品名1", "部品名2"],
    "description": "損害の説明（50文字以内）"
}}

JSON のみを出力してください。"""

    try:
        response = bedrock_client.invoke_model(
            modelId=model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "inputText": prompt,
                "textGenerationConfig": {
                    "maxTokenCount": 512,
                    "temperature": 0.1,
                },
            }),
        )
        response_json = json.loads(response["body"].read())
        if "results" in response_json:
            output_text = response_json["results"][0].get("outputText", "")
        elif "content" in response_json:
            output_text = response_json["content"][0].get("text", "")
        else:
            output_text = ""

        if "```json" in output_text:
            json_str = output_text.split("```json")[1].split("```")[0].strip()
        elif "```" in output_text:
            json_str = output_text.split("```")[1].split("```")[0].strip()
        else:
            json_str = output_text.strip()

        return json.loads(json_str)
    except Exception as e:
        logger.warning("Bedrock assessment failed: %s", e)
        return {
            "damage_type": "other",
            "severity_level": "unknown",
            "affected_components": [],
            "description": "自動評価に失敗しました",
        }


@lambda_error_handler
def handler(event, context):
    """事故写真の損害評価（Rekognition + Bedrock）

    Input:
        {"Key": "claims/CLM20260115_001/photo_front.jpg", "Size": 4194304, ...}

    Output:
        {
            "status": "SUCCESS" | "MANUAL_REVIEW",
            "file_key": "...",
            "damage_assessment": {...},
            "output_key": "..."
        }
    """
    file_key = event["Key"]
    file_size = event.get("Size", 0)

    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    output_bucket = os.environ["OUTPUT_BUCKET"]
    model_id = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")

    logger.info(
        "Damage assessment started: file_key=%s, size=%d",
        file_key,
        file_size,
    )

    # 画像取得
    response = s3ap.get_object(file_key)
    image_bytes = response["Body"].read()

    # Rekognition で損害検出
    rekognition_client = boto3.client("rekognition")
    labels = detect_damage_labels(rekognition_client, image_bytes)

    # 損害分類
    damage_classification = classify_damage(labels)

    if not damage_classification["damage_detected"]:
        # 損害ラベル未検出 → 手動レビュー
        status = "MANUAL_REVIEW"
        damage_assessment = {
            "damage_type": "unknown",
            "severity_level": "unknown",
            "affected_components": [],
            "rekognition_labels": labels[:10],
            "reason_code": damage_classification["reason_code"],
        }
    else:
        # Bedrock で構造化評価
        bedrock_client = boto3.client("bedrock-runtime")
        bedrock_assessment = _assess_with_bedrock(bedrock_client, labels, model_id)

        status = "SUCCESS"
        damage_assessment = {
            "damage_type": bedrock_assessment.get("damage_type", "other"),
            "severity_level": bedrock_assessment.get("severity_level", "unknown"),
            "affected_components": bedrock_assessment.get("affected_components", []),
            "rekognition_labels": labels[:10],
            "description": bedrock_assessment.get("description", ""),
        }

    # 出力キー生成
    now = datetime.now(timezone.utc)
    file_stem = PurePosixPath(file_key).stem
    output_key = f"assessments/{now.strftime('%Y/%m/%d')}/{file_stem}_assessment.json"

    # 結果を S3 出力バケットに書き込み
    result = {
        "status": status,
        "file_key": file_key,
        "damage_assessment": damage_assessment,
        "output_key": output_key,
        "assessed_at": now.isoformat(),
    }

    s3_client = boto3.client("s3")
    s3_client.put_object(
        Bucket=output_bucket,
        Key=output_key,
        Body=json.dumps(result, default=str, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json; charset=utf-8",
    )

    logger.info(
        "Damage assessment completed: file_key=%s, status=%s, type=%s",
        file_key,
        status,
        damage_assessment.get("damage_type", "unknown"),
    )

    return result
