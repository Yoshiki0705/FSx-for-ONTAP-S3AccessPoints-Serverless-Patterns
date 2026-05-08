"""半導体 / EDA DRC 集計 Lambda ハンドラ

Athena SQL クエリを実行して、メタデータカタログから DRC（Design Rule Check）
統計を集計する。

集計項目:
    - cell_count 分布（min, max, avg, p95）
    - bounding_box 外れ値（IQR 法）
    - 命名規則違反（ハイフン含有等）
    - 無効ファイル数

Glue Data Catalog テーブルを作成/更新し、Athena ワークグループで
クエリを実行する。

Environment Variables:
    GLUE_DATABASE: Glue Data Catalog データベース名
    GLUE_TABLE: Glue Data Catalog テーブル名
    ATHENA_WORKGROUP: Athena ワークグループ名
    OUTPUT_BUCKET: S3 出力バケット名（Athena クエリ結果用）
"""

from __future__ import annotations

import json
import logging
import os
import time

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import xray_subsegment, EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)


# DRC 集計用 Athena SQL クエリ定義
QUERIES = {
    "cell_count_distribution": """
        SELECT
            MIN(cell_count) AS min_cell_count,
            MAX(cell_count) AS max_cell_count,
            AVG(cell_count) AS avg_cell_count,
            APPROX_PERCENTILE(cell_count, 0.95) AS p95_cell_count
        FROM "{database}"."{table}"
        WHERE file_key LIKE '{prefix}%'
          AND cell_count IS NOT NULL
    """,
    "bounding_box_outliers": """
        WITH stats AS (
            SELECT
                APPROX_PERCENTILE(
                    bounding_box.max_x - bounding_box.min_x, 0.25
                ) AS q1_width,
                APPROX_PERCENTILE(
                    bounding_box.max_x - bounding_box.min_x, 0.75
                ) AS q3_width,
                APPROX_PERCENTILE(
                    bounding_box.max_y - bounding_box.min_y, 0.25
                ) AS q1_height,
                APPROX_PERCENTILE(
                    bounding_box.max_y - bounding_box.min_y, 0.75
                ) AS q3_height
            FROM "{database}"."{table}"
            WHERE file_key LIKE '{prefix}%'
        )
        SELECT t.file_key
        FROM "{database}"."{table}" t, stats s
        WHERE t.file_key LIKE '{prefix}%'
          AND (
              (t.bounding_box.max_x - t.bounding_box.min_x)
                  > s.q3_width + 1.5 * (s.q3_width - s.q1_width)
              OR (t.bounding_box.max_y - t.bounding_box.min_y)
                  > s.q3_height + 1.5 * (s.q3_height - s.q1_height)
          )
    """,
    "naming_violations": """
        SELECT file_key
        FROM "{database}"."{table}"
        WHERE file_key LIKE '{prefix}%'
          AND (
              file_key LIKE '%-%'
              OR REGEXP_LIKE(file_key, '[^a-zA-Z0-9_./]')
          )
    """,
    "invalid_files_count": """
        SELECT COUNT(*) AS invalid_count
        FROM "{database}"."{table}"
        WHERE file_key LIKE '{prefix}%'
          AND cell_count IS NULL
    """,
}


def _ensure_glue_table(
    glue_client, database: str, table: str, s3_location: str
) -> None:
    """Glue Data Catalog テーブルを作成/更新する

    EDA メタデータ JSON のスキーマに対応するテーブル定義を作成する。

    Args:
        glue_client: boto3 Glue クライアント
        database: Glue データベース名
        table: Glue テーブル名
        s3_location: メタデータ JSON の S3 ロケーション
    """
    table_input = {
        "Name": table,
        "StorageDescriptor": {
            "Columns": [
                {"Name": "file_key", "Type": "string"},
                {"Name": "file_format", "Type": "string"},
                {"Name": "library_name", "Type": "string"},
                {
                    "Name": "units",
                    "Type": "struct<user_unit:double,db_unit:double>",
                },
                {"Name": "cell_count", "Type": "int"},
                {
                    "Name": "bounding_box",
                    "Type": "struct<min_x:double,min_y:double,max_x:double,max_y:double>",
                },
                {"Name": "creation_date", "Type": "string"},
                {"Name": "file_version", "Type": "string"},
                {"Name": "extracted_at", "Type": "string"},
            ],
            "Location": s3_location,
            "InputFormat": "org.apache.hadoop.mapred.TextInputFormat",
            "OutputFormat": (
                "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"
            ),
            "SerdeInfo": {
                "SerializationLibrary": "org.openx.data.jsonserde.JsonSerDe",
            },
        },
        "TableType": "EXTERNAL_TABLE",
    }

    try:
        glue_client.update_table(
            DatabaseName=database,
            TableInput=table_input,
        )
        logger.info("Updated Glue table %s.%s", database, table)
    except glue_client.exceptions.EntityNotFoundException:
        glue_client.create_table(
            DatabaseName=database,
            TableInput=table_input,
        )
        logger.info("Created Glue table %s.%s", database, table)


