"""建設 / AEC OCR Lambda ハンドラ

Cross_Region_Client で Amazon Textract に図面 PDF を送信し、
テキスト・テーブル抽出を実行する。

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

logger = logging.getLogger(__name__)

DEFAULT_CROSS_REGION = "us-east-1"


def _extract_text_from_blocks(blocks: list[dict]) -> str:
    """Textract レスポンスブロックからテキストを抽出する

    Args:
        blocks: Textract AnalyzeDocument レスポンスの Blocks

    Returns:
        str: 抽出されたテキスト
    """
    lines = []
    for block in blocks:
        if block.get("BlockType") == "LINE":
            text = block.get("Text", "")
            if text:
                lines.append(text)
    return "\n".join(lines)


def _extract_tables_from_blocks(blocks: list[dict]) -> list[dict]:
    """Textract レスポンスブロックからテーブルを抽出する

    Args:
        blocks: Textract AnalyzeDocument レスポンスの Blocks

    Returns:
        list[dict]: 抽出されたテーブルのリスト
    """
    # ブロック ID → ブロックのマッピング
    block_map = {block["Id"]: block for block in blocks if "Id" in block}

    tables = []
    for block in blocks:
        if block.get("BlockType") != "TABLE":
            continue

        table_data = {"rows": []}
        relationships = block.get("Relationships", [])

        # テーブルのセルを収集
        cells = []
        for rel in relationships:
            if rel.get("Type") == "CHILD":
                for child_id in rel.get("Ids", []):
                    child_block = block_map.get(child_id, {})
                    if child_block.get("BlockType") == "CELL":
                        cells.append(child_block)

        # セルを行・列で整理
        if cells:
            max_row = max(c.get("RowIndex", 1) for c in cells)
            max_col = max(c.get("ColumnIndex", 1) for c in cells)

            for row_idx in range(1, max_row + 1):
                row = []
                for col_idx in range(1, max_col + 1):
                    cell_text = ""
                    for cell in cells:
                        if (
                            cell.get("RowIndex") == row_idx
                            and cell.get("ColumnIndex") == col_idx
                        ):
                            # セルのテキストを取得
                            cell_rels = cell.get("Relationships", [])
                            for cell_rel in cell_rels:
                                if cell_rel.get("Type") == "CHILD":
                                    for word_id in cell_rel.get("Ids", []):
                                        word_block = block_map.get(word_id, {})
                                        if word_block.get("BlockType") == "WORD":
                                            cell_text += word_block.get("Text", "") + " "
                            break
                    row.append(cell_text.strip())
                table_data["rows"].append(row)

        tables.append(table_data)

    return tables


@lambda_error_handler
def handler(event, context):
    """図面 PDF OCR（Cross-Region Textract）

    Input:
        {"Key": "drawings/floor_plan.pdf", "Size": 5242880, ...}

    Output:
        {
            "status": "SUCCESS",
            "file_key": "...",
            "extracted_text": "...",
            "tables": [...],
            "output_key": "..."
        }
    """
    file_key = event["Key"]
    file_size = event.get("Size", 0)

    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    output_bucket = os.environ["OUTPUT_BUCKET"]
    cross_region = os.environ.get("CROSS_REGION", DEFAULT_CROSS_REGION)

    logger.info(
        "OCR started: file_key=%s, size=%d, cross_region=%s",
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
            "tables": [],
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
        logger.error("Textract AnalyzeDocument failed for %s: %s", file_key, e)
        return {
            "status": "ERROR",
            "file_key": file_key,
            "error": f"Textract failed: {e}",
            "extracted_text": "",
            "tables": [],
        }

    # テキストとテーブルの抽出
    blocks = textract_response.get("Blocks", [])
    extracted_text = _extract_text_from_blocks(blocks)
    tables = _extract_tables_from_blocks(blocks)

    # 出力キー生成
    now = datetime.now(timezone.utc)
    file_stem = PurePosixPath(file_key).stem
    output_key = f"ocr/{now.strftime('%Y/%m/%d')}/{file_stem}_ocr.json"

    # 結果を S3 出力バケットに書き込み
    result = {
        "status": "SUCCESS",
        "file_key": file_key,
        "extracted_text": extracted_text,
        "tables": tables,
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
        "OCR completed: file_key=%s, text_length=%d, tables=%d",
        file_key,
        len(extracted_text),
        len(tables),
    )

    return result
