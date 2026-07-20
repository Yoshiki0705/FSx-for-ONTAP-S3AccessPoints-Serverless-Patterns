"""Step Functions → DynamoDB Job Status Updater (E-3)

Receives EventBridge events for Step Functions execution status changes
and updates the JobExecution DynamoDB table. Since JobExecution is an
Amplify model with real-time subscriptions enabled, the DynamoDB update
automatically triggers onUpdate subscriptions — pushing status changes
to connected portal clients via WebSocket.

This eliminates the need for 5-second polling in the Results tab.

EventBridge rule:
    source: ["aws.states"]
    detail-type: ["Step Functions Execution Status Change"]
    detail:
      status: ["SUCCEEDED", "FAILED", "TIMED_OUT", "ABORTED"]

Environment variables:
    JOB_EXECUTION_TABLE_NAME: Amplify-managed DynamoDB table for JobExecution model
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

TABLE_NAME = os.environ.get("JOB_EXECUTION_TABLE_NAME", "")


def handler(event: dict, context) -> dict:
    """Update JobExecution record when Step Functions execution completes.

    EventBridge detail contains:
    - executionArn: ARN of the completed execution
    - status: SUCCEEDED | FAILED | TIMED_OUT | ABORTED
    - startDate / stopDate: epoch milliseconds
    - input / output: JSON strings (for SUCCEEDED)
    """
    detail = event.get("detail", {})
    execution_arn = detail.get("executionArn", "")
    status = detail.get("status", "")
    stop_date = detail.get("stopDate")

    if not execution_arn or not status:
        logger.warning("Missing executionArn or status in event")
        return {"statusCode": 400}

    if not TABLE_NAME:
        logger.error("JOB_EXECUTION_TABLE_NAME not configured")
        return {"statusCode": 500}

    logger.info(f"Updating job: {execution_arn} → {status}")

    try:
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table(TABLE_NAME)

        # Find the record by executionArn (GSI query or scan)
        # Amplify models use 'id' as partition key, but we store executionArn
        # Use a scan with filter (acceptable for low-volume job updates)
        response = table.scan(
            FilterExpression="executionArn = :arn",
            ExpressionAttributeValues={":arn": execution_arn},
            Limit=1,
        )

        items = response.get("Items", [])
        if not items:
            logger.info(f"No JobExecution record found for {execution_arn} — may be from a different source")
            return {"statusCode": 200, "body": "No matching record"}

        item = items[0]
        record_id = item["id"]

        # Build update expression
        update_expr = "SET #status = :status, updatedAt = :now"
        expr_values: dict = {
            ":status": status,
            ":now": datetime.now(timezone.utc).isoformat(),
        }
        expr_names = {"#status": "status"}

        if stop_date:
            # Convert epoch ms to ISO string
            stop_iso = datetime.fromtimestamp(stop_date / 1000, tz=timezone.utc).isoformat()
            update_expr += ", stopDate = :stopDate"
            expr_values[":stopDate"] = stop_iso

        # For SUCCEEDED, try to include output
        if status == "SUCCEEDED" and detail.get("output"):
            try:
                output_data = json.loads(detail["output"])
                update_expr += ", output = :output"
                expr_values[":output"] = output_data
            except (json.JSONDecodeError, TypeError):
                pass

        table.update_item(
            Key={"id": record_id},
            UpdateExpression=update_expr,
            ExpressionAttributeValues=expr_values,
            ExpressionAttributeNames=expr_names,
        )

        logger.info(f"Updated {record_id}: status={status}")
        return {"statusCode": 200, "body": f"Updated {record_id}"}

    except Exception as e:
        logger.error(f"Failed to update job status: {e}")
        return {"statusCode": 500, "body": str(e)}