def _execute_athena_query(
    athena_client,
    query: str,
    database: str,
    workgroup: str,
    output_location: str,
) -> dict:
    """Athena クエリを実行し、結果を返す

    Args:
        athena_client: boto3 Athena クライアント
        query: SQL クエリ文字列
        database: Glue データベース名
        workgroup: Athena ワークグループ名
        output_location: クエリ結果の S3 出力先

    Returns:
        dict: クエリ結果 (status, rows, query_execution_id)
    """
    with xray_subsegment(

        name="athena_startqueryexecution",

        annotations={"service_name": "athena", "operation": "StartQueryExecution", "use_case": "semiconductor-eda"},

    ):

        response = athena_client.start_query_execution(
        QueryString=query,
        QueryExecutionContext={"Database": database},
        WorkGroup=workgroup,
        ResultConfiguration={"OutputLocation": output_location},
    )
    query_execution_id = response["QueryExecutionId"]

    # クエリ完了を待機（最大 5 分）
    max_wait = 300
    elapsed = 0
    while elapsed < max_wait:
        status = athena_client.get_query_execution(
            QueryExecutionId=query_execution_id,
        )
        state = status["QueryExecution"]["Status"]["State"]
        if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(2)
        elapsed += 2

    if state != "SUCCEEDED":
        reason = status["QueryExecution"]["Status"].get(
            "StateChangeReason", "Unknown"
        )
        logger.error("Athena query failed: %s - %s", state, reason)
        return {
            "status": state,
            "reason": reason,
            "rows": [],
            "query_execution_id": query_execution_id,
        }

    # 結果取得
    results = athena_client.get_query_results(
        QueryExecutionId=query_execution_id,
    )

    rows = []
    result_set = results.get("ResultSet", {})
    column_info = result_set.get("ResultSetMetadata", {}).get(
        "ColumnInfo", []
    )
    data_rows = result_set.get("Rows", [])

    # 最初の行はヘッダー
    for row in data_rows[1:]:
        row_data = {}
        for i, col in enumerate(column_info):
            value = row["Data"][i].get("VarCharValue", "")
            row_data[col["Name"]] = value
        rows.append(row_data)

    return {
        "status": "SUCCEEDED",
        "rows": rows,
        "query_execution_id": query_execution_id,
    }


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """半導体 / EDA DRC 集計 Lambda

    Athena SQL クエリを実行して DRC 統計を集計する。
    Glue Data Catalog テーブルを作成/更新し、cell_count 分布、
    bounding_box 外れ値、命名規則違反、無効ファイル数を集計する。

    Args:
        event: メタデータ抽出結果
            {"metadata_prefix": "metadata/2026/01/15/", "total_files": 150}

    Returns:
        dict: status, statistics, query_execution_id
    """
    database = os.environ["GLUE_DATABASE"]
    table = os.environ["GLUE_TABLE"]
    workgroup = os.environ["ATHENA_WORKGROUP"]
    output_bucket = os.environ["OUTPUT_BUCKET"]

    metadata_prefix = event.get("metadata_prefix", "")
    total_files = event.get("total_objects", event.get("total_files", 0))

    # Glue テーブルの S3 ロケーション
    s3_location = f"s3://{output_bucket}/metadata/"
    # Athena クエリ結果の出力先
    output_location = f"s3://{output_bucket}/athena-results/"

    logger.info(
        "DRC Aggregation started: database=%s, table=%s, "
        "metadata_prefix=%s, total_files=%d",
        database,
        table,
        metadata_prefix,
        total_files,
    )

    # Glue テーブル作成/更新
    glue_client = boto3.client("glue")
    _ensure_glue_table(glue_client, database, table, s3_location)

    # Athena クエリ実行
    athena_client = boto3.client("athena")
    statistics = {
        "total_designs": total_files,
        "cell_count_distribution": {"min": 0, "max": 0, "avg": 0, "p95": 0},
        "bounding_box_outliers": [],
        "naming_violations": [],
        "invalid_files": 0,
    }
    last_query_execution_id = ""

    for query_name, query_template in QUERIES.items():
        query = query_template.format(
            database=database,
            table=table,
            prefix=metadata_prefix,
        )
        logger.info("Executing Athena query: %s", query_name)

        result = _execute_athena_query(
            athena_client=athena_client,
            query=query,
            database=database,
            workgroup=workgroup,
            output_location=output_location,
        )
        last_query_execution_id = result.get(
            "query_execution_id", last_query_execution_id
        )

        if result["status"] != "SUCCEEDED":
            logger.warning(
                "Query %s failed: %s",
                query_name,
                result.get("reason", "Unknown"),
            )
            continue

        rows = result.get("rows", [])

        if query_name == "cell_count_distribution" and rows:
            row = rows[0]
            statistics["cell_count_distribution"] = {
                "min": _safe_int(row.get("min_cell_count", "0")),
                "max": _safe_int(row.get("max_cell_count", "0")),
                "avg": _safe_int(row.get("avg_cell_count", "0")),
                "p95": _safe_int(row.get("p95_cell_count", "0")),
            }

        elif query_name == "bounding_box_outliers":
            statistics["bounding_box_outliers"] = [
                row.get("file_key", "") for row in rows
            ]

        elif query_name == "naming_violations":
            statistics["naming_violations"] = [
                row.get("file_key", "") for row in rows
            ]

        elif query_name == "invalid_files_count" and rows:
            statistics["invalid_files"] = _safe_int(
                rows[0].get("invalid_count", "0")
            )

        logger.info(
            "Query %s completed: %d rows", query_name, len(rows)
        )

    logger.info(
        "DRC Aggregation completed: total_designs=%d, invalid=%d",
        statistics["total_designs"],
        statistics["invalid_files"],
    )


    # EMF メトリクス出力
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="drc_aggregation")
    metrics.set_dimension("UseCase", os.environ.get("USE_CASE", "semiconductor-eda"))
    metrics.put_metric("FilesProcessed", 1.0, "Count")
    metrics.flush()

    return {
        "status": "SUCCESS",
        "statistics": statistics,
        "query_execution_id": last_query_execution_id,
    }


def _safe_int(value: str) -> int:
    """文字列を安全に整数に変換する

    Args:
        value: 変換対象の文字列

    Returns:
        int: 変換結果（変換失敗時は 0）
    """
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return 0
