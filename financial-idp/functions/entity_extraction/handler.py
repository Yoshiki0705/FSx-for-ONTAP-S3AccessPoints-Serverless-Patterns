"""金融・保険 Entity Extraction Lambda ハンドラ

OCR Lambda から抽出テキストを受け取り、Amazon Comprehend で
Named Entity Recognition (NER) を実行する。

抽出対象エンティティ:
    - DATE: 日付
    - QUANTITY: 金額
    - ORGANIZATION: 組織名
    - PERSON: 人名
"""

from __future__ import annotations

import logging

import boto3

from shared.exceptions import lambda_error_handler

logger = logging.getLogger(__name__)

# 抽出対象のエンティティタイプ
TARGET_ENTITY_TYPES = {"DATE", "QUANTITY", "ORGANIZATION", "PERSON"}


@lambda_error_handler
def handler(event, context):
    """Entity Extraction Lambda: Comprehend で Named Entity 抽出

    OCR Lambda から以下の形式でデータを受け取る:
        {"document_key": str, "extracted_text": str, ...}

    Returns:
        dict: document_key, extracted_text, entities
    """
    document_key = event["document_key"]
    extracted_text = event.get("extracted_text", "")

    logger.info(
        "Entity extraction started: key=%s, text_length=%d",
        document_key,
        len(extracted_text),
    )

    # テキストが空の場合（OCR エラー等）はスキップ
    if not extracted_text.strip():
        logger.warning(
            "Empty text for document %s, skipping entity extraction",
            document_key,
        )
        return {
            "document_key": document_key,
            "extracted_text": extracted_text,
            "entities": {
                "dates": [],
                "amounts": [],
                "organizations": [],
                "persons": [],
            },
        }

    comprehend_client = boto3.client("comprehend")

    # Comprehend の入力テキスト上限は 100KB (UTF-8)
    # 超過する場合は先頭部分のみ処理
    max_bytes = 100_000
    text_for_comprehend = extracted_text
    if len(extracted_text.encode("utf-8")) > max_bytes:
        text_for_comprehend = extracted_text[:max_bytes]
        logger.warning(
            "Text truncated to %d bytes for Comprehend (original: %d bytes)",
            max_bytes,
            len(extracted_text.encode("utf-8")),
        )

    response = comprehend_client.detect_entities(
        Text=text_for_comprehend,
        LanguageCode="ja",
    )

    # エンティティをタイプ別に分類
    entities = {
        "dates": [],
        "amounts": [],
        "organizations": [],
        "persons": [],
    }

    for entity in response.get("Entities", []):
        entity_type = entity.get("Type", "")
        entity_data = {
            "text": entity.get("Text", ""),
            "score": entity.get("Score", 0.0),
            "begin_offset": entity.get("BeginOffset", 0),
            "end_offset": entity.get("EndOffset", 0),
        }

        if entity_type == "DATE":
            entities["dates"].append(entity_data)
        elif entity_type == "QUANTITY":
            entities["amounts"].append(entity_data)
        elif entity_type == "ORGANIZATION":
            entities["organizations"].append(entity_data)
        elif entity_type == "PERSON":
            entities["persons"].append(entity_data)

    logger.info(
        "Entity extraction completed: key=%s, dates=%d, amounts=%d, "
        "organizations=%d, persons=%d",
        document_key,
        len(entities["dates"]),
        len(entities["amounts"]),
        len(entities["organizations"]),
        len(entities["persons"]),
    )

    return {
        "document_key": document_key,
        "extracted_text": extracted_text,
        "entities": entities,
    }
