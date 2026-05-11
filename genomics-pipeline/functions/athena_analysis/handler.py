"""ゲノミクス / バイオインフォマティクス Athena 分析 Lambda ハンドラ

Athena SQL クエリを実行して品質閾値未満のサンプルを特定する。
Glue Data Catalog テーブルを作成/更新し、QC メトリクスとバリアント統計を
横断的に分析する。

分析内容:
    - 品質スコアが閾値未満のサンプル特定
    - GC 含有率の異常値検出
    - バリアント統計のサマリー集計

Environment Variables:
    GLUE_DATABASE: Glue データベース名
    GLUE_TABLE: Glue テーブル名
    ATHENA_WORKGROUP: Athena ワークグループ名
    OUTPUT_BUCKET: S3 出力バケット名
    QUALITY_THRESHOLD: 品質閾値 (デフォルト: 20.0)
"""

from __future__ import annotations

import logging
import os
import time

import boto3

from pathlib import PurePosixPath

from shared.exceptions import lambda_error_handler
from shared.observability import xray_subsegment, EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)

DEFAULT_QUALITY_THRESHOLD = 20.0

# Athena SQL クエリ定義
QUERIES = {
    "below_threshold_samples": """
        SELECT file_key,
               json_extract_scalar(quality_metrics, '$.average_quality_score') AS avg_quality,
               json_extract_scalar(quality_metrics, '$.gc_content_percentage') AS gc_content,
               json_extract_scalar(quality_metrics, '$.total_reads') AS total_reads
        FROM "{database}"."{table}"
        WHERE CAST(json_extract_scalar(quality_metrics, '$.average_quality_score') AS DOUBLE) < {threshold}
        ORDER BY CAST(json_extract_scalar(quality_metrics, '$.average_quality_score') AS DOUBLE) ASC
    """,
    "quality_summary": """
        SELECT COUNT(*) AS total_samples,
               AVG(CAST(json_extract_scalar(quality_metrics, '$.average_quality_score') AS DOUBLE)) AS avg_quality,
               MIN(CAST(json_extract_scalar(quality_metrics, '$.average_quality_score') AS DOUBLE)) AS min_quality,
               MAX(CAST(json_extract_scalar(quality_metrics, '$.average_quality_score') AS DOUBLE)) AS max_quality,
               AVG(CAST(json_extract_scalar(quality_metrics, '$.gc_content_percentage') AS DOUBLE)) AS avg_gc_content
        FROM "{database}"."{table}"
    """,
    "gc_content_outliers": """
        SELECT file_key,
               json_extract_scalar(quality_metrics, '$.gc_content_percentage') AS gc_content
        FROM "{database}"."{table}"
        WHERE CAST(json_extract_scalar(quality_metrics, '$.gc_content_percentage') AS DOUBLE) < 30.0
           OR CAST(json_extract_scalar(quality_metrics, '$.gc_content_percentage') AS DOUBLE) > 70.0
        ORDER BY CAST(json_extract_scalar(quality_metrics, '$.gc_content_percentage') AS DOUBLE) ASC
    """,
}


