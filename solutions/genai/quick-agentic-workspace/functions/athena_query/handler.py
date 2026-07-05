"""UC30 Amazon Quick Agentic Workspace — Athena Query (BI 基盤)

Amazon Quick Sight（BI）が参照する構造化データを、FSx for ONTAP S3 Access Point 上の
CSV から Glue/Athena で問い合わせる。Quick Sight のデータセット作成や、エージェントが
構造化データに基づく回答を返すための分析バックエンド。

event 例:
  {"sql": "SELECT role, SUM(amount) FROM pipeline GROUP BY role"}
  {"query_name": "sales_pipeline_total"}
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

athena_client = boto3.client("athena")

# 代表的な定義済みクエリ（query_name で指定可能）
NAMED_QUERIES = {
    "sales_pipeline_total": (
        "SELECT stage, COUNT(*) AS deals, SUM(amount_jpy) AS total_jpy "
        "FROM sales_pipeline GROUP BY stage ORDER BY total_jpy DESC"
    ),
    "it_incident_summary": (
        "SELECT severity, COUNT(*) AS incidents, AVG(mttr_minutes) AS avg_mttr "
        "FROM it_incidents GROUP BY severity ORDER BY severity"
    ),
}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Athena クエリを実行し結果行を返す。

    セキュリティ: 任意 SQL（`sql`）は既定で**無効**（`ALLOW_RAW_SQL=true` で明示的に有効化した
    管理用途のみ）。通常は許可リスト `NAMED_QUERIES`（`query_name`）のみを実行する。
    ロール別のデータ境界は Lake Formation（LF-TBAC）で強制する前提（テンプレート外の付与が必要）。
    """
    database = os.environ.get("ATHENA_DATABASE", "")
    workgroup = os.environ.get("ATHENA_WORKGROUP", "primary")
    output_location = os.environ.get("ATHENA_OUTPUT_LOCATION", "")
    allow_raw_sql = os.environ.get("ALLOW_RAW_SQL", "false").lower() == "true"
    now = int(datetime.now(timezone.utc).timestamp())

    raw_sql = event.get("sql")
    query_name = event.get("query_name", "")

    # 既定: 任意 SQL は拒否。許可リストのみ実行。
    if raw_sql and not allow_raw_sql:
        logger.warning("Raw SQL rejected (ALLOW_RAW_SQL is false); use query_name allowlist")
        return {
            "status": "error",
            "error": "raw sql is disabled; use a named query (query_name)",
            "allowed_queries": sorted(NAMED_QUERIES.keys()),
            "timestamp": now,
        }

    sql = (raw_sql if allow_raw_sql and raw_sql else None) or NAMED_QUERIES.get(query_name, "")
    if not (sql and database):
        return {
            "status": "error",
            "error": "ATHENA_DATABASE and (known query_name or enabled raw sql) are required",
            "allowed_queries": sorted(NAMED_QUERIES.keys()),
            "timestamp": now,
        }

    try:
        start = athena_client.start_query_execution(
            QueryString=sql,
            QueryExecutionContext={"Database": database},
            WorkGroup=workgroup,
            ResultConfiguration={"OutputLocation": output_location} if output_location else {},
        )
        qid = start["QueryExecutionId"]

        state = "RUNNING"
        for _ in range(30):
            exec_resp = athena_client.get_query_execution(QueryExecutionId=qid)
            state = exec_resp["QueryExecution"]["Status"]["State"]
            if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
                break
            time.sleep(2)

        if state != "SUCCEEDED":
            return {"status": "error", "query_state": state, "query_id": qid, "timestamp": now}

        results = athena_client.get_query_results(QueryExecutionId=qid, MaxResults=100)
        rows = [[col.get("VarCharValue", "") for col in row["Data"]] for row in results["ResultSet"]["Rows"]]
        header = rows[0] if rows else []
        data_rows = rows[1:] if len(rows) > 1 else []

        logger.info("Athena query %s SUCCEEDED, %d rows", qid, len(data_rows))
        return {
            "status": "completed",
            "query_id": qid,
            "columns": header,
            "rows": data_rows,
            "row_count": len(data_rows),
            "timestamp": now,
        }

    except Exception as e:  # noqa: BLE001 - 内部詳細は漏らさずサーバー側にのみ記録
        logger.error("athena_query failed: %s", str(e))
        return {"status": "error", "error": "internal error", "timestamp": now}
