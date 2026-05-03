"""製造業 Athena Analysis Lambda ハンドラ

Parquet 変換済みセンサーログに対して Athena SQL クエリを実行し、
設定可能な閾値に基づいて異常センサー値を検出する。

検出対象:
- 温度異常（閾値超過）
- 振動異常（閾値超過）
- 圧力異常（閾値超過）

Environment Variables:
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias (Parquet データの LOCATION 用)
    ATHENA_RESULTS_BUCKET: Athena クエリ結果の S3 バケット名
    GLUE_DATABASE: Glue Data Catalog データベース名
    GLUE_TABLE: Glue Data Catalog テーブル名
    ATHENA_WORKGROUP: Athena ワークグループ名
    ANOMALY_THRESHOLD: 異常検出閾値（標準偏差の倍数、デフォルト: 3.0）

Note:
    Glue テーブルの LOCATION は S3 AP Alias を使用する。
    Athena クエリ結果のみ標準 S3 バケットに出力する（Athena の制約）。
"""

from __future__ import annotations

import json
import logging
import os
import time

import boto3

from shared.exceptions import lambda_error_handler

logger = logging.getLogger(__name__)


# 異常検出 Athena SQL クエリ定義
QUERIES = {
    "sensor_anomalies": """
        SELECT sensor_id, timestamp, value, metric_name
        FROM "{database}"."{table}"
        WHERE ABS(value - (
            SELECT AVG(value) FROM "{database}"."{table}" AS sub
            WHERE sub.metric_name = "{table}".metric_name
        )) > {threshold} * (
            SELECT STDDEV(value) FROM "{database}"."{table}" AS sub
            WHERE sub.metric_name = "{table}".metric_name
        )
        ORDER BY timestamp DESC
        LIMIT 1000
    """,
    "high_value_readings": """
        SELECT sensor_id, timestamp, value, metric_name
        FROM "{database}"."{table}"
        WHERE value > (
            SELECT AVG(value) + {threshold} * STDDEV(value)
            FROM "{database}"."{table}" AS sub
            WHERE sub.metric_name = "{table}".metric_name
        )
        ORDER BY value DESC
        LIMIT 500
    """,
}


def _ensure_glue_table(
    glue_client, database: str, table: str, s3_location: str
) -> None:
    """Glue Data Catalog テーブルを作成/更新する

    Args:
        glue_client: boto3 Glue クライアント
        database: Glue データベース名
        table: Glue テーブル名
        s3_location: Parquet データの S3 ロケーション
    """
    table_input = {
        "Name": table,
        "StorageDescriptor": {
            "Columns": [
                {"Name": "sensor_id", "Type": "string"},
                {"Name": "timestamp", "Type": "string"},
                {"Name": "value", "Type": "double"},
                {"Name": "metric_name", "Type": "string"},
                {"Name": "unit", "Type": "string"},
            ],
            "Location": s3_location,
            "InputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat",
            "OutputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat",
            "SerdeInfo": {
                "SerializationLibrary": "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe",
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
        dict: クエリ結果 (status, rows, column_info)
    """
    response = athena_client.start_query_execution(
        QueryString=query,
        QueryExecutionContext={"Database": database},
        WorkGroup=workgroup,
        ResultConfiguration={"OutputLocation": output_location},
    )
    query_execution_id = response["QueryExecutionId"]

    # クエリ完了を待機
    while True:
        status = athena_client.get_query_execution(
            QueryExecutionId=query_execution_id,
        )
        state = status["QueryExecution"]["Status"]["State"]
        if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(2)

    if state != "SUCCEEDED":
        reason = status["QueryExecution"]["Status"].get(
            "StateChangeReason", "Unknown"
        )
        logger.error("Athena query failed: %s - %s", state, reason)
        return {"status": state, "reason": reason, "rows": []}

    # 結果取得
    results = athena_client.get_query_results(
        QueryExecutionId=query_execution_id,
    )

    rows = []
    result_set = results.get("ResultSet", {})
    column_info = result_set.get("ResultSetMetadata", {}).get("ColumnInfo", [])
    data_rows = result_set.get("Rows", [])

    # 最初の行はヘッダー
    for row in data_rows[1:]:
        row_data = {}
        for i, col in enumerate(column_info):
            value = row["Data"][i].get("VarCharValue", "")
            row_data[col["Name"]] = value
        rows.append(row_data)

    return {"status": "SUCCEEDED", "rows": rows, "column_info": column_info}


@lambda_error_handler
def handler(event, context):
    """Athena Analysis Lambda

    Glue Data Catalog テーブルを作成/更新し、Athena SQL クエリを実行して
    異常センサー値を検出する。

    Returns:
        dict: query_results (各クエリの結果), execution_id
    """
    output_ap = os.environ["S3_ACCESS_POINT_OUTPUT"]
    athena_results_bucket = os.environ["ATHENA_RESULTS_BUCKET"]
    database = os.environ["GLUE_DATABASE"]
    table = os.environ["GLUE_TABLE"]
    workgroup = os.environ["ATHENA_WORKGROUP"]
    threshold = float(os.environ.get("ANOMALY_THRESHOLD", "3.0"))

    # Glue テーブル LOCATION は S3 AP Alias を使用
    s3_location = f"s3://{output_ap}/parquet/"
    # Athena クエリ結果のみ標準 S3 バケットに出力（Athena の制約）
    output_location = f"s3://{athena_results_bucket}/athena-results/"

    logger.info(
        "Manufacturing Athena Analysis started: "
        "database=%s, table=%s, workgroup=%s, threshold=%.1f",
        database,
        table,
        workgroup,
        threshold,
    )

    # Glue テーブル作成/更新
    glue_client = boto3.client("glue")
    _ensure_glue_table(glue_client, database, table, s3_location)

    # Athena クエリ実行
    athena_client = boto3.client("athena")
    query_results = {}

    for query_name, query_template in QUERIES.items():
        query = query_template.format(
            database=database,
            table=table,
            threshold=threshold,
        )
        logger.info("Executing Athena query: %s", query_name)

        result = _execute_athena_query(
            athena_client=athena_client,
            query=query,
            database=database,
            workgroup=workgroup,
            output_location=output_location,
        )
        query_results[query_name] = result

        logger.info(
            "Query %s completed: status=%s, rows=%d",
            query_name,
            result["status"],
            len(result.get("rows", [])),
        )

    logger.info(
        "Manufacturing Athena Analysis completed: %d queries executed",
        len(query_results),
    )

    return {
        "query_results": query_results,
        "execution_id": context.aws_request_id,
    }
