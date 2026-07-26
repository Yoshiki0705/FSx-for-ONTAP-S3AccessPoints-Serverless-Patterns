import os
import json
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
        return {"columns": [], "rows": [], "status": "ERROR", "error": str(e)}
