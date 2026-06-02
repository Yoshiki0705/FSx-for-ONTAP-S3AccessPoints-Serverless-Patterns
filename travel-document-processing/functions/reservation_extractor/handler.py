"""旅行・ホスピタリティ業界 (UC20) Reservation Extractor Lambda ハンドラ

予約文書（PDF、スキャン画像）から構造化データを抽出する。

処理フロー:
    1. S3 AP からドキュメント取得
    2. Comprehend で言語検出
    3. Textract でテキスト抽出（言語ヒント付き）
    4. Comprehend + 正規表現で構造化データ抽出
       - ゲスト名、日付、部屋タイプ、金額

多言語対応 (Requirement 4.5):
    検出された言語に応じて Textract 言語ヒントと Comprehend モデルを選択。

エラーハンドリング (Requirement 4.6):
    抽出失敗時はエラーを記録し、残りのドキュメント処理を継続。

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用)
    CROSS_REGION_TEXTRACT_REGION: Textract リージョン (default: "us-east-1")
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import xray_subsegment, EmfMetrics, trace_lambda_handler
from shared.retry_handler import retry_with_backoff, RetryConfig
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)

# Textract 言語ヒントマッピング
LANGUAGE_HINTS: dict[str, list[str]] = {
    "ja": ["JAPANESE"],
    "en": ["ENGLISH"],
    "ko": ["KOREAN"],
    "zh": ["CHINESE_SIMPLIFIED"],
    "zh-TW": ["CHINESE_TRADITIONAL"],
    "fr": ["FRENCH"],
    "de": ["GERMAN"],
    "es": ["SPANISH"],
    "it": ["ITALIAN"],
    "pt": ["PORTUGUESE"],
}

# Comprehend 対応言語コード
COMPREHEND_SUPPORTED_LANGUAGES: frozenset[str] = frozenset(
    {"en", "es", "fr", "de", "it", "pt", "ar", "hi", "ja", "ko", "zh", "zh-TW"}
)

# 日付パターン（複数フォーマット対応）
DATE_PATTERNS: list[re.Pattern] = [
    re.compile(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}"),  # 2026-01-15, 2026/01/15
    re.compile(r"\d{1,2}[-/]\d{1,2}[-/]\d{4}"),  # 01-15-2026, 15/01/2026
    re.compile(r"\d{4}年\d{1,2}月\d{1,2}日"),     # 2026年1月15日
]

# 金額パターン
AMOUNT_PATTERNS: list[re.Pattern] = [
    re.compile(r"[¥￥]\s*[\d,]+"),               # ¥50,000
    re.compile(r"\$\s*[\d,]+\.?\d*"),            # $500.00
    re.compile(r"€\s*[\d,]+\.?\d*"),             # €450.00
    re.compile(r"[\d,]+\s*(?:円|yen|USD|EUR)"),  # 50,000円
]

# 部屋タイプキーワード
ROOM_TYPE_KEYWORDS: list[str] = [
    "single", "double", "twin", "suite", "deluxe", "standard", "superior",
    "premium", "executive", "family", "connecting",
    "シングル", "ダブル", "ツイン", "スイート", "デラックス", "スタンダード",
    "スーペリア", "プレミアム", "エグゼクティブ", "ファミリー",
]


def detect_language(text: str, comprehend_client) -> str:
    """Comprehend でテキストの主要言語を検出する。

    Args:
        text: 分析対象テキスト
        comprehend_client: Comprehend boto3 クライアント

    Returns:
        str: 言語コード (例: "ja", "en")
    """
    if not text or len(text.strip()) < 10:
        return "ja"  # デフォルト日本語

    # Comprehend は最低 20 文字推奨
    sample_text = text[:5000]  # 最大 5000 bytes

    try:
        response = comprehend_client.detect_dominant_language(Text=sample_text)
        languages = response.get("Languages", [])
        if languages:
            return languages[0].get("LanguageCode", "ja")
    except Exception as e:
        logger.warning("Language detection failed, defaulting to 'ja': %s", str(e))

    return "ja"


def get_textract_hints(language_code: str) -> list[str] | None:
    """言語コードに対応する Textract 言語ヒントを返す。

    Args:
        language_code: ISO 言語コード

    Returns:
        list[str] | None: Textract 言語ヒントリスト、または None
    """
    return LANGUAGE_HINTS.get(language_code)


def extract_text_with_textract(
    document_bytes: bytes,
    textract_client,
    language_code: str = "ja",
) -> str:
    """Textract でドキュメントからテキストを抽出する。

    Args:
        document_bytes: ドキュメントバイナリ
        textract_client: Textract boto3 クライアント
        language_code: 言語コード

    Returns:
        str: 抽出されたテキスト
    """
    params: dict = {
        "Document": {"Bytes": document_bytes},
        "FeatureTypes": ["FORMS", "TABLES"],
    }

    hints = get_textract_hints(language_code)
    if hints:
        params["QueriesConfig"] = {"Queries": []}  # Textract AnalyzeDocument の場合
        # DetectDocumentText では言語ヒントは不要だが、AnalyzeDocument で使用

    @retry_with_backoff(config=RetryConfig(max_attempts=3))
    def _call_textract():
        return textract_client.analyze_document(**params)

    response = _call_textract()

    # テキストブロックを結合
    lines: list[str] = []
    for block in response.get("Blocks", []):
        if block.get("BlockType") == "LINE":
            text = block.get("Text", "")
            if text:
                lines.append(text)

    return "\n".join(lines)


def extract_structured_data(text: str, language_code: str) -> dict:
    """テキストから構造化データを抽出する。

    抽出対象:
        - guest_name: ゲスト名
        - check_in_date: チェックイン日
        - check_out_date: チェックアウト日
        - room_type: 部屋タイプ
        - amount: 金額

    Args:
        text: 抽出対象テキスト
        language_code: 言語コード

    Returns:
        dict: 抽出された構造化データ
    """
    result: dict = {
        "guest_name": None,
        "check_in_date": None,
        "check_out_date": None,
        "room_type": None,
        "amount": None,
        "language_detected": language_code,
    }

    if not text:
        return result

    # 日付抽出
    dates_found: list[str] = []
    for pattern in DATE_PATTERNS:
        dates_found.extend(pattern.findall(text))

    if len(dates_found) >= 2:
        result["check_in_date"] = dates_found[0]
        result["check_out_date"] = dates_found[1]
    elif len(dates_found) == 1:
        result["check_in_date"] = dates_found[0]

    # 金額抽出
    for pattern in AMOUNT_PATTERNS:
        match = pattern.search(text)
        if match:
            result["amount"] = match.group(0).strip()
            break

    # 部屋タイプ抽出
    text_lower = text.lower()
    for keyword in ROOM_TYPE_KEYWORDS:
        if keyword.lower() in text_lower:
            result["room_type"] = keyword
            break

    # ゲスト名抽出（言語依存）
    result["guest_name"] = _extract_guest_name(text, language_code)

    return result


def _extract_guest_name(text: str, language_code: str) -> str | None:
    """テキストからゲスト名を抽出する。

    Args:
        text: 入力テキスト
        language_code: 言語コード

    Returns:
        str | None: ゲスト名
    """
    # 日本語パターン
    if language_code == "ja":
        patterns = [
            re.compile(r"(?:お名前|氏名|宿泊者|ゲスト)[：:]\s*(.+?)(?:\n|$)"),
            re.compile(r"(?:Mr\.|Mrs\.|Ms\.)\s+([A-Za-z\s]+)"),
        ]
    else:
        patterns = [
            re.compile(r"(?:Guest|Name|Customer)[：:]\s*(.+?)(?:\n|$)", re.IGNORECASE),
            re.compile(r"(?:Mr\.|Mrs\.|Ms\.)\s+([A-Za-z\s]+)"),
        ]

    for pattern in patterns:
        match = pattern.search(text)
        if match:
            name = match.group(1).strip()
            if name and len(name) >= 2:
                return name

    return None


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """Travel Reservation Extractor Lambda

    予約文書から構造化データを抽出する。

    Input event:
        - Key: S3 オブジェクトキー
        - Size: ファイルサイズ
        - category: "reservation_doc"

    Returns:
        dict: status, key, extracted_data, errors
    """
    key = event.get("Key", "")
    category = event.get("category", "reservation_doc")

    logger.info("Processing reservation document: key=%s", key)

    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    s3ap_output = S3ApHelper(
        os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ["S3_ACCESS_POINT"])
    )
    textract_region = os.environ.get("CROSS_REGION_TEXTRACT_REGION", "us-east-1")

    # Textract クライアント (Cross-Region)
    textract_client = boto3.client("textract", region_name=textract_region)
    comprehend_client = boto3.client("comprehend")

    errors: list[dict] = []

    try:
        # Step 1: ドキュメント取得
        with xray_subsegment(
            name="s3ap_get_document",
            annotations={
                "service_name": "s3",
                "operation": "GetObject",
                "use_case": "travel-document-processing",
            },
        ):
            doc_bytes = s3ap.get_object_bytes(key=key)

        # Step 2: Textract でテキスト抽出（初回 — 言語検出用）
        with xray_subsegment(
            name="textract_extract_text",
            annotations={
                "service_name": "textract",
                "operation": "AnalyzeDocument",
                "use_case": "travel-document-processing",
            },
        ):
            extracted_text = extract_text_with_textract(
                doc_bytes, textract_client, language_code="ja"
            )

        # Step 3: 言語検出
        with xray_subsegment(
            name="comprehend_detect_language",
            annotations={
                "service_name": "comprehend",
                "operation": "DetectDominantLanguage",
                "use_case": "travel-document-processing",
            },
        ):
            language_code = detect_language(extracted_text, comprehend_client)

        # 非日本語の場合は言語ヒント付きで再抽出 (Requirement 4.5)
        if language_code != "ja":
            logger.info(
                "Non-Japanese document detected (lang=%s). "
                "Re-extracting with language hints.",
                language_code,
            )
            with xray_subsegment(
                name="textract_reextract_multilingual",
                annotations={
                    "service_name": "textract",
                    "operation": "AnalyzeDocument",
                    "language": language_code,
                },
            ):
                extracted_text = extract_text_with_textract(
                    doc_bytes, textract_client, language_code=language_code
                )

        # Step 4: 構造化データ抽出
        structured_data = extract_structured_data(extracted_text, language_code)

        logger.info(
            "Reservation extraction completed: key=%s, language=%s, "
            "guest_name=%s, room_type=%s",
            key,
            language_code,
            structured_data.get("guest_name"),
            structured_data.get("room_type"),
        )

        # 結果を S3 に出力
        result_key = f"results/reservations/{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/{os.path.basename(key)}.json"
        s3ap_output.put_object(
            key=result_key,
            body=json.dumps({
                "source_key": key,
                "category": category,
                "extracted_data": structured_data,
                "extracted_text_length": len(extracted_text),
                "processed_at": datetime.now(timezone.utc).isoformat(),
            }, ensure_ascii=False, default=str),
            content_type="application/json",
        )

        # EMF メトリクス
        metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="processing")
        metrics.set_dimension("UseCase", "travel-document-processing")
        metrics.set_dimension("Stage", "reservation-extractor")
        metrics.put_metric("SuccessCount", 1.0, "Count")
        metrics.flush()

        return {
            "status": "success",
            "key": key,
            "category": category,
            "result_key": result_key,
            "extracted_data": structured_data,
            "errors": [],
        }

    except Exception as e:
        # Requirement 4.6: 抽出失敗時はエラーを記録し継続
        error_detail = {
            "path": key,
            "category": category,
            "error_type": type(e).__name__,
            "details": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        errors.append(error_detail)

        logger.error(
            "Reservation extraction failed: key=%s, error=%s",
            key,
            str(e),
        )

        # エラーを出力バケットに記録
        error_key = f"errors/reservations/{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/{os.path.basename(key)}.json"
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
        metrics.set_dimension("Stage", "reservation-extractor")
        metrics.put_metric("ErrorCount", 1.0, "Count")
        metrics.flush()

        return {
            "status": "error",
            "key": key,
            "category": category,
            "errors": errors,
        }
