"""Report Lambda — 日本語文書 OCR × AgentCore Gateway パターン。

Map の結果を集計し、`manifest.json`（全文書の完全な一覧）を結果バケットに書き、
エージェントが `DescribeExecution` で読む実行結果を返す。

実行結果は Step Functions の 256 KiB の内側に必ず収める。文書ごとの一覧は 1 件ずつ大きさを
見積もり、上限を超える分を切り詰めて `documents_truncated: true` を立てる（完全な一覧は
`manifest.json`）。OCR 本文は載せない。

失敗の見え方を二つに分ける:
- 一部の文書が失敗: 実行は成功で、`summary` に件数、`status: completed_with_errors`
- 全文書が失敗、または実行全体の失敗（入力不正、設定不正）: `status: failed` / `error` を返し、
  ステートマシンの Choice が Fail 状態へ送る。エージェントは `DescribeExecution` の
  `status: FAILED` と `error` / `cause` を読める

項目抽出（任意）の扱い:
- 状態遷移が運ぶのは件数（`requested` / `ungrounded_count`）だけ。値と根拠は `fields.json` にあり、
  ここで文書ごとに読み直す（Map の集計が 256 KiB を超えないようにするため）。
- 根拠のない項目が 1 つでもある、または抽出に失敗した文書は、OCR の判定が AUTO_APPROVE でも
  HUMAN_REVIEW に引き上げる。`result.json` は OCR だけの判定を持ち、項目を含めた最終の判定は
  `manifest.json` と実行結果の `action` にある。

Environment Variables:
    SNS_TOPIC_ARN: 通知先（任意）
    OUTPUT_BUCKET / OUTPUT_DESTINATION: manifest の書き込み先と fields.json の読み出し先
        （shared.output_writer が読む）
    AWS_REGION: 実行結果の `region` に載せる
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections import Counter
from typing import Any

import boto3
from botocore.exceptions import ClientError

from shared.exceptions import S3ApHelperError, lambda_error_handler
from shared.observability import EmfMetrics
from shared.output_writer import OutputWriter

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_sns = boto3.client("sns")

#: 実行結果の `documents` に載せるバイト数の上限。Step Functions の 256 KiB (262,144 B) の内側に、
#: 他の項目と余裕を残す。
MAX_DOCUMENTS_BYTES = 150_000
#: 通知しないエラー型。エージェントの入力ミスは日常的に起こるので、メールを送らない。
QUIET_ERRORS = frozenset({"InvalidInput"})
MAX_CAUSE_CHARS = 500
#: 実行結果に載せる項目の値の長さ。全文は `fields.json` にある。
FIELD_VALUE_VIEW_CHARS = 60
#: `review_reason` の長さ。
MAX_REVIEW_REASON_CHARS = 240


def clean_error_message(error: dict[str, Any]) -> tuple[str, str]:
    """Catch が持ってきた `Error` と `Cause` から、読める型とメッセージを取り出す。

    Lambda の失敗の `Cause` は、`errorMessage` とスタックトレースを含む JSON 文字列になる。
    エージェントに返すのは `errorMessage` だけにする。

    Args:
        error: `{"Error": ..., "Cause": ...}`。

    Returns:
        (エラー型, 500 文字までのメッセージ)。
    """
    error_type = str(error.get("Error") or "Error")
    cause = error.get("Cause")
    message = ""
    if isinstance(cause, str):
        try:
            parsed = json.loads(cause)
            if isinstance(parsed, dict):
                error_type = str(parsed.get("errorType") or error_type)
                message = str(parsed.get("errorMessage") or "")
        except ValueError:
            message = cause
    return error_type, (message or str(cause or error_type))[:MAX_CAUSE_CHARS]


def normalize_error(value: Any) -> dict[str, str]:
    """文書の失敗の `error` を `{type, message}` の形に揃える。

    Lambda が返す失敗記録は辞書（`{type, message}`）だが、ステートマシンの Catch が作る記録は
    エラー型の文字列になる。どちらが来ても集計が落ちないよう、ここで揃える。

    Args:
        value: 辞書、文字列、または None。

    Returns:
        `type` と `message` を持つ辞書。
    """
    if isinstance(value, dict):
        return {"type": str(value.get("type") or "unknown"), "message": str(value.get("message") or "")[:200]}
    if isinstance(value, str) and value:
        return {"type": value, "message": ""}
    return {"type": "unknown", "message": ""}


def _short(value: Any) -> str | None:
    """項目の値を、実行結果に載せる長さに切る。切ったときは末尾に `…` を付ける。"""
    if value in (None, ""):
        return None
    text = str(value)
    return text if len(text) <= FIELD_VALUE_VIEW_CHARS else text[:FIELD_VALUE_VIEW_CHARS] + "…"


def fields_view(fields: dict[str, Any], detail: dict[str, Any] | None) -> dict[str, Any] | None:
    """項目抽出の結果を、実行結果に載せる小さな形にする。

    状態遷移が運ぶのは件数だけ。`fields.json`（`detail`）を読めたときに限り、項目ごとの値
    （60 文字まで）と根拠なしの項目名を足す。根拠の引用は載せない（`fields.json` にある）。

    Args:
        fields: 状態遷移の `fields` 記録（`status`、`requested`、`ungrounded_count` など）。
        detail: `fields.json` の内容。読めなければ None。

    Returns:
        抽出を要求していないときは None。
    """
    status = fields.get("status")
    if status == "failed":
        return {"status": "failed", "error": str(fields.get("error") or "unknown")[:80]}
    if status != "completed":
        return None
    view: dict[str, Any] = {"status": "completed", "ungrounded_count": int(fields.get("ungrounded_count") or 0)}
    stored = (detail or {}).get("fields")
    if isinstance(stored, dict):
        entries = {name: entry for name, entry in stored.items() if isinstance(entry, dict)}
        view["values"] = {name: _short(entry.get("value")) for name, entry in entries.items()}
        view["ungrounded"] = [name for name, entry in entries.items() if not entry.get("grounded")]
    else:
        view["values_unavailable"] = True
    return view


def review_outcome(ocr: dict[str, Any], fields: dict[str, Any]) -> tuple[str | None, str | None]:
    """OCR の判定と項目抽出の結果を合わせた、最終の判定と理由を返す。

    項目に根拠がない、または抽出に失敗した文書は、OCR の判定が AUTO_APPROVE でも HUMAN_REVIEW に
    引き上げる（検証されていない項目を人の確認なしに通さない）。REJECT と HUMAN_REVIEW は
    下げない。抽出を要求していない文書は OCR の判定のまま。

    Args:
        ocr: 状態遷移の `ocr` 記録。
        fields: 状態遷移の `fields` 記録。

    Returns:
        (最終の action, 人が読む理由)。AUTO_APPROVE のまま理由が無ければ理由は None。
    """
    review = ocr.get("human_review") or {}
    action = review.get("action")
    reasons: list[str] = []
    if action != "AUTO_APPROVE" and review.get("reason"):
        reasons.append(str(review["reason"]))
    status = fields.get("status")
    if status == "completed" and int(fields.get("ungrounded_count") or 0) > 0:
        reasons.append(
            f"{int(fields['ungrounded_count'])} of {int(fields.get('requested') or 0)} requested fields "
            "have no matching evidence in the text"
        )
        if action == "AUTO_APPROVE":
            action = "HUMAN_REVIEW"
    elif status == "failed":
        reasons.append(f"field extraction failed ({str(fields.get('error') or 'unknown')[:60]})")
        if action == "AUTO_APPROVE":
            action = "HUMAN_REVIEW"
    reason = "; ".join(reasons)[:MAX_REVIEW_REASON_CHARS] if reasons else None
    return action, reason


def document_view(record: dict[str, Any], fields_detail: dict[str, Any] | None = None) -> dict[str, Any]:
    """Map の 1 件の記録を、実行結果に載せる小さな形にする。

    Args:
        record: ワークフローの Summarize / RecordFailure が作った記録。
        fields_detail: この文書の `fields.json` の内容（読めたときだけ）。

    Returns:
        `key`、`doc_id`、`status`、完了なら `pages`・`mean_confidence`・`action`（項目抽出を含めた
        最終の判定）・`review_reason`（要レビューのとき）・`result`、失敗なら `error`、
        項目抽出を要求していれば `fields`。
    """
    ocr = record.get("ocr") or {}
    fields = record.get("fields") or {}
    view: dict[str, Any] = {
        "key": record.get("key"),
        "doc_id": record.get("doc_id"),
        "status": ocr.get("status", "failed"),
    }
    if view["status"] == "completed":
        action, reason = review_outcome(ocr, fields)
        view.update(
            {
                "pages": ocr.get("pages"),
                "api": ocr.get("api"),
                "mean_confidence": ocr.get("mean_confidence"),
                "action": action,
                "result": ocr.get("result"),
            }
        )
        if action != "AUTO_APPROVE" and reason:
            view["review_reason"] = reason
    else:
        view["error"] = normalize_error(ocr.get("error"))
    summary = fields_view(fields, fields_detail)
    if summary is not None:
        view["fields"] = summary
    return view


def read_fields_detail(writer: OutputWriter, key: str) -> dict[str, Any] | None:
    """結果バケットから 1 文書の `fields.json` を読む。読めなければ None。

    値が読めなくても、判定に必要な件数は状態遷移の記録にある。ここで失敗しても報告全体は止めない。

    Args:
        writer: 結果バケットの `OutputWriter`。
        key: `fields.json` のキー。

    Returns:
        解析した辞書。読めない、または辞書でないときは None。
    """
    try:
        detail = writer.get_json(key)
    except (ClientError, S3ApHelperError, ValueError) as e:
        logger.warning("Cannot read %s: %s", key, type(e).__name__)
        return None
    return detail if isinstance(detail, dict) else None


def build_views(processed: list[dict[str, Any]], writer: OutputWriter, output_prefix: str) -> list[dict[str, Any]]:
    """Map の結果すべてを、実行結果に載せる形にする。項目抽出が完了した文書は `fields.json` も読む。

    Args:
        processed: Map の結果。
        writer: 結果バケットの `OutputWriter`。
        output_prefix: `{collection}/{execution}`。文書の出力は `{output_prefix}/{doc_id}/` 配下。

    Returns:
        `document_view` の一覧。
    """
    views = []
    for record in processed:
        detail = None
        if (record.get("fields") or {}).get("status") == "completed":
            detail = read_fields_detail(writer, f"{output_prefix}/{record.get('doc_id')}/fields.json")
        views.append(document_view(record, detail))
    return views


def fit_documents(
    views: list[dict[str, Any]], budget_bytes: int = MAX_DOCUMENTS_BYTES
) -> tuple[list[dict[str, Any]], bool]:
    """文書の一覧を、バイト数の上限に収まる先頭から順に切り詰める。

    要レビューと失敗の文書を先に載せる。エージェントが次に見るべきものを落とさないため。

    Args:
        views: `document_view` の一覧。
        budget_bytes: 上限（UTF-8 のバイト数）。

    Returns:
        (収まった一覧, 切り詰めたか)。
    """

    def priority(view: dict[str, Any]) -> int:
        if view.get("status") != "completed":
            return 0
        return 1 if view.get("action") != "AUTO_APPROVE" else 2

    kept: list[dict[str, Any]] = []
    used = 2
    for view in sorted(views, key=priority):
        size = len(json.dumps(view, ensure_ascii=False).encode("utf-8")) + 2
        if used + size > budget_bytes:
            return kept, True
        kept.append(view)
        used += size
    return kept, False


def summarize(views: list[dict[str, Any]], skipped_count: int) -> dict[str, Any]:
    """文書ごとの表示用の記録（`document_view`）から集計を作る。

    `review_required` は項目抽出を含めた最終の判定で数える。

    Args:
        views: `build_views` の結果。
        skipped_count: 対象外として除いた文書数（discovery の値）。

    Returns:
        `total`、`succeeded`、`failed`、`skipped`、`pages`、`review_required`、`mean_confidence`、
        `errors`（エラー型ごとの件数）。
    """
    done = [v for v in views if v["status"] == "completed"]
    confidences = [v["mean_confidence"] for v in done if isinstance(v.get("mean_confidence"), (int, float))]
    return {
        "total": len(views),
        "succeeded": len(done),
        "failed": len(views) - len(done),
        "skipped": skipped_count,
        "pages": sum(int(v.get("pages") or 0) for v in done),
        "review_required": sum(1 for v in done if v.get("action") != "AUTO_APPROVE"),
        "mean_confidence": round(sum(confidences) / len(confidences), 4) if confidences else None,
        "errors": dict(Counter(v["error"]["type"] for v in views if v["status"] != "completed")),
    }


@lambda_error_handler
def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Report Lambda ハンドラー。

    Args:
        event: 通常は `{"discovery": {...}, "processed": [...], "execution_name": ...}`。
            エラー経路（ReportError）では `{"status": "ERROR", "error": {...}, "execution_name": ...}`。
        context: Lambda コンテキスト。

    Returns:
        通常は `status`（completed / completed_with_errors / failed）、`summary`、`review_queue`、
        `documents`、`output` などを持つ辞書。全件失敗のときは `error_type` と `cause` も持つ。
        エラー経路では `status: error`、`error_type`、`cause`。
    """
    if event.get("status") == "ERROR":
        return _handle_error(event)

    discovery = event.get("discovery") or {}
    processed = event.get("processed") or []
    if not isinstance(processed, list):
        processed = []
    classification = discovery.get("classification", "INTERNAL")
    execution_name = str(event.get("execution_name") or discovery.get("execution_name") or "local")
    output_prefix = discovery.get("output_prefix") or f"{discovery.get('collection', 'unknown')}/{execution_name}"
    writer = OutputWriter.from_env()
    views = build_views(processed, writer, output_prefix)
    summary = summarize(views, int(discovery.get("skipped_count", 0)))
    review_queue = [v["key"] for v in views if v["status"] == "completed" and v.get("action") != "AUTO_APPROVE"]

    if summary["total"] and summary["succeeded"] == 0:
        status = "failed"
    elif summary["failed"]:
        status = "completed_with_errors"
    else:
        status = "completed"

    manifest_key = f"{output_prefix}/manifest.json"
    manifest = {
        "schema_version": "1",
        "execution": execution_name,
        "collection": discovery.get("collection"),
        "profile": discovery.get("profile"),
        "status": status,
        "summary": summary,
        "documents": views,
        "skipped": discovery.get("skipped", []),
        "truncated": bool(discovery.get("truncated")),
        "data_classification": classification,
        "generated_at": int(time.time()),
    }
    writer.put_json(manifest_key, manifest)

    documents, documents_truncated = fit_documents(views)
    result: dict[str, Any] = {
        "status": status,
        "collection": discovery.get("collection"),
        "profile": discovery.get("profile"),
        "region": os.environ.get("AWS_REGION", ""),
        "summary": summary,
        "review_queue": review_queue[:50],
        "review_queue_truncated": len(review_queue) > 50,
        "documents": documents,
        "documents_truncated": documents_truncated,
        "skipped": discovery.get("skipped", [])[:20],
        "discovery_truncated": bool(discovery.get("truncated")),
        "output": {"prefix": output_prefix, "manifest": writer.build_s3_uri(manifest_key)},
        "data_classification": classification,
    }
    if status == "failed":
        first = ", ".join(f"{k} x{v}" for k, v in sorted(summary["errors"].items(), key=lambda kv: -kv[1])[:3])
        result["error_type"] = "AllDocumentsFailed"
        result["cause"] = f"All {summary['total']} documents failed ({first}). Details: {result['output']['manifest']}"

    metrics = EmfMetrics(service="japanese-document-ocr-agent")
    metrics.set_dimension("Collection", str(discovery.get("collection", "unknown")))
    metrics.put_metric("WorkflowReports", 1, "Count")
    metrics.put_metric("DocumentsSucceeded", summary["succeeded"], "Count")
    metrics.put_metric("DocumentsFailed", summary["failed"], "Count")
    metrics.flush()
    _notify(result, summary)
    logger.info("Report: status=%s %d/%d succeeded", status, summary["succeeded"], summary["total"])
    return result


