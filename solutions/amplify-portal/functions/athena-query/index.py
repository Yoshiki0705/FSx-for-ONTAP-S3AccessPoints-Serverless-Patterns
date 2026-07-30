import os
import time
import boto3

region = os.environ.get("AWS_REGION", "ap-northeast-1")
athena = boto3.client("athena", region_name=region)

WORKGROUP = os.environ.get("ATHENA_WORKGROUP", "primary")
OUTPUT_LOCATION = os.environ.get("ATHENA_OUTPUT_LOCATION", "")

def handler(event, context):
    """Execute an Athena SQL query and return results.

    Starts query execution, polls for completion, and returns results.
    Max wait: 30 seconds (then returns execution ID for async polling).
    """
    sql = event.get("sql", "")
    database = event.get("database", "default")

    if not sql:
        return {"columns": [], "rows": [], "status": "ERROR", "error": "No SQL query provided"}

    try:
        params = {
            "QueryString": sql,
            "QueryExecutionContext": {"Database": database},
            "WorkGroup": WORKGROUP,
        }
        if OUTPUT_LOCATION:
            params["ResultConfiguration"] = {"OutputLocation": OUTPUT_LOCATION}

        response = athena.start_query_execution(**params)
        execution_id = response["QueryExecutionId"]

        # Poll for completion (max 30s)
        for _ in range(30):
            time.sleep(1)
            status_resp = athena.get_query_execution(QueryExecutionId=execution_id)
            state = status_resp["QueryExecution"]["Status"]["State"]
            if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
                break

        if state != "SUCCEEDED":
            reason = status_resp["QueryExecution"]["Status"].get("StateChangeReason", "")
            return {"columns": [], "rows": [], "status": state, "error": reason, "executionId": execution_id}

        # Get results
        results = athena.get_query_results(QueryExecutionId=execution_id, MaxResults=100)
        columns = [col["Name"] for col in results["ResultSet"]["ResultSetMetadata"]["ColumnInfo"]]
        rows = []
        for row in results["ResultSet"]["Rows"][1:]:  # Skip header
            rows.append([datum.get("VarCharValue", "") for datum in row["Data"]])

        return {"columns": columns, "rows": rows, "status": "SUCCEEDED", "error": None, "executionId": execution_id}

    except Exception as e:
        error_msg = str(e)
        # Provide user-friendly guidance for common setup issues
        if "No output location provided" in error_msg:
            return {
                "columns": [], "rows": [], "status": "SETUP_REQUIRED",
                "error": "Athena の出力先が未設定です。AWS コンソールで Athena ワークグループの「クエリ結果の場所」を設定するか、ポータルの環境変数 ATHENA_OUTPUT_LOCATION に S3 パス（例: s3://my-bucket/athena-results/）を設定してください。",
                "setupHint": "ATHENA_OUTPUT_LOCATION"
            }
        if "Database" in error_msg and "not found" in error_msg.lower():
            return {
                "columns": [], "rows": [], "status": "SETUP_REQUIRED",
                "error": f"データベース '{database}' が見つかりません。Glue Crawler でデータカタログを作成するか、データベース名を確認してください。SHOW DATABASES で利用可能なデータベースを確認できます。",
                "setupHint": "DATABASE_NOT_FOUND"
            }
        return {"columns": [], "rows": [], "status": "ERROR", "error": error_msg}
