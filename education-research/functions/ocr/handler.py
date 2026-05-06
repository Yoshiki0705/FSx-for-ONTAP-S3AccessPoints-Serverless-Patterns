"""教育 / 研究 OCR Lambda ハンドラ

Cross_Region_Client で Amazon Textract に論文 PDF を送信し、テキスト抽出を実行する。
処理不能 PDF はエラーログ出力しワークフロー継続する。

Textract は ap-northeast-1 非対応のため、CrossRegionClient を使用して
us-east-1 にルーティングする。

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    OUTPUT_BUCKET: S3 出力バケット名
    CROSS_REGION: クロスリージョンターゲット (デフォルト: us-east-1)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import PurePosixPath

import boto3

from shared.cross_region_client import CrossRegionClient, CrossRegionConfig
from shared.exceptions import lambda_error_handler
from shared.s3ap_helper import S3ApHelper
from shared.observability import xray_subsegment, EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)

DEFAULT_CROSS_REGION = "us-east-1"


def _extract_text_from_blocks(blocks: list[dict]) -> str:
    """Textract レスポンスブロックからテキストを抽出する"""
    lines = []
    for block in blocks:
        if block.get("BlockType") == "LINE":
            text = block.get("Text", "")
            if text:
                lines.append(text)
    return "\n".join(lines)


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """論文 PDF OCR（Cross-Region Textract）

    Input:
        {"Key": "papers/research_2026.pdf", "Size": 3145728, ...}

    Output:
        {
            "status": "SUCCESS" | "ERROR",
            "file_key": "...",
            "extracted_text": "...",
            "page_count": 10,
            "output_key": "..."
        }
    """
    file_key = event["Key"]
    file_size = event.get("Size", 0)

    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    output_bucket = os.environ["OUTPUT_BUCKET"]
    cross_region = os.environ.get("CROSS_REGION", DEFAULT_CROSS_REGION)

    logger.info(
        "Education OCR started: file_key=%s, size=%d, cross_region=%s",
        file_key,
        file_size,
        cross_region,
    )

    # PDF ファイル取得
    try:
        response = s3ap.get_object(file_key)
        body = response["Body"]
        document_bytes = body.read()
        body.close()
    except Exception as e:
        logger.error("Failed to read PDF file %s: %s", file_key, e)
        return {
            "status": "ERROR",
            "file_key": file_key,
            "error": f"Failed to read file: {e}",
            "extracted_text": "",
            "page_count": 0,
        }

    # Cross-Region Textract で OCR 実行
    cross_region_config = CrossRegionConfig(
        target_region=cross_region,
        services=["textract"],
    )
    cross_region_client = CrossRegionClient(cross_region_config)

    try:
        textract_response = cross_region_client.analyze_document(
            document_bytes=document_bytes,
            feature_types=["TABLES", "FORMS"],
        )
    except Exception as e:
        logger.error("Textract failed for %s: %s", file_key, e)
        return {
            "status": "ERROR",
            "file_key": file_key,
            "error": f"Textract failed: {e}",
            "extracted_text": "",
            "page_count": 0,
        }

    # テキスト抽出
    blocks = textract_response.get("Blocks", [])
    extracted_text = _extract_text_from_blocks(blocks)

    # ページ数推定
    page_blocks = [b for b in blocks if b.get("BlockType") == "PAGE"]
    page_count = len(page_blocks) if page_blocks else 1

    # 出力キー生成
    now = datetime.now(timezone.utc)
    file_stem = PurePosixPath(file_key).stem
    output_key = f"ocr/{now.strftime('%Y/%m/%d')}/{file_stem}_text.json"

    # 結果を S3 出力バケットに書き込み
    result = {
        "status": "SUCCESS",
        "file_key": file_key,
        "extracted_text": extracted_text,
        "page_count": page_count,
        "output_key": output_key,
        "extracted_at": now.isoformat(),
    }

    s3_client = boto3.client("s3")
    s3_client.put_object(
        Bucket=output_bucket,
        Key=output_key,
        Body=json.dumps(result, default=str, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json; charset=utf-8",
    )

    logger.info(
        "Education OCR completed: file_key=%s, text_length=%d, pages=%d",
        file_key,
        len(extracted_text),
        page_count,
    )


    # EMF メトリクス出力
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="ocr")
    metrics.set_dimension("UseCase", os.environ.get("USE_CASE", "education-research"))
    metrics.put_metric("FilesProcessed", 1.0, "Count")
    metrics.flush()

    return result