def _handle_error(event: dict[str, Any]) -> dict[str, Any]:
    error_type, message = clean_error_message(event.get("error") or {})
    logger.error("Workflow failed: %s: %s", error_type, message)
    metrics = EmfMetrics(service="japanese-document-ocr-agent")
    metrics.put_metric("WorkflowFailures", 1, "Count")
    metrics.flush()
    result = {"status": "error", "error_type": error_type, "cause": message}
    if error_type not in QUIET_ERRORS:
        _notify(result, None)
    return result


def _notify(result: dict[str, Any], summary: dict[str, Any] | None) -> None:
    """SNS に通知する（トピック未設定ならスキップ）。通知の失敗でワークフローを失敗させない。

    Args:
        result: 実行結果。
        summary: 集計。エラー経路では None。
    """
    topic_arn = os.environ.get("SNS_TOPIC_ARN", "")
    if not topic_arn:
        return
    if summary is None:
        subject = f"[FAILED] OCR workflow: {result['error_type']}"
        lines = [f"Error: {result['error_type']}", f"Cause: {result['cause']}"]
    else:
        review = summary["review_required"]
        subject = f"OCR {result['status']}: {summary['succeeded']}/{summary['total']} succeeded"
        if review:
            subject = f"[REVIEW {review}] {subject}"
        if result["status"] == "failed":
            subject = f"[FAILED] {subject}"
        lines = [
            f"Collection: {result['collection']} (profile {result['profile']})",
            f"Documents: {summary['total']} (succeeded {summary['succeeded']}, failed {summary['failed']}, "
            f"skipped {summary['skipped']})",
            f"Pages processed: {summary['pages']}",
            f"Human review required: {review}",
            f"Data classification: {result['data_classification']}",
            f"Manifest: {result['output']['manifest']}",
        ]
    try:
        _sns.publish(TopicArn=topic_arn, Subject=subject[:100], Message="\n".join(lines))
    except Exception as e:  # noqa: BLE001 — 通知の失敗でワークフローを失敗させない
        logger.warning("SNS publish failed: %s", e)
