"""HR (UC27) Resume Extractor Lambda ハンドラ

履歴書から構造化データを抽出する。

抽出対象 (Requirement 11.2):
    - スキル (skills)
    - 経験年数 (experience_years)
    - 学歴 (education)
    - 資格 (certifications)

PII 取り扱い (Requirement 11.5):
    - PII_MODE=strict: ログへの PII 出力禁止
    - 暗号化出力必須
    - アクセス監査証跡記録

AI/ML サービス:
    - Amazon Textract: 文書テキスト抽出
    - Amazon Comprehend: エンティティ認識

Note: Output bucket enforces SSE-KMS encryption via bucket default encryption policy
(configured in template.yaml OutputBucket resource)

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN
    PII_MODE: PII 保護モード (default: strict)
    TEXTRACT_REGION: Textract リージョン (default: us-east-1)
"""

from __future__ import annotations

import logging
import os
import re
import time

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler
from shared.pii_filter import PiiFilter, is_strict_mode
from shared.retry_handler import RetryConfig, categorize_error, retry_with_backoff

logger = logging.getLogger(__name__)

# スキル検出パターン
SKILL_PATTERNS: list[re.Pattern] = [
    re.compile(r"(?:スキル|技術|Skills?)[\s:：]*(.*)", re.IGNORECASE),
]

# 経験年数パターン
EXPERIENCE_PATTERNS: list[re.Pattern] = [
    re.compile(r"(?:経験|experience)[\s:：]*(\d+)\s*(?:年|years?)", re.IGNORECASE),
]

# 資格パターン
CERT_KEYWORDS: frozenset[str] = frozenset(
    {
        "aws",
        "azure",
        "gcp",
        "pmp",
        "cissp",
        "cpa",
        "toeic",
        "基本情報",
        "応用情報",
        "ネットワークスペシャリスト",
        "データベーススペシャリスト",
        "情報セキュリティ",
    }
)


def extract_text_textract(
    s3ap_alias: str,
    object_key: str,
    textract_client=None,
) -> str:
    """Textract で履歴書からテキストを抽出する。"""
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


def extract_entities_comprehend(
    text: str,
    comprehend_client=None,
) -> list[dict]:
    """Comprehend でエンティティを抽出する。"""
    if not text:
        return []

    if comprehend_client is None:
        comprehend_client = boto3.client("comprehend")

    truncated = text[:5000]

    @retry_with_backoff(config=RetryConfig(max_attempts=3))
    def _call_comprehend():
        return comprehend_client.detect_entities(
            Text=truncated,
            LanguageCode="ja",
        )

    response = _call_comprehend()
    return [
        {"text": e.get("Text", ""), "type": e.get("Type", ""), "score": e.get("Score", 0.0)}
        for e in response.get("Entities", [])
        if e.get("Score", 0.0) >= 0.7
    ]


def extract_candidate_data(text: str, entities: list[dict]) -> dict:
    """テキストとエンティティから候補者データを抽出する。

    Args:
        text: Textract 抽出テキスト
        entities: Comprehend エンティティ

    Returns:
        dict: skills, experience_years, education, certifications
    """
    result: dict = {
        "skills": [],
        "experience_years": None,
        "education": [],
        "certifications": [],
    }

    # スキル抽出
    for pattern in SKILL_PATTERNS:
        match = pattern.search(text)
        if match:
            skills_text = match.group(1)
            skills = [s.strip() for s in re.split(r"[,、/\s]+", skills_text) if s.strip()]
            result["skills"].extend(skills[:20])
            break

    # 経験年数
    for pattern in EXPERIENCE_PATTERNS:
        match = pattern.search(text)
        if match:
            result["experience_years"] = int(match.group(1))
            break

    # 学歴 (ORGANIZATION エンティティから)
    org_entities = [e for e in entities if e["type"] == "ORGANIZATION"]
    education_keywords = {"大学", "university", "college", "高校", "専門学校", "大学院"}
    for ent in org_entities:
        if any(kw in ent["text"].lower() for kw in education_keywords):
            result["education"].append(ent["text"])

    # 資格
    text_lower = text.lower()
    for cert in CERT_KEYWORDS:
        if cert in text_lower:
            result["certifications"].append(cert)

    return result


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """Resume Extractor Lambda

    Input event:
        - objects: 履歴書オブジェクトリスト

    Returns:
        dict: results, success_count, error_count
    """
    start_time = time.time()

    s3ap_alias = os.environ.get("S3_ACCESS_POINT", "")
    pii_filter = PiiFilter()

    # SECURITY: Output bucket enforces SSE-KMS via default encryption policy (template.yaml).
    # For defense-in-depth, consider adding explicit ServerSideEncryption to put_object calls
    # when S3ApHelper supports it. See: shared/s3ap_helper.py

    objects = event.get("objects", [])

    # PII strict モードではログにファイル名を含めない
    if is_strict_mode():
        logger.info("Resume extraction started: %d documents (strict PII mode)", len(objects))
    else:
        logger.info("Resume extraction started: %d documents", len(objects))

    results: list[dict] = []
    success_count = 0
    error_count = 0

    for obj in objects:
        key = obj.get("Key", "")
        position_type = obj.get("position_type", "general")

        try:
            text = extract_text_textract(s3ap_alias, key)
            entities = extract_entities_comprehend(text)
            candidate_data = extract_candidate_data(text, entities)

            # 保護特性の除去 (Requirement 11.6)
            candidate_data = pii_filter.remove_protected_characteristics(candidate_data)

            # 保護特性チェック
            protected_found = pii_filter.contains_protected_characteristics(text)
            compliance_note = None
            if protected_found:
                compliance_note = f"Protected characteristics detected and excluded: {', '.join(protected_found)}"

            results.append(
                {
                    "key": key,
                    "position_type": position_type,
                    "status": "success",
                    "candidate_data": candidate_data,
                    "compliance_note": compliance_note,
                }
            )
            success_count += 1

        except Exception as e:
            error_category = categorize_error(e)
            # strict モードではエラーログにファイルパスを含めない
            if is_strict_mode():
                logger.warning(
                    "Resume extraction failed: %s [%s]",
                    str(e),
                    error_category.value,
                )
            else:
                logger.warning(
                    "Resume extraction failed for %s: %s [%s]",
                    key,
                    str(e),
                    error_category.value,
                )
            results.append(
                {
                    "key": key,
                    "position_type": position_type,
                    "status": "error",
                    "error_type": error_category.value,
                    "error_message": str(e),
                }
            )
            error_count += 1

    processing_duration_ms = int((time.time() - start_time) * 1000)

    logger.info(
        "Resume extraction completed: success=%d, errors=%d",
        success_count,
        error_count,
    )

    # EMF メトリクス
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="processing")
    metrics.set_dimension("UseCase", "hr-document-screening")
    metrics.set_dimension("Stage", "resume-extraction")
    metrics.put_metric("ProcessingDuration", float(processing_duration_ms), "Milliseconds")
    metrics.put_metric("SuccessCount", float(success_count), "Count")
    metrics.put_metric("ErrorCount", float(error_count), "Count")
    metrics.flush()

    return {
        "results": results,
        "success_count": success_count,
        "error_count": error_count,
        "processing_duration_ms": processing_duration_ms,
        "audit_trail": pii_filter.get_audit_trail(),
    }
