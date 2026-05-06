"""製造業 Transform Lambda ハンドラ

Map ステートから CSV ファイル情報を受け取り、S3 AP 経由で CSV を取得して
JSON Lines 形式に変換し、S3 AP に書き出す。

標準ライブラリのみ使用（外部依存なし）。
大規模データの Parquet 変換は Glue ETL 拡張パターンを使用すること。

参考:
- AWS Lambda でサーバーレス処理: https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-process-files-with-lambda.html
- Glue ETL パイプライン: https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-transform-data-with-glue.html

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用)
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os

from shared.exceptions import lambda_error_handler
from shared.s3ap_helper import S3ApHelper
from shared.observability import xray_subsegment, EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)


def csv_to_jsonlines(csv_bytes: bytes) -> tuple[str, int]:
    """CSV バイト列を JSON Lines 文字列に変換する

    標準ライブラリのみ使用。各行を JSON オブジェクトに変換し、
    改行区切りで連結する。

    Args:
        csv_bytes: CSV ファイルのバイト列

    Returns:
        tuple[str, int]: (JSON Lines 文字列, レコード数)
    """
    text = csv_bytes.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))

    lines: list[str] = []
    for row in reader:
        # 数値フィールドの型変換を試行
        converted: dict = {}
        for key, value in row.items():
            try:
                converted[key] = float(value)
            except (ValueError, TypeError):
                converted[key] = value
        lines.append(json.dumps(converted, ensure_ascii=False))

    return "\n".join(lines) + "\n", len(lines)


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """Transform Lambda

    Map ステートから CSV ファイル情報を受け取り、
    CSV → JSON Lines 変換して S3 AP に書き出す。

    Args:
        event: Map ステートからの入力
            {"Key": str, "Size": int}

    Returns:
        dict: output_key, original_key, record_count, status
    """
    csv_key = event["Key"]

    logger.info("Transform started: csv_key=%s", csv_key)

    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    response = s3ap.get_object(csv_key)
    csv_bytes = response["Body"].read()

    logger.info("CSV file retrieved: key=%s, size=%d bytes", csv_key, len(csv_bytes))

    jsonlines_str, record_count = csv_to_jsonlines(csv_bytes)

    output_key = csv_key.rsplit(".", 1)[0] + ".jsonl"
    output_key = f"transformed/{output_key}"

    s3ap_output = S3ApHelper(
        os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ["S3_ACCESS_POINT"])
    )
    s3ap_output.put_object(
        key=output_key,
        body=jsonlines_str,
        content_type="application/x-ndjson",
    )

    logger.info(
        "Transform completed: %s → %s (%d records)",
        csv_key,
        output_key,
        record_count,
    )


    # EMF メトリクス出力
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="transform")
    metrics.set_dimension("UseCase", os.environ.get("USE_CASE", "manufacturing-analytics"))
    metrics.put_metric("FilesProcessed", 1.0, "Count")
    metrics.flush()

    return {
        "output_key": output_key,
        "original_key": csv_key,
        "record_count": record_count,
        "status": "SUCCESS",
    }
