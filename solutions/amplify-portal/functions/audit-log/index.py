import os
import json
import time
import boto3

ATHENA_DATABASE = os.environ.get("ATHENA_DATABASE", "cloudtrail_logs")
ATHENA_TABLE = os.environ.get("ATHENA_TABLE", "cloudtrail_s3_events")
ATHENA_OUTPUT = os.environ.get("ATHENA_OUTPUT_LOCATION", "")
S3AP_ALIAS = os.environ.get("S3_AP_ALIAS", "")
REGION = os.environ.get("AWS_REGION", "ap-northeast-1")


def handler(event, context):
    """Query CloudTrail S3 data events for file access audit trail.

    Runs Athena SQL against a pre-configured CloudTrail table to retrieve
    file access events (GetObject, PutObject, DeleteObject) filtered by
    file path prefix, date range, and event type.

    Pre-requisites:
    - CloudTrail trail with S3 data events enabled for the S3 AP ARN
    - Athena table created over the CloudTrail S3 logs (via CREATE TABLE or Glue Crawler)
    - Athena output S3 bucket configured
    """
    file_key_prefix = event.get("fileKeyPrefix", "")
    start_date = event.get("startDate", "")
    end_date = event.get("endDate", "")
    event_type = event.get("eventType", "ALL")
    max_results = min(event.get("maxResults", 50), 200)

    if not ATHENA_OUTPUT:
        return {
            "events": [],
            "queryExecutionId": "",
            "error": "Audit log not configured (set ATHENA_DATABASE, ATHENA_TABLE, ATHENA_OUTPUT_LOCATION)",
        }

    # Build WHERE clause
    conditions = []

    if event_type == "ALL":
        conditions.append("eventsource = 's3.amazonaws.com'")
        conditions.append("eventname IN ('GetObject', 'PutObject', 'DeleteObject', 'ListBucket', 'PutObjectLockConfiguration', 'PutBucketObjectLockConfiguration', 'PutObjectRetention')")
    elif event_type == "READ":
        conditions.append("eventsource = 's3.amazonaws.com'")
        conditions.append("eventname IN ('GetObject', 'ListBucket')")
    elif event_type == "WRITE":
        conditions.append("eventsource = 's3.amazonaws.com'")
        conditions.append("eventname IN ('PutObject', 'DeleteObject')")
    elif event_type == "LOCK":
        conditions.append("eventsource = 's3.amazonaws.com'")
        conditions.append("eventname IN ('PutObjectLockConfiguration', 'PutBucketObjectLockConfiguration', 'PutObjectRetention', 'PutObjectLegalHold')")

    if S3AP_ALIAS:
        conditions.append(f"requestparameters LIKE '%{S3AP_ALIAS}%'")

    if file_key_prefix:
        conditions.append(f"requestparameters LIKE '%{file_key_prefix}%'")

    if start_date:
        conditions.append(f"eventtime >= '{start_date}'")
    if end_date:
        conditions.append(f"eventtime <= '{end_date}'")

    where_clause = " AND ".join(conditions)

    sql = f"""
    SELECT
        eventtime,
        eventname,
        useridentity.arn AS user_arn,
        useridentity.principalid AS principal_id,
        sourceipaddress,
        json_extract_scalar(requestparameters, '$.key') AS file_key,
        json_extract_scalar(requestparameters, '$.bucketName') AS bucket_name,
        errorcode,
        errormessage
    FROM "{ATHENA_DATABASE}"."{ATHENA_TABLE}"
    WHERE {where_clause}
    ORDER BY eventtime DESC
    LIMIT {max_results}
    """

    try:
        athena = boto3.client("athena", region_name=REGION)

        # Start query
        start_resp = athena.start_query_execution(
            QueryString=sql,
            QueryExecutionContext={"Database": ATHENA_DATABASE},
            ResultConfiguration={"OutputLocation": ATHENA_OUTPUT},
        )
        query_id = start_resp["QueryExecutionId"]

        # Poll for completion (max 30s)
        for _ in range(30):
            status_resp = athena.get_query_execution(QueryExecutionId=query_id)
            state = status_resp["QueryExecution"]["Status"]["State"]
            if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
                break
            time.sleep(1)

        if state != "SUCCEEDED":
            error_msg = status_resp["QueryExecution"]["Status"].get("StateChangeReason", state)
            return {
                "events": [],
                "queryExecutionId": query_id,
                "error": f"Query {state}: {error_msg}",
            }

        # Get results
        results_resp = athena.get_query_results(
            QueryExecutionId=query_id, MaxResults=max_results + 1
        )

        rows = results_resp["ResultSet"]["Rows"]
        if len(rows) <= 1:
            return {"events": [], "queryExecutionId": query_id, "error": None}

        # Parse header + data rows
        headers = [col["VarCharValue"] for col in rows[0]["Data"]]
        events = []
        for row in rows[1:]:
            values = [col.get("VarCharValue", "") for col in row["Data"]]
            event_dict = dict(zip(headers, values))
            events.append({
                "timestamp": event_dict.get("eventtime", ""),
                "action": event_dict.get("eventname", ""),
                "userArn": event_dict.get("user_arn", ""),
                "principalId": event_dict.get("principal_id", ""),
                "sourceIp": event_dict.get("sourceipaddress", ""),
                "fileKey": event_dict.get("file_key", ""),
                "bucketName": event_dict.get("bucket_name", ""),
                "errorCode": event_dict.get("errorcode", ""),
                "errorMessage": event_dict.get("errormessage", ""),
            })

        return {
            "events": events,
            "queryExecutionId": query_id,
            "error": None,
        }

    except Exception as e:
        print(f"Audit log query error: {e}")
        return {
            "events": [],
            "queryExecutionId": "",
            "error": str(e),
        }
