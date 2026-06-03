"""農業・食品業界 (UC21) Traceability Extractor Lambda ハンドラ

トレーサビリティ文書（収穫記録、出荷マニフェスト、検査証明書）から
ロット情報を抽出し、Comprehend でロット別に分類する。

機能:
    - Textract による構造化データ抽出 (ロットID, 日付, 産地, 責任者)
    - Comprehend によるロット別文書分類 (信頼度 0.80 以上)
    - 信頼度 0.80 未満は "review-required" マーク

Confidence Threshold:
    - TraceabilityConfidenceThreshold (default: 0.80)

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用)
    TRACEABILITY_CONFIDENCE_THRESHOLD: 分類信頼度閾値 (default: 0.80)
    CROSS_REGION_TEXTRACT_REGION: Textract 実行リージョン (default: us-east-1)
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import trace_lambda_handler
from shared.retry_handler import retry_with_backoff, RetryConfig

logger = logging.getLogger(__name__)

DEFAULT_TRACEABILITY_THRESHOLD: float = 0.80

# 抽出対象フィールドキー
EXTRACTION_FIELDS: list[str] = [
    "lot_id",
    "date",
    "origin_location",
    "responsible_party",
]


def extract_document_data_with_textract(
    textract_client,
    s3_bucket: str,
    s3_key: str,
) -> dict:
    """Textract で文書からテキストと構造化データを抽出する。

    Args:
        textract_client: boto3 textract client (Cross-Region)
        s3_bucket: S3 バケット/AP エイリアス
        s3_key: オブジェクトキー

    Returns:
        dict: raw_text, key_value_pairs, tables
    """

    @retry_with_backoff(config=RetryConfig(max_attempts=3))
    def _analyze_document():
        return textract_client.analyze_document(
            Document={"S3Object": {"Bucket": s3_bucket, "Name": s3_key}},
            FeatureTypes=["FORMS", "TABLES"],
        )

    response = _analyze_document()
    blocks = response.get("Blocks", [])

    # テキストブロックの抽出
    raw_text_lines: list[str] = []
    key_value_pairs: dict[str, str] = {}
    word_map: dict[str, str] = {}

    for block in blocks:
        block_type = block.get("BlockType", "")
        if block_type == "LINE":
            raw_text_lines.append(block.get("Text", ""))
        elif block_type == "WORD":
            word_map[block.get("Id", "")] = block.get("Text", "")

    # KEY_VALUE_SET 処理
    key_blocks = [b for b in blocks if b.get("BlockType") == "KEY_VALUE_SET" and "KEY" in b.get("EntityTypes", [])]
    value_blocks_map: dict[str, dict] = {
        b["Id"]: b for b in blocks if b.get("BlockType") == "KEY_VALUE_SET" and "VALUE" in b.get("EntityTypes", [])
    }

    for key_block in key_blocks:
        key_text = _get_text_from_relationships(key_block, word_map, blocks)
        # Find VALUE relationship
        for rel in key_block.get("Relationships", []):
            if rel.get("Type") == "VALUE":
                for value_id in rel.get("Ids", []):
                    if value_id in value_blocks_map:
                        value_block = value_blocks_map[value_id]
                        value_text = _get_text_from_relationships(value_block, word_map, blocks)
                        if key_text and value_text:
                            key_value_pairs[key_text.strip()] = value_text.strip()

    return {
        "raw_text": "\n".join(raw_text_lines),
        "key_value_pairs": key_value_pairs,
        "line_count": len(raw_text_lines),
    }


def _get_text_from_relationships(block: dict, word_map: dict, all_blocks: list) -> str:
    """ブロックの関連テキストを取得する。"""
    texts: list[str] = []
    for rel in block.get("Relationships", []):
        if rel.get("Type") == "CHILD":
            for child_id in rel.get("Ids", []):
                if child_id in word_map:
                    texts.append(word_map[child_id])
    return " ".join(texts)


def extract_traceability_fields(
    raw_text: str,
    key_value_pairs: dict[str, str],
) -> dict:
    """抽出されたテキストからトレーサビリティフィールドを特定する。

    Args:
        raw_text: 文書の全文テキスト
        key_value_pairs: Textract の Key-Value ペア

    Returns:
        dict: lot_id, date, origin_location, responsible_party
    """
    fields: dict[str, str | None] = {
        "lot_id": None,
        "date": None,
        "origin_location": None,
        "responsible_party": None,
    }

    # Key-Value ペアからのマッチング (日本語/英語キーワード)
    lot_keywords = ["ロットID", "ロット番号", "Lot ID", "Lot No", "LOT", "生産ロット"]
    date_keywords = ["日付", "収穫日", "出荷日", "Date", "Harvest Date", "Ship Date"]
    origin_keywords = ["産地", "原産地", "生産地", "Origin", "Location", "Farm"]
    party_keywords = ["責任者", "生産者", "担当者", "Responsible", "Producer", "Manager"]

    for key, value in key_value_pairs.items():
        key_lower = key.lower()
        if any(kw.lower() in key_lower for kw in lot_keywords):
            fields["lot_id"] = value
        elif any(kw.lower() in key_lower for kw in date_keywords):
            fields["date"] = value
        elif any(kw.lower() in key_lower for kw in origin_keywords):
            fields["origin_location"] = value
        elif any(kw.lower() in key_lower for kw in party_keywords):
            fields["responsible_party"] = value

    return fields


def classify_document_by_lot(
    comprehend_client,
    text: str,
    confidence_threshold: float,
) -> dict:
    """Comprehend でドキュメントをロット別に分類する。

    Args:
        comprehend_client: boto3 comprehend client
        text: 分類対象テキスト
        confidence_threshold: 最低信頼度閾値

    Returns:
        dict: classification result with lot_category, confidence, status
    """

    @retry_with_backoff(config=RetryConfig(max_attempts=3))
    def _detect_entities():
        return comprehend_client.detect_entities(
            Text=text[:5000],  # Comprehend max 5000 bytes for sync
            LanguageCode="ja",
        )

    @retry_with_backoff(config=RetryConfig(max_attempts=3))
    def _detect_key_phrases():
        return comprehend_client.detect_key_phrases(
            Text=text[:5000],
            LanguageCode="ja",
        )

    entities_response = _detect_entities()
    entities = entities_response.get("Entities", [])

    key_phrases_response = _detect_key_phrases()
    key_phrases = key_phrases_response.get("KeyPhrases", [])

    # ロット関連エンティティの検出
    lot_entities = [
        e for e in entities
        if e.get("Type") in ("QUANTITY", "OTHER", "ORGANIZATION")
    ]

    # 全体の信頼度スコアを計算
    if lot_entities:
        avg_confidence = sum(e.get("Score", 0) for e in lot_entities) / len(lot_entities)
    elif entities:
        avg_confidence = sum(e.get("Score", 0) for e in entities) / len(entities)
    else:
        avg_confidence = 0.0

    if avg_confidence >= confidence_threshold:
        status = "classified"
    else:
        status = "review-required"

    return {
        "classification_confidence": round(avg_confidence, 4),
        "status": status,
        "entities_count": len(entities),
        "key_phrases_count": len(key_phrases),
        "reason": None if status == "classified" else (
            f"Classification confidence {avg_confidence:.2f} below threshold {confidence_threshold}"
        ),
    }


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """Agri-Food Traceability Extractor Lambda

    トレーサビリティ文書からロット情報を抽出し分類する。

    Input event (single document from Map state):
        - Key: S3 オブジェクトキー
        - Size: ファイルサイズ
        - category: "traceability_doc"

    Returns:
        dict: status, key, extracted_fields, classification
    """
    start_time = time.time()

    s3_access_point = os.environ["S3_ACCESS_POINT"]
    cross_region = os.environ.get("CROSS_REGION_TEXTRACT_REGION", "us-east-1")
    confidence_threshold = float(
        os.environ.get("TRACEABILITY_CONFIDENCE_THRESHOLD", str(DEFAULT_TRACEABILITY_THRESHOLD))
    )

    object_key = event.get("Key", "")
    object_size = event.get("Size", 0)

    logger.info(
        "Traceability extraction started: key=%s, size=%d, threshold=%.2f",
        object_key,
        object_size,
        confidence_threshold,
    )

    try:
        # Cross-Region Textract クライアント
        textract_client = boto3.client("textract", region_name=cross_region)

        # Textract で文書解析
        document_data = extract_document_data_with_textract(
            textract_client, s3_access_point, object_key
        )

        # トレーサビリティフィールド抽出
        extracted_fields = extract_traceability_fields(
            document_data["raw_text"],
            document_data["key_value_pairs"],
        )

        # Comprehend によるロット分類
        comprehend_client = boto3.client("comprehend")
        classification = classify_document_by_lot(
            comprehend_client,
            document_data["raw_text"],
            confidence_threshold,
        )

        processing_duration_ms = int((time.time() - start_time) * 1000)

        result = {
            "status": "success",
            "key": object_key,
            "size": object_size,
            "extracted_fields": extracted_fields,
            "classification": classification,
            "document_stats": {
                "line_count": document_data["line_count"],
                "kv_pairs_count": len(document_data["key_value_pairs"]),
            },
            "confidence_threshold": confidence_threshold,
            "processing_duration_ms": processing_duration_ms,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            "Traceability extraction completed: key=%s, lot_id=%s, status=%s, confidence=%.2f",
            object_key,
            extracted_fields.get("lot_id"),
            classification["status"],
            classification["classification_confidence"],
        )

        return result

    except Exception as e:
        processing_duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "Traceability extraction failed: key=%s, error=%s",
            object_key,
            str(e),
        )
        return {
            "status": "error",
            "key": object_key,
            "size": object_size,
            "error": {
                "type": type(e).__name__,
                "message": str(e),
            },
            "classification": {
                "classification_confidence": 0.0,
                "status": "review-required",
                "reason": f"Extraction failed: {type(e).__name__}: {e}",
            },
            "processing_duration_ms": processing_duration_ms,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }
