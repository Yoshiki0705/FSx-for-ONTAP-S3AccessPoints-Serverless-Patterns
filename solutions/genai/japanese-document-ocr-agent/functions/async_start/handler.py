"""OCR (async start) Lambda — 日本語文書 OCR × AgentCore Gateway パターン。

PDF / TIFF / 大きい画像を Textract の非同期 API に渡す入口。

非同期 API (`StartDocumentTextDetection` / `StartDocumentAnalysis`) は `DocumentLocation` に
S3 バケット上のオブジェクトしか受け付けず、FSx for ONTAP の S3 Access Point は `S3Object` 参照で
読めない（`docs/agent/pitfalls-s3ap-ontap.md`）。そのため、文書を S3 Access Point から
同一リージョンのステージングバケットへストリーミングコピーし、そのキーを渡す。
コピーは終端（成功・失敗・タイムアウト）で `async_collect` が削除する。ライフサイクルは保険。

`ClientRequestToken` は実行名・文書 ID・プロファイルから決定的に作る。Step Functions が
このタスクを再試行しても、Textract は同じジョブとして扱い、二重に課金しない。

Environment Variables:
    S3_ACCESS_POINT_ALIAS: 読み取り元（S3 Access Point Alias。DemoMode では通常バケット名）
    STAGING_BUCKET: ステージングバケット名
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from shared.exceptions import S3ApHelperError, TextractRejected, lambda_error_handler
from shared.observability import EmfMetrics
from shared.textract_helper import (
    FEATURE_PROFILES,
    build_client,
    classify_client_error,
    client_request_token,
    delete_staged_copy,
    failure_record,
    is_permanent_s3_error,
    stage_document,
    staged_key_for,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_textract = build_client()


@lambda_error_handler
def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """OCR (async start) Lambda ハンドラー。

    Args:
        event: Map の項目。`doc`、`profile`、`execution_name`、`poll_seconds` を持つ。
        context: Lambda コンテキスト。

    Returns:
        成功なら `status: started` とジョブ情報（`job_id`、`api`、`staged_key`、`started_at`、
        `wait_seconds`、`poll_index`）。文書が不正なら `status: failed` とエラー型。

    Raises:
        TextractThrottled: スロットリング（Step Functions が再試行する）。
        TextractTransient: 一時的な失敗（Step Functions が再試行する）。
    """
    doc = event["doc"]
    profile = event["profile"]
    features = FEATURE_PROFILES[profile]
    staging_bucket = os.environ["STAGING_BUCKET"]
    execution_name = event["execution_name"]
    staged_key = staged_key_for(execution_name, doc["doc_id"], doc["key"])
    api = "StartDocumentAnalysis" if features else "StartDocumentTextDetection"
    logger.info("OCR async start: doc_id=%s profile=%s api=%s size=%s", doc["doc_id"], profile, api, doc.get("size"))

    try:
        stage_document(os.environ["S3_ACCESS_POINT_ALIAS"], doc["key"], staging_bucket, staged_key, doc.get("size"))
    except S3ApHelperError as e:
        if not is_permanent_s3_error(e):
            raise
        logger.warning("Cannot read %s: %s", doc["doc_id"], e)
        return failure_record(e)

    request: dict[str, Any] = {
        "DocumentLocation": {"S3Object": {"Bucket": staging_bucket, "Name": staged_key}},
        "ClientRequestToken": client_request_token(execution_name, doc["doc_id"], profile),
        "JobTag": doc["doc_id"],
    }
    try:
        if features:
            response = _textract.start_document_analysis(FeatureTypes=features, **request)
        else:
            response = _textract.start_document_text_detection(**request)
    except Exception as e:  # noqa: BLE001 — 分類してから再送出または記録する
        error = classify_client_error(e)
        if isinstance(error, TextractRejected):
            logger.warning("Textract rejected %s: %s", doc["doc_id"], error)
            delete_staged_copy(staging_bucket, staged_key)
            return failure_record(error)
        # 再試行する場合もコピーは残す。トークンが同じなので、次の試行は同じジョブとして扱われる。
        raise error from e

    metrics = EmfMetrics(service="japanese-document-ocr-agent")
    metrics.set_dimension("Collection", str(event.get("collection", "unknown")))
    metrics.put_metric("AsyncJobsStarted", 1, "Count")
    metrics.flush()
    return {
        "status": "started",
        "job_id": response["JobId"],
        "api": api,
        "staged_key": staged_key,
        "started_at": int(time.time()),
        "wait_seconds": int(event.get("poll_seconds", 5)),
        "poll_index": 0,
    }
