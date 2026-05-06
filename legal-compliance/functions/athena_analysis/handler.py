"""法務・コンプライアンス Athena Analysis Lambda ハンドラ

Glue Data Catalog テーブルを作成/更新し、Athena SQL クエリを実行して
コンプライアンス違反を検出する。

検出対象:
- 過剰権限共有 (Everyone/Full Control)
- 陳腐化アクセスエントリ (90日以上未変更)
- ポリシー違反 (特定 SID パターン)

Environment Variables:
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias (ACL データの LOCATION 用)
    ATHENA_RESULTS_BUCKET: Athena クエリ結果の S3 バケット名
    GLUE_DATABASE: Glue Data Catalog データベース名
    GLUE_TABLE: Glue Data Catalog テーブル名
    ATHENA_WORKGROUP: Athena ワークグループ名

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
from shared.observability import xray_subsegment, EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)


# Athena SQL クエリ定義
QUERIES = {
    "overly_permissive_shares": """
        SELECT object_key, volume_uuid, security_style, acl_entry
        FROM "{database}"."{table}"
        CROSS JOIN UNNEST(acls) AS t(acl_entry)
        WHERE acl_entry.sid LIKE '%S-1-1-0%'
          AND acl_entry.permissions LIKE '%FULL%'
    """,
    "stale_access_entries": """
        SELECT object_key, volume_uuid, collected_at
        FROM "{database}"."{table}"
        WHERE date_diff('day',
              from_iso8601_timestamp(collected_at),
              current_timestamp) > 90
    """,
    "policy_violations": """
        SELECT object_key, volume_uuid, security_style, acl_entry
        FROM "{database}"."{table}"
        CROSS JOIN UNNEST(acls) AS t(acl_entry)
        WHERE acl_entry.sid LIKE 'S-1-5-21-%'
          AND acl_entry.type = 'ALLOWED'
          AND acl_entry.permissions LIKE '%FULL%'
    """,
}


def _ensure_glue_table(glue_client, database: str, table: str, s3_location: str) -> None:
    """Glue Data Catalog テーブルを作成/更新する

    Args:
        glue_client: boto3 Glue クライアント
        database: Glue データベース名
        table: Glue テーブル名
        s3_location: ACL データの S3 ロケーション
    """
    table_input = {
        "Name": table,
        "StorageDescriptor": {
            "Columns": [
                {"Name": "object_key", "Type": "string"},
                {"Name": "volume_uuid", "Type": "string"},
                {"Name": "security_style", "Type": "string"},
                {"Name": "acls", "Type": "array<struct<sid:string,type:string,permissions:string>>"},
                {"Name": "collected_at", "Type": "string"},
            ],
            "Location": s3_location,
            "InputFormat": "org.apache.hadoop.mapred.TextInputFormat",
            "OutputFormat": "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat",
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
        dict: クエリ結果 (rows, column_info)
    """
    with xray_subsegment(

        name="athena_startqueryexecution",

        annotations={"service_name": "athena", "operation": "StartQueryExecution", "use_case": "legal-compliance"},

    ):

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
        reason = status["QueryExecution"]["Status"].get("StateChangeReason", "Unknown")
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


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """Athena Analysis Lambda

    Glue Data Catalog テーブルを作成/更新し、定義済み Athena SQL クエリを
    実行してコンプライアンス違反を検出する。

    Returns:
        dict: query_results (各クエリの結果)
    """
    output_ap = os.environ["S3_ACCESS_POINT_OUTPUT"]
    athena_results_bucket = os.environ["ATHENA_RESULTS_BUCKET"]
    database = os.environ["GLUE_DATABASE"]
    table = os.environ["GLUE_TABLE"]
    workgroup = os.environ["ATHENA_WORKGROUP"]

    # Glue テーブル LOCATION は S3 AP Alias を使用
    s3_location = f"s3://{output_ap}/acl-data/"
    # Athena クエリ結果のみ標準 S3 バケットに出力（Athena の制約）
    output_location = f"s3://{athena_results_bucket}/athena-results/"

    logger.info(
        "Athena Analysis started: database=%s, table=%s, workgroup=%s",
        database,
        table,
        workgroup,
    )

    # Glue テーブル作成/更新
    glue_client = boto3.client("glue")
    _ensure_glue_table(glue_client, database, table, s3_location)

    # Athena クエリ実行
    athena_client = boto3.client("athena")
    query_results = {}

    for query_name, query_template in QUERIES.items():
        query = query_template.format(database=database, table=table)
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

    logger.info("Athena Analysis completed: %d queries executed", len(query_results))


    # EMF メトリクス出力
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="athena_analysis")
    metrics.set_dimension("UseCase", os.environ.get("USE_CASE", "legal-compliance"))
    metrics.put_metric("FilesProcessed", 1.0, "Count")
    metrics.flush()

    return {
        "query_results": query_results,
        "execution_id": context.aws_request_id,
    }
