"""保険 / 損害査定 見積書 OCR Lambda ハンドラ

Cross_Region_Client で Amazon Textract に見積書を送信し、
テキスト・テーブル抽出（修理項目、費用、工数、部品）を実行する。

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    OUTPUT_DESTINATION: `STANDARD_S3` or `FSXN_S3AP` (デフォルト: `STANDARD_S3`)
    OUTPUT_BUCKET: STANDARD_S3 モードの出力バケット名
    OUTPUT_S3AP_ALIAS: FSXN_S3AP モードの S3AP Alias or ARN
    OUTPUT_S3AP_PREFIX: FSXN_S3AP モードの出力プレフィックス (デフォルト: `ai-outputs/`)
    CROSS_REGION: クロスリージョンターゲット (デフォルト: us-east-1)
    LOG_PII_DATA: PII データのログ出力 (デフォルト: false)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import PurePosixPath


from shared.cross_region_client import CrossRegionClient, CrossRegionConfig
from shared.exceptions import lambda_error_handler
from shared.output_writer import OutputWriter
from shared.s3ap_helper import S3ApHelper
from shared.observability import EmfMetrics, trace_lambda_handler

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


def _extract_tables_from_blocks(blocks: list[dict]) -> list[dict]:
    """Textract レスポンスブロックからテーブルを抽出する"""
    block_map = {block["Id"]: block for block in blocks if "Id" in block}
    tables = []

    for block in blocks:
        if block.get("BlockType") != "TABLE":
            continue

        table_data = {"rows": []}
        relationships = block.get("Relationships", [])

        cells = []
        for rel in relationships:
            if rel.get("Type") == "CHILD":
                for child_id in rel.get("Ids", []):
                    child_block = block_map.get(child_id, {})
                    if child_block.get("BlockType") == "CELL":
                        cells.append(child_block)

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


def _parse_estimate_data(text: str, tables: list[dict]) -> dict:
    """見積書データを解析する

    Args:
        text: 抽出されたテキスト
        tables: 抽出されたテーブル

    Returns:
        dict: 構造化見積書データ
    """
    repair_items = []
    total_parts_cost = 0
    total_labor_cost = 0

    # テーブルから修理項目を抽出
    for table in tables:
        for row in table.get("rows", [])[1:]:  # ヘッダー行をスキップ
            if len(row) >= 2:
                item_name = row[0] if row[0] else ""
                cost_str = row[1] if len(row) > 1 else "0"

                # 数値抽出
                import re
                cost_match = re.search(r"[\d,]+", cost_str.replace(",", ""))
                cost = int(cost_match.group().replace(",", "")) if cost_match else 0

                labor_str = row[2] if len(row) > 2 else "0"
                labor_match = re.search(r"[\d.]+", labor_str)
                labor_hours = float(labor_match.group()) if labor_match else 0.0

                if item_name:
                    repair_items.append({
                        "item": item_name,
                        "cost": cost,
                        "labor_hours": labor_hours,
                    })
                    total_parts_cost += cost

    return {
        "repair_items": repair_items,
        "total_parts_cost": total_parts_cost,
        "total_labor_cost": total_labor_cost,
        "total_estimate": total_parts_cost + total_labor_cost,
        "currency": "JPY",
    }


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """見積書 OCR（Cross-Region Textract）

    Input:
        {"Key": "claims/CLM20260115_001/estimate.pdf", "Size": 2097152, ...}

    Output:
        {
            "status": "SUCCESS",
            "file_key": "...",
            "estimate_data": {...},
            "output_key": "..."
        }
    """
    file_key = event["Key"]
    file_size = event.get("Size", 0)

    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    output_writer = OutputWriter.from_env()
    cross_region = os.environ.get("CROSS_REGION", DEFAULT_CROSS_REGION)

    logger.info(
        "Estimate OCR started: file_key=%s, size=%d, cross_region=%s, output=%s",
        file_key,
        file_size,
        cross_region,
        output_writer.target_description,
    )

    # 見積書取得
    try:
        response = s3ap.get_object(file_key)
        body = response["Body"]
        document_bytes = body.read()
        body.close()
    except Exception as e:
        logger.error("Failed to read estimate %s: %s", file_key, e)
        return {
            "status": "ERROR",
            "file_key": file_key,
            "error": f"Failed to read file: {e}",
            "estimate_data": {},
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
            "estimate_data": {},
        }

    # テキストとテーブルの抽出
    blocks = textract_response.get("Blocks", [])
    extracted_text = _extract_text_from_blocks(blocks)
    tables = _extract_tables_from_blocks(blocks)

    # 見積書データ解析
    estimate_data = _parse_estimate_data(extracted_text, tables)

    # 出力キー生成
    now = datetime.now(timezone.utc)
    file_stem = PurePosixPath(file_key).stem
    output_key = f"estimates/{now.strftime('%Y/%m/%d')}/{file_stem}_estimate.json"

    # 結果を出力先（標準 S3 または FSxN S3AP）に書き込み
    result = {
        "status": "SUCCESS",
        "file_key": file_key,
        "estimate_data": estimate_data,
        "extracted_text": extracted_text,
        "tables": tables,
        "output_key": output_key,
        "extracted_at": now.isoformat(),
    }

    output_writer.put_json(key=output_key, data=result)

    logger.info(
        "Estimate OCR completed: file_key=%s, items=%d, total=%d, output_uri=%s",
        file_key,
        len(estimate_data.get("repair_items", [])),
        estimate_data.get("total_estimate", 0),
        output_writer.build_s3_uri(output_key),
    )


    # EMF メトリクス出力
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="estimate_ocr")
    metrics.set_dimension("UseCase", os.environ.get("USE_CASE", "insurance-claims"))
    metrics.put_metric("FilesProcessed", 1.0, "Count")
    metrics.flush()

    return result
