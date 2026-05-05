"""物流 / サプライチェーン OCR Lambda ハンドラ

Cross_Region_Client で Amazon Textract に配送伝票ドキュメントを送信し、
テキスト・フォーム抽出（sender, recipient, tracking_number, item descriptions,
quantities）を実行する。低信頼度結果は手動検証フラグを設定する。

Textract は ap-northeast-1 非対応のため、CrossRegionClient を使用して
us-east-1 にルーティングする。

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    OUTPUT_BUCKET: S3 出力バケット名
    CROSS_REGION: クロスリージョンターゲット (デフォルト: us-east-1)
    CONFIDENCE_THRESHOLD: 信頼度閾値 (デフォルト: 80)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import PurePosixPath

import boto3

from shared.cross_region_client import CrossRegionClient, CrossRegionConfig
from shared.exceptions import lambda_error_handler
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)

DEFAULT_CROSS_REGION = "us-east-1"
DEFAULT_CONFIDENCE_THRESHOLD = 80.0


def _extract_text_from_blocks(blocks: list[dict]) -> str:
    """Textract レスポンスブロックからテキストを抽出する

    Args:
        blocks: Textract AnalyzeDocument レスポンスの Blocks

    Returns:
        str: 抽出されたテキスト
    """
    lines = []
    for block in blocks:
        if block.get("BlockType") == "LINE":
            text = block.get("Text", "")
            if text:
                lines.append(text)
    return "\n".join(lines)


def _extract_forms_from_blocks(blocks: list[dict]) -> list[dict]:
    """Textract レスポンスブロックからフォーム（Key-Value ペア）を抽出する

    Args:
        blocks: Textract AnalyzeDocument レスポンスの Blocks

    Returns:
        list[dict]: 抽出されたフォームフィールドのリスト
    """
    block_map = {block["Id"]: block for block in blocks if "Id" in block}
    forms = []

    for block in blocks:
        if block.get("BlockType") != "KEY_VALUE_SET":
            continue
        if "KEY" not in block.get("EntityTypes", []):
            continue

        # キーテキストを取得
        key_text = _get_text_from_relationships(block, block_map)

        # 対応する VALUE ブロックを取得
        value_text = ""
        for rel in block.get("Relationships", []):
            if rel.get("Type") == "VALUE":
                for value_id in rel.get("Ids", []):
                    value_block = block_map.get(value_id, {})
                    value_text = _get_text_from_relationships(
                        value_block, block_map
                    )

        confidence = block.get("Confidence", 0.0)
        if key_text:
            forms.append({
                "key": key_text,
                "value": value_text,
                "confidence": round(confidence, 2),
            })

    return forms


def _get_text_from_relationships(block: dict, block_map: dict) -> str:
    """ブロックの Relationships から CHILD テキストを結合する

    Args:
        block: Textract ブロック
        block_map: ID → ブロックのマッピング

    Returns:
        str: 結合されたテキスト
    """
    words = []
    for rel in block.get("Relationships", []):
        if rel.get("Type") == "CHILD":
            for child_id in rel.get("Ids", []):
                child_block = block_map.get(child_id, {})
                if child_block.get("BlockType") == "WORD":
                    words.append(child_block.get("Text", ""))
    return " ".join(words)


def _evaluate_confidence(forms: list[dict], threshold: float) -> tuple[bool, list[dict]]:
    """フォームフィールドの信頼度を評価する

    Args:
        forms: 抽出されたフォームフィールドのリスト
        threshold: 信頼度閾値

    Returns:
        tuple: (all_above_threshold, low_confidence_fields)
    """
    low_confidence_fields = [
        f for f in forms if f.get("confidence", 0.0) < threshold
    ]
    all_above = len(low_confidence_fields) == 0
    return all_above, low_confidence_fields


@lambda_error_handler
def handler(event, context):
    """配送伝票 OCR（Cross-Region Textract）

    Input:
        {"Key": "slips/delivery_20260115.pdf", "Size": 2097152, ...}

    Output:
        {
            "status": "SUCCESS" | "MANUAL_VERIFICATION",
            "file_key": "...",
            "extracted_text": "...",
            "forms": [...],
            "low_confidence_fields": [...],
            "output_key": "..."
        }
    """
    file_key = event["Key"]
    file_size = event.get("Size", 0)

    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    output_bucket = os.environ["OUTPUT_BUCKET"]
    cross_region = os.environ.get("CROSS_REGION", DEFAULT_CROSS_REGION)
    confidence_threshold = float(
        os.environ.get("CONFIDENCE_THRESHOLD", str(DEFAULT_CONFIDENCE_THRESHOLD))
    )

    logger.info(
        "Logistics OCR started: file_key=%s, size=%d, cross_region=%s",
        file_key,
        file_size,
        cross_region,
    )

    # ドキュメント取得
    try:
        response = s3ap.get_object(file_key)
        body = response["Body"]
        document_bytes = body.read()
        body.close()
    except Exception as e:
        logger.error("Failed to read document %s: %s", file_key, e)
        return {
            "status": "ERROR",
            "file_key": file_key,
            "error": f"Failed to read file: {e}",
            "extracted_text": "",
            "forms": [],
        }

    # Cross-Region Textract で OCR 実行
    cross_region_config = CrossRegionConfig(
        target_region=cross_region,
        services=["textract"],
    )
    cross_region_client = CrossRegionClient(cross_region_config)

    try:
        textract_response = cross_region_client.analyze_document(
            document_bytes=document_bytes,
            feature_types=["FORMS"],
        )
    except Exception as e:
        logger.error("Textract AnalyzeDocument failed for %s: %s", file_key, e)
        return {
            "status": "ERROR",
            "file_key": file_key,
            "error": f"Textract failed: {e}",
            "extracted_text": "",
            "forms": [],
        }

    # テキストとフォームの抽出
    blocks = textract_response.get("Blocks", [])
    extracted_text = _extract_text_from_blocks(blocks)
    forms = _extract_forms_from_blocks(blocks)

    # 信頼度評価
    all_above, low_confidence_fields = _evaluate_confidence(
        forms, confidence_threshold
    )
    status = "SUCCESS" if all_above else "MANUAL_VERIFICATION"

    # 出力キー生成
    now = datetime.now(timezone.utc)
    file_stem = PurePosixPath(file_key).stem
    output_key = f"ocr/{now.strftime('%Y/%m/%d')}/{file_stem}_ocr.json"

    # 結果を S3 出力バケットに書き込み
    result = {
        "status": status,
        "file_key": file_key,
        "extracted_text": extracted_text,
        "forms": forms,
        "low_confidence_fields": low_confidence_fields,
        "output_key": output_key,
        "extracted_at": now.isoformat(),
    }

    s3_client = boto3.client("s3")
    s3_client.put_object(
        Bucket=output_bucket,
        Key=output_key,
        Body=json.dumps(result, default=str, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json; charset=utf-8",
    )

    logger.info(
        "Logistics OCR completed: file_key=%s, status=%s, forms=%d, low_confidence=%d",
        file_key,
        status,
        len(forms),
        len(low_confidence_fields),
    )

    return result
