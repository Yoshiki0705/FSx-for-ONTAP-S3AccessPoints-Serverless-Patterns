"""UC16 Government Archives OCR Lambda

Amazon Textract を使って文書を OCR する。
Textract は ap-northeast-1 未対応のため、`shared.cross_region_client.CrossRegionClient`
経由で us-east-1 等の対応リージョンへルーティングする（UC2/UC10/UC12/UC13/UC14 と同じパターン）。

ルーティング:
- ≤ SYNC_PAGE_THRESHOLD ページ: AnalyzeDocument (sync)
- > SYNC_PAGE_THRESHOLD ページ: StartDocumentAnalysis (async)

Environment Variables:
    S3_ACCESS_POINT_ALIAS: 入力 S3 AP Alias
    SYNC_PAGE_THRESHOLD: 同期 API ページ閾値 (default: 10)
    CROSS_REGION: Textract クロスリージョンターゲット (default: us-east-1)
    USE_CROSS_REGION: "true" でクロスリージョン、"false" で同一リージョン (default: "true")
    OUTPUT_DESTINATION: `STANDARD_S3` or `FSXN_S3AP` (デフォルト: `STANDARD_S3`)
    OUTPUT_BUCKET: STANDARD_S3 モードの出力バケット（同時に下流 Lambda が読み書きする作業バケット）
    OUTPUT_S3AP_ALIAS: FSXN_S3AP モードの S3AP Alias or ARN
    OUTPUT_S3AP_PREFIX: FSXN_S3AP モードの出力プレフィックス
"""

from __future__ import annotations

import logging
import os

import boto3

from shared.cross_region_client import CrossRegionClient, CrossRegionConfig
from shared.exceptions import CrossRegionClientError, lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler
from shared.output_writer import OutputWriter
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)

DEFAULT_CROSS_REGION = "us-east-1"


def select_textract_api(page_count: int, threshold: int) -> str:
    """Textract API を選択する。

    Args:
        page_count: ページ数
        threshold: 同期/非同期の境界

    Returns:
        "sync" | "async"
    """
    return "sync" if page_count <= threshold else "async"


def _extract_text_from_blocks(blocks: list[dict]) -> str:
    """Textract Blocks からテキスト行を抽出する。"""
    lines = []
    for block in blocks:
        if block.get("BlockType") == "LINE":
            text = block.get("Text", "")
            if text:
                lines.append(text)
    return "\n".join(lines)


def _extract_text_sync(
    textract, document_bytes: bytes
) -> tuple[str, list[dict]]:
    """同期 Textract API でテキスト抽出（直接 boto3 client 経由、UT 互換）。"""
    response = textract.analyze_document(
        Document={"Bytes": document_bytes},
        FeatureTypes=["FORMS", "TABLES"],
    )
    blocks = response.get("Blocks", [])
    return _extract_text_from_blocks(blocks), blocks


def _invoke_textract(
    document_bytes: bytes, use_cross_region: bool, cross_region_target: str
) -> tuple[str, list[dict], str]:
    """Textract 呼び出し（cross-region 優先、同一リージョン fallback）。

    Returns:
        (text, blocks, mode) ここで mode は "cross_region" | "same_region" | "unavailable"
    """
    if use_cross_region:
        try:
            client = CrossRegionClient(
                config=CrossRegionConfig(target_region=cross_region_target)
            )
            response = client.analyze_document(
                document_bytes=document_bytes,
                feature_types=["FORMS", "TABLES"],
            )
            blocks = response.get("Blocks", [])
            return _extract_text_from_blocks(blocks), blocks, "cross_region"
        except CrossRegionClientError as e:
            logger.warning(
                "Cross-region Textract failed, trying same region: %s", e
            )
        except Exception as e:
            logger.warning(
                "Cross-region Textract client init failed: %s", e
            )

    # same-region fallback
    try:
        textract = boto3.client("textract")
        text, blocks = _extract_text_sync(textract, document_bytes)
        return text, blocks, "same_region"
    except Exception as e:
        logger.warning(
            "Same-region Textract invocation failed (region unsupported?): %s", e
        )
        return "", [], "unavailable"


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """UC16 OCR Lambda ハンドラ。

    Input:
        {"Key": "archives/report.pdf", "DocumentType": "pdf", "Size": 12345}

    Output:
        {"document_key": str, "text_key": str, "page_count": int, "api_used": str}
    """
    output_writer = OutputWriter.from_env()
    s3_access_point = os.environ.get("S3_ACCESS_POINT_ALIAS", "")
    sync_threshold = int(os.environ.get("SYNC_PAGE_THRESHOLD", "10"))
    use_cross_region = os.environ.get("USE_CROSS_REGION", "true").lower() == "true"
    cross_region_target = os.environ.get("CROSS_REGION", DEFAULT_CROSS_REGION)

    document_key = event.get("Key") or event.get("document_key")
    if not document_key:
        raise ValueError("Input event must contain 'Key' or 'document_key'")

    # 画像/PDF ダウンロード
    if s3_access_point:
        s3ap = S3ApHelper(s3_access_point)
        response = s3ap.get_object(document_key)
        document_bytes = response["Body"].read()
    else:
        # Fallback: OUTPUT_BUCKET から直接読み取り（テスト互換）
        fallback_bucket = os.environ.get("OUTPUT_BUCKET", "")
        s3_client = boto3.client("s3")
        response = s3_client.get_object(Bucket=fallback_bucket, Key=document_key)
        document_bytes = response["Body"].read()

    # ページ数推定（PDF のバイト数から概算、画像は 1 ページ）
    page_count = 1
    if document_key.lower().endswith(".pdf"):
        # 100KB あたり約 1 ページと仮定（実運用では pypdf 推奨）
        page_count = max(1, len(document_bytes) // 100000)

    api_choice = select_textract_api(page_count, sync_threshold)
    logger.info(
        "UC16 OCR: key=%s, pages=%d, api=%s, cross_region=%s",
        document_key,
        page_count,
        api_choice,
        use_cross_region,
    )

    # Textract 呼び出し
    if api_choice == "sync":
        text, blocks, invoke_mode = _invoke_textract(
            document_bytes, use_cross_region, cross_region_target
        )
        if invoke_mode == "unavailable":
            api_choice = "unavailable"
    else:
        # async 経路は別 Lambda 推奨、ここでは空を返す
        text, blocks, invoke_mode = "", [], "async_not_implemented"

    # 結果を出力先に書き出し（OutputWriter で STANDARD_S3 / FSXN_S3AP 切替）
    text_key = f"ocr-results/{document_key}.txt"
    output_writer.put_text(key=text_key, text=text)

    blocks_key = f"ocr-results/{document_key}.blocks.json"
    output_writer.put_json(key=blocks_key, data=blocks)

    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="ocr")
    metrics.set_dimension("UseCase", "government-archives")
    metrics.set_dimension("ApiChoice", api_choice)
    metrics.set_dimension("InvokeMode", invoke_mode)
    metrics.put_metric("PageCount", float(page_count), "Count")
    metrics.put_metric("TextLength", float(len(text)), "Count")
    metrics.flush()

    return {
        "document_key": document_key,
        "text_key": text_key,
        "blocks_key": blocks_key,
        "page_count": page_count,
        "api_used": api_choice,
        "invoke_mode": invoke_mode,
        "text_length": len(text),
        "text_preview": text[:500] if text else "",
    }
