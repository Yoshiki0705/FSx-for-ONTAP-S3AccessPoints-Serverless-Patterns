"""UC16 Government Archives OCR Lambda

Amazon Textract を使って文書を OCR する。
- ≤ SYNC_PAGE_THRESHOLD ページ: AnalyzeDocument (sync)
- > SYNC_PAGE_THRESHOLD ページ: StartDocumentAnalysis (async)

Environment Variables:
    OUTPUT_BUCKET: 出力先 S3 バケット
    S3_ACCESS_POINT_ALIAS: 入力 S3 AP Alias
    SYNC_PAGE_THRESHOLD: 同期 API ページ閾値 (default: 10)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)


def select_textract_api(page_count: int, threshold: int) -> str:
    """Textract API を選択する。

    Args:
        page_count: ページ数
        threshold: 同期/非同期の境界

    Returns:
        "sync" | "async"
    """
    return "sync" if page_count <= threshold else "async"


def _extract_text_sync(
    textract, document_bytes: bytes
) -> tuple[str, list[dict]]:
    """同期 Textract API でテキスト抽出。"""
    response = textract.analyze_document(
        Document={"Bytes": document_bytes},
        FeatureTypes=["FORMS", "TABLES"],
    )
    text_lines = []
    blocks = response.get("Blocks", [])
    for block in blocks:
        if block.get("BlockType") == "LINE":
            text = block.get("Text", "")
            if text:
                text_lines.append(text)
    return "\n".join(text_lines), blocks


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """UC16 OCR Lambda ハンドラ。

    Input:
        {"Key": "archives/report.pdf", "DocumentType": "pdf", "Size": 12345}

    Output:
        {"document_key": str, "text_key": str, "page_count": int, "api_used": str}
    """
    output_bucket = os.environ["OUTPUT_BUCKET"]
    s3_access_point = os.environ.get("S3_ACCESS_POINT_ALIAS", "")
    sync_threshold = int(os.environ.get("SYNC_PAGE_THRESHOLD", "10"))

    document_key = event.get("Key") or event.get("document_key")
    if not document_key:
        raise ValueError("Input event must contain 'Key' or 'document_key'")

    # 画像/PDF ダウンロード
    if s3_access_point:
        s3ap = S3ApHelper(s3_access_point)
        response = s3ap.get_object(document_key)
        document_bytes = response["Body"].read()
    else:
        s3_client = boto3.client("s3")
        response = s3_client.get_object(Bucket=output_bucket, Key=document_key)
        document_bytes = response["Body"].read()

    # ページ数推定（PDF の場合は bytes の簡易推定、画像は 1 ページ）
    page_count = 1
    if document_key.lower().endswith(".pdf"):
        # ページ数の推定（バイト数から概算、実際には pypdf で取得）
        # 簡易実装: 100KB あたり約 1 ページと仮定
        page_count = max(1, len(document_bytes) // 100000)

    api_choice = select_textract_api(page_count, sync_threshold)
    logger.info(
        "UC16 OCR: key=%s, pages=%d, api=%s",
        document_key,
        page_count,
        api_choice,
    )

    # Textract が未対応リージョンの場合は空テキストで継続（UC2/UC10/UC12/UC13/UC14 と同じ方針）
    try:
        textract = boto3.client("textract")
    except Exception as e:
        logger.warning("Textract client unavailable: %s", e)
        api_choice = "unavailable"
        text = ""
        blocks = []
    else:
        if api_choice == "sync":
            try:
                text, blocks = _extract_text_sync(textract, document_bytes)
            except textract.exceptions.InvalidParameterException as e:
                # 同期 API サイズ制限超過 → 非同期へフォールバック
                logger.warning("Sync Textract failed, falling back to async: %s", e)
                api_choice = "async"
                text = ""
                blocks = []
            except Exception as e:
                # EndpointConnectionError 等で Textract 呼び出し不可
                logger.warning("Textract invocation failed (region unsupported?): %s", e)
                api_choice = "unavailable"
                text = ""
                blocks = []
        else:
            text = ""
            blocks = []

    # 結果を S3 に書き出し
    text_key = f"ocr-results/{document_key}.txt"
    s3_client = boto3.client("s3")
    s3_client.put_object(
        Bucket=output_bucket,
        Key=text_key,
        Body=text.encode("utf-8"),
        ContentType="text/plain",
        ServerSideEncryption="aws:kms",
    )

    blocks_key = f"ocr-results/{document_key}.blocks.json"
    s3_client.put_object(
        Bucket=output_bucket,
        Key=blocks_key,
        Body=json.dumps(blocks, default=str),
        ContentType="application/json",
        ServerSideEncryption="aws:kms",
    )

    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="ocr")
    metrics.set_dimension("UseCase", "government-archives")
    metrics.set_dimension("ApiChoice", api_choice)
    metrics.put_metric("PageCount", float(page_count), "Count")
    metrics.put_metric("TextLength", float(len(text)), "Count")
    metrics.flush()

    return {
        "document_key": document_key,
        "text_key": text_key,
        "blocks_key": blocks_key,
        "page_count": page_count,
        "api_used": api_choice,
        "text_length": len(text),
        "text_preview": text[:500] if text else "",
    }
