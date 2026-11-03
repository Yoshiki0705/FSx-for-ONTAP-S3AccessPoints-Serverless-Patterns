"""OCR (sync) Lambda — 日本語文書 OCR × AgentCore Gateway パターン。

S3 Access Point 上の画像（PNG / JPEG）を bytes で取得し、Textract の同期 API に渡す。
FSx for ONTAP の S3 Access Point は Textract の `S3Object` 参照で読めないため、必ず
bytes を inline で渡す（`S3ApHelper.get_object_bytes`）。

プロファイルで API を切り替える:
- `text`: `DetectDocumentText`（費用が低い。日本語に対応）
- `structure`: `AnalyzeDocument(TABLES, LAYOUT)`（日本語に対応。Forms は日本語に非対応のため使わない）

再試行で直る失敗（スロットリング、一時的な失敗）は `TextractThrottled` / `TextractTransient` を
raise して Step Functions の Retry に任せる。文書が悪い（形式不正など）場合は再試行しても
変わらないので、例外にせず失敗レコードを返し、他の文書の処理を止めない。

Environment Variables:
    S3_ACCESS_POINT_ALIAS: S3 Access Point Alias（DemoMode では通常バケット名）
    OUTPUT_BUCKET / OUTPUT_DESTINATION: 結果の書き込み先（shared.output_writer が読む）
    REVIEW_AUTO_APPROVE / REVIEW_REJECT / LOW_CONFIDENCE_LINE / LOW_CONFIDENCE_CHAR_RATIO /
    HANDWRITING_WORD_RATIO: Human Review の閾値（既定は shared.textract_helper の値）
"""

from __future__ import annotations

import logging
import os
from typing import Any

from shared.exceptions import S3ApHelperError, TextractRejected, lambda_error_handler
from shared.observability import EmfMetrics
from shared.output_writer import OutputWriter
from shared.s3ap_helper import S3ApHelper
from shared.textract_helper import (
    FEATURE_PROFILES,
    BlockAccumulator,
    build_client,
    classify_client_error,
    failure_record,
    finalize_document,
    is_permanent_s3_error,
    review_settings_from_env,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_textract = build_client()


@lambda_error_handler
def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """OCR (sync) Lambda ハンドラー。

    Args:
        event: Map の項目。`doc`（`key`、`size`、`doc_id` など）、`profile`、`output_prefix`、
            `classification`、`collection` を持つ。
        context: Lambda コンテキスト。

    Returns:
        完了なら `status: completed`、ページ数、平均信頼度、Human Review 判定、結果の S3 URI。
        文書が不正なら `status: failed` とエラー型。

    Raises:
        TextractThrottled: スロットリング（Step Functions が再試行する）。
        TextractTransient: 一時的な失敗（Step Functions が再試行する）。
    """
    doc = event["doc"]
    profile = event["profile"]
    key = doc["key"]
    features = FEATURE_PROFILES[profile]
    api = "AnalyzeDocument" if features else "DetectDocumentText"
    logger.info("OCR sync: doc_id=%s profile=%s api=%s size=%s", doc["doc_id"], profile, api, doc.get("size"))

    try:
        data = S3ApHelper(os.environ["S3_ACCESS_POINT_ALIAS"]).get_object_bytes(key)
    except S3ApHelperError as e:
        if not is_permanent_s3_error(e):
            raise  # SlowDown など。Step Functions の Retry に任せる
        # 権限なし・キーなし・サイズ超過は再試行しても同じ。他の文書は続行する。
        logger.warning("Cannot read %s: %s", doc["doc_id"], e)
        return failure_record(e)

    try:
        if features:
            response = _textract.analyze_document(Document={"Bytes": data}, FeatureTypes=features)
        else:
            response = _textract.detect_document_text(Document={"Bytes": data})
    except Exception as e:  # noqa: BLE001 — 分類してから再送出または記録する
        error = classify_client_error(e)
        if isinstance(error, TextractRejected):
            logger.warning("Textract rejected %s: %s", doc["doc_id"], error)
            return failure_record(error)
        raise error from e

    line_threshold, thresholds = review_settings_from_env()
    accumulator = BlockAccumulator(low_confidence_threshold=line_threshold)
    accumulator.declare_pages(response.get("DocumentMetadata", {}).get("Pages", 1))
    accumulator.add(response.get("Blocks", []))
    record = finalize_document(
        accumulator=accumulator,
        writer=OutputWriter.from_env(),
        key_prefix=f"{event['output_prefix']}/{doc['doc_id']}",
        source={
            "key": key,
            "size": doc.get("size"),
            "last_modified": doc.get("last_modified"),
            "etag": doc.get("etag"),
            "collection": event.get("collection"),
        },
        textract_meta={
            "api": api,
            "mode": "sync",
            "profile": profile,
            "features": features,
            "region": _textract.meta.region_name,
            "model_version": response.get("AnalyzeDocumentModelVersion")
            or response.get("DetectDocumentTextModelVersion"),
        },
        classification=event.get("classification", "INTERNAL"),
        thresholds=thresholds,
    )

    metrics = EmfMetrics(service="japanese-document-ocr-agent")
    metrics.set_dimension("Collection", str(event.get("collection", "unknown")))
    metrics.put_metric("PagesProcessed", record["pages"], "Count")
    metrics.put_metric("DocumentsProcessed", 1, "Count")
    if record["human_review"]["requires_review"]:
        metrics.put_metric("HumanReviewRequired", 1, "Count")
    metrics.flush()
    return record