def _ensure_glue_table(
    glue_client,
    database: str,
    table: str,
    s3_location: str,
) -> None:
    """Glue Data Catalog テーブルを作成/更新する

    QC メトリクス JSON を格納するテーブルを定義する。
    テーブルが既に存在する場合はスキップする。

    Args:
        glue_client: boto3 Glue クライアント
        database: Glue データベース名
        table: Glue テーブル名
        s3_location: テーブルデータの S3 ロケーション
    """
    try:
        glue_client.get_table(DatabaseName=database, Name=table)
        logger.info("Glue table %s.%s already exists", database, table)
        return
    except glue_client.exceptions.EntityNotFoundException:
        pass

    table_input = {
        "Name": table,
        "Description": "Genomics QC metrics from FASTQ quality analysis",
        "StorageDescriptor": {
            "Columns": [
                {"Name": "file_key", "Type": "string"},
                {"Name": "quality_metrics", "Type": "string"},
                {"Name": "sample_size", "Type": "int"},
                {"Name": "extracted_at", "Type": "string"},
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

        annotations={"service_name": "athena", "operation": "StartQueryExecution", "use_case": "genomics-pipeline"},

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


def _safe_float(value: str) -> float:
    """文字列を安全に float に変換する"""
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def _safe_int(value: str) -> int:
    """文字列を安全に int に変換する"""
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return 0


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """ゲノミクス / バイオインフォマティクス Athena 分析 Lambda

    Athena SQL クエリを実行して品質閾値未満のサンプルを特定し、
    QC メトリクスのサマリー統計を集計する。

    Args:
        event: QC / バリアント集計結果
            {
                "qc_results": [...],
                "variant_stats": [...],
                "metadata_prefix": "qc/"
            }

    Returns:
        dict: status, below_threshold_samples, quality_summary,
              gc_content_outliers, query_execution_id
    """
    database = os.environ["GLUE_DATABASE"]
    table = os.environ["GLUE_TABLE"]
    workgroup = os.environ["ATHENA_WORKGROUP"]
    output_bucket = os.environ["OUTPUT_BUCKET"]
    quality_threshold = float(
        os.environ.get("QUALITY_THRESHOLD", DEFAULT_QUALITY_THRESHOLD)
    )

    # Glue テーブルの S3 ロケーション
    s3_location = f"s3://{output_bucket}/qc/"
    # Athena クエリ結果の出力先
    output_location = f"s3://{output_bucket}/athena-results/"

    logger.info(
        "Athena Analysis started: database=%s, table=%s, threshold=%.1f",
        database,
        table,
        quality_threshold,
    )

    # Glue テーブル作成/更新
    glue_client = boto3.client("glue")
    _ensure_glue_table(glue_client, database, table, s3_location)

    # Athena クエリ実行
    athena_client = boto3.client("athena")
    analysis_results = {
        "below_threshold_samples": [],
        "quality_summary": {},
        "gc_content_outliers": [],
    }
    last_query_execution_id = ""

    for query_name, query_template in QUERIES.items():
        query = query_template.format(
            database=database,
            table=table,
            threshold=quality_threshold,
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

        if query_name == "below_threshold_samples":
            analysis_results["below_threshold_samples"] = [
                {
                    "file_key": row.get("file_key", ""),
                    "average_quality_score": _safe_float(
                        row.get("avg_quality", "0")
                    ),
                    "gc_content_percentage": _safe_float(
                        row.get("gc_content", "0")
                    ),
                    "total_reads": _safe_int(row.get("total_reads", "0")),
                }
                for row in rows
            ]

        elif query_name == "quality_summary" and rows:
            row = rows[0]
            analysis_results["quality_summary"] = {
                "total_samples": _safe_int(row.get("total_samples", "0")),
                "average_quality_score": round(
                    _safe_float(row.get("avg_quality", "0")), 1
                ),
                "min_quality_score": round(
                    _safe_float(row.get("min_quality", "0")), 1
                ),
                "max_quality_score": round(
                    _safe_float(row.get("max_quality", "0")), 1
                ),
                "average_gc_content": round(
                    _safe_float(row.get("avg_gc_content", "0")), 1
                ),
            }

        elif query_name == "gc_content_outliers":
            analysis_results["gc_content_outliers"] = [
                {
                    "file_key": row.get("file_key", ""),
                    "gc_content_percentage": _safe_float(
                        row.get("gc_content", "0")
                    ),
                }
                for row in rows
            ]

        logger.info(
            "Query %s completed: %d rows", query_name, len(rows)
        )

    # 閾値未満サンプル名の抽出（サマリー用）
    below_threshold_sample_names = [
        PurePosixPath(s["file_key"]).stem
        for s in analysis_results["below_threshold_samples"]
    ]

    logger.info(
        "Athena Analysis completed: below_threshold=%d, outliers=%d",
        len(analysis_results["below_threshold_samples"]),
        len(analysis_results["gc_content_outliers"]),
    )


    # EMF メトリクス出力
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="athena_analysis")
    metrics.set_dimension("UseCase", os.environ.get("USE_CASE", "genomics-pipeline"))
    metrics.put_metric("FilesProcessed", 1.0, "Count")
    metrics.flush()

    return {
        "status": "SUCCESS",
        "below_threshold_samples": analysis_results["below_threshold_samples"],
        "below_threshold_sample_names": below_threshold_sample_names,
        "quality_summary": analysis_results["quality_summary"],
        "gc_content_outliers": analysis_results["gc_content_outliers"],
        "quality_threshold": quality_threshold,
        "query_execution_id": last_query_execution_id,
    }
