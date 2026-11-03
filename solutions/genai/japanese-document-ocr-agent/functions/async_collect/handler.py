"""OCR (async collect) Lambda — 日本語文書 OCR × AgentCore Gateway パターン。

非同期ジョブが終端状態になったあと、結果を取得して正規化し、結果バケットに書く。
成否にかかわらず、ステージング済みのコピーを削除する（成功・失敗・タイムアウト・確認の失敗）。

- `SUCCEEDED` / `PARTIAL_SUCCESS`: `Get*` を `NextToken` で辿って全ページを集める。
  `PARTIAL_SUCCESS`（一部のページが失敗）は Human Review に引き上げる
- `FAILED` / `TIMED_OUT` / 状態確認の失敗: 失敗レコードを返す（他の文書は止めない）

ページ送りには歯止めがある。Textract は必ず `NextToken` を返し終えるが、壊れた応答で
無限ループにならないようにする。

Environment Variables:
    STAGING_BUCKET: ステージングバケット名
    OUTPUT_BUCKET / OUTPUT_DESTINATION: 結果の書き込み先（shared.output_writer が読む）
"""

from __future__ import annotations

import logging
import os
from typing import Any

from shared.exceptions import TextractRejected, lambda_error_handler
from shared.observability import EmfMetrics
from shared.output_writer import OutputWriter
from shared.textract_helper import (
    FEATURE_PROFILES,
    MAX_RESULT_PAGES,
    BlockAccumulator,
    build_client,
    classify_client_error,
    delete_staged_copy,
    failure_record,
    finalize_document,
    review_settings_from_env,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_textract = build_client()

MAX_WARNINGS = 5


def _failed(error_type: str, message: str) -> dict[str, Any]:
    return {"status": "failed", "error": {"type": error_type, "message": message[:200]}}


def collect_blocks(job_id: str, features: list[str], accumulator: BlockAccumulator) -> dict[str, Any]:
    """`Get*` を `NextToken` で辿り、全ページの Block を `accumulator` に足す。

    Args:
        job_id: Textract のジョブ ID。
        features: 空なら `GetDocumentTextDetection`、あれば `GetDocumentAnalysis`。
        accumulator: Block を足す先。

    Returns:
        `model_version`、`warnings`（上限あり）、`response_pages`（呼び出し回数）。

    Raises:
        TextractThrottled: スロットリング（呼び出し側が再試行する）。
        TextractTransient: 一時的な失敗（呼び出し側が再試行する）。
        TextractRejected: ジョブ ID の不正、結果ページが多すぎる、応答がジョブの失敗を示す場合。
    """
    fetch = _textract.get_document_analysis if features else _textract.get_document_text_detection
    token: str | None = None
    calls = 0
    model_version: str | None = None
    warnings: list[dict[str, Any]] = []
    while True:
        kwargs: dict[str, Any] = {"JobId": job_id}
        if token:
            kwargs["NextToken"] = token
        try:
            response = fetch(**kwargs)
        except Exception as e:  # noqa: BLE001 — 分類してから再送出する
            raise classify_client_error(e) from e
        calls += 1
        if response.get("JobStatus") == "FAILED":
            raise TextractRejected(f"job reported FAILED while reading results: {response.get('StatusMessage', '')}")
        accumulator.declare_pages(response.get("DocumentMetadata", {}).get("Pages", 0))
        accumulator.add(response.get("Blocks", []))
        model_version = (
            model_version
            or response.get("AnalyzeDocumentModelVersion")
            or response.get("DetectDocumentTextModelVersion")
        )
        for warning in response.get("Warnings", []) or []:
            if len(warnings) < MAX_WARNINGS:
                warnings.append({"code": warning.get("ErrorCode"), "pages": (warning.get("Pages") or [])[:20]})
        token = response.get("NextToken")
        if not token:
            break
        if calls >= MAX_RESULT_PAGES:
            raise TextractRejected(f"job {job_id} returned more than {MAX_RESULT_PAGES} result pages")
    return {"model_version": model_version, "warnings": warnings, "response_pages": calls}


@lambda_error_handler
def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """OCR (async collect) Lambda ハンドラー。

    Args:
        event: Map の項目。`doc`、`profile`、`job`（`async_check` が更新したもの）、
            `output_prefix`、`classification`、`collection` を持つ。状態確認が失敗して
            Catch から来たときは `check_error`（`Error`、`Cause`）も持つ。
        context: Lambda コンテキスト。

    Returns:
        完了なら `status: completed`、ページ数、平均信頼度、Human Review 判定、結果の S3 URI。
        失敗なら `status: failed` とエラー型。

    Raises:
        TextractThrottled: 結果取得がスロットリングされた（Step Functions が再試行する）。
        TextractTransient: 一時的な失敗（Step Functions が再試行する）。
    """
    doc = event["doc"]
    job = event["job"]
    profile = event["profile"]
    features = FEATURE_PROFILES[profile]
    staging_bucket = os.environ["STAGING_BUCKET"]
    try:
        if event.get("check_error"):
            error = event["check_error"]
            logger.warning("Job %s: status check failed (%s)", job.get("job_id"), error.get("Error"))
            return _failed(str(error.get("Error", "CheckFailed")), "could not check the job status")

        status = job.get("status")
        if status in ("FAILED", "TIMED_OUT"):
            kind = "JobTimeout" if status == "TIMED_OUT" else "JobFailed"
            logger.warning("Job %s ended with %s", job["job_id"], status)
            return _failed(kind, job.get("status_message") or f"Textract job ended with {status}")

        line_threshold, thresholds = review_settings_from_env()
        accumulator = BlockAccumulator(low_confidence_threshold=line_threshold)
        try:
            summary = collect_blocks(job["job_id"], features, accumulator)
        except TextractRejected as e:
            logger.warning("Cannot collect %s: %s", doc["doc_id"], e)
            return failure_record(e)

        partial = status == "PARTIAL_SUCCESS"
        record = finalize_document(
            accumulator=accumulator,
            writer=OutputWriter.from_env(),
            key_prefix=f"{event['output_prefix']}/{doc['doc_id']}",
            source={
                "key": doc["key"],
                "size": doc.get("size"),
                "last_modified": doc.get("last_modified"),
                "etag": doc.get("etag"),
                "collection": event.get("collection"),
            },
            textract_meta={
                "api": job.get("api"),
                "mode": "async",
                "profile": profile,
                "features": features,
                "region": _textract.meta.region_name,
                "job_id": job["job_id"],
                "job_status": status,
                "polls": job.get("poll_index"),
                "elapsed_seconds": job.get("elapsed_seconds"),
                "model_version": summary["model_version"],
                "warnings": summary["warnings"],
            },
            classification=event.get("classification", "INTERNAL"),
            thresholds=thresholds,
            extra_reasons=["Textract reported PARTIAL_SUCCESS (some pages failed)"] if partial else (),
        )
        metrics = EmfMetrics(service="japanese-document-ocr-agent")
        metrics.set_dimension("Collection", str(event.get("collection", "unknown")))
        metrics.put_metric("PagesProcessed", record["pages"], "Count")
        metrics.put_metric("DocumentsProcessed", 1, "Count")
        if record["human_review"]["requires_review"]:
            metrics.put_metric("HumanReviewRequired", 1, "Count")
        metrics.flush()
        return record
    finally:
        # 結果の取得が再試行になっても、ジョブはもう文書を読み終えているので、コピーは不要。
        if job.get("staged_key"):
            delete_staged_copy(staging_bucket, job["staged_key"])
