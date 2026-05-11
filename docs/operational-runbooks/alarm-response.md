# Alarm Response Runbook

**Scope**: Responding to Phase 8 Theme N CloudWatch Alarms across all UCs.

---

## Alarm naming convention

```
fsxn-<usecase>-<resource>-<metric>-alarm
```

Examples:
- `fsxn-legal-compliance-sfn-failed-alarm`
- `fsxn-legal-compliance-lambda-errors-alarm`
- `fsxn-legal-compliance-dynamodb-write-throttles-alarm`

## General triage flow

1. Acknowledge the alarm in CloudWatch console.
2. Identify the resource and metric from the alarm name.
3. Jump to the per-alarm section below.
4. If the root cause is unclear after the dedicated section, follow the
   "Generic deep-dive" at the end of this runbook.

---

## Step Functions ExecutionsFailed

**Alarm**: `fsxn-<usecase>-sfn-failed-alarm`

**Meaning**: One or more Step Functions executions entered FAILED,
TIMED_OUT, or ABORTED state in the last 5 minutes.

**Investigation**:

1. Open Step Functions console → State machine → Executions tab.
2. Filter by status = Failed / Timed out / Aborted in the alarm window.
3. Click the failing execution and inspect the Graph view.
4. Locate the red failed state. Click it for Input / Output / Exception.
5. Cross-reference the `error` field:
   - `Lambda.Unknown` → open the failed Lambda's CloudWatch log group and
     search the execution's correlation ID.
   - `States.TaskFailed` → the task's own error message explains the cause.
   - `States.Timeout` → raise the task-level or execution-level timeout.

**Common root causes**:

| Symptom | Root cause | Remediation |
|---------|-----------|-------------|
| `AccessDenied` on S3 PutObject | Discovery Lambda IAM missing full ARN form | Re-apply IAM fix (see `deployment-troubleshooting.md` Failure Mode 6) |
| `ResourceNotFoundException` on Secrets Manager | Secret not provisioned | Create per `deployment-troubleshooting.md` Failure Mode 5 |
| `TaskTimedOut` on Bedrock call | Cold model or throttling | Retry via SFN rerun runbook |
| `Lambda.TooManyRequestsException` | Concurrency limit hit | Request burst limit increase or add reserved concurrency |

## Lambda Errors

**Alarm**: `fsxn-<usecase>-lambda-<function>-errors-alarm`

**Meaning**: 3 or more Lambda errors in the last 5 minutes.

**Investigation**:

1. CloudWatch Logs Insights query:
   ```
   fields @timestamp, @message, @requestId
   | filter @message like /ERROR/ or level == "ERROR"
   | sort @timestamp desc
   | limit 50
   ```
2. Group errors by `errorType`. If one `errorType` dominates, investigate
   that class first.
3. If errors correlate with a specific input (e.g., `Key=...`), that
   input likely triggers an unhandled edge case.

**Common root causes**:
- **Unhandled exception** in handler — add defensive code path + unit test.
- **Resource not ready** (DynamoDB table still creating on first invoke) —
  add retry in `shared/exceptions.py::lambda_error_handler`.
- **Memory exhaustion** on large files — raise Lambda memory or stream via
  `OutputWriter.put_stream()`.

## Lambda Throttles

**Alarm**: `fsxn-<usecase>-lambda-<function>-throttles-alarm`

**Meaning**: 1+ throttling events in 5 minutes.

**Investigation**:

1. Check `Reserved concurrency` on the Lambda function.
2. Check account-level `ConcurrentExecutions` quota via Service Quotas.
3. Look for a fan-out burst (Map state with many parallel iterations) in
   the Step Functions execution.

**Remediation**:
- Short-term: raise reserved concurrency for this function.
- Medium-term: add `MaxConcurrency` on the Map state to cap burst rate.
- Long-term: request account-level quota increase.

## Lambda Duration p99 near timeout

**Alarm**: `fsxn-<usecase>-lambda-<function>-p99duration-alarm`

**Meaning**: p99 invocation duration >= 80% of the configured timeout.

**Investigation**:

1. Open CloudWatch Logs Insights on the function:
   ```
   filter @type = "REPORT"
   | stats avg(@duration), max(@duration), pct(@duration, 99) by bin(5m)
   ```
2. Correlate with X-Ray segments if enabled. Look at the slowest
   sub-segment (Bedrock call, Textract call, etc.).

**Remediation**:
- External service slowness → retry with exponential backoff (already in
  `shared/cross_region_client.py`).
- Cold start → add Provisioned Concurrency for user-facing paths.
- Algorithmic slowness → profile locally with the same input.

## DynamoDB ThrottleEvents

**Alarm**: `fsxn-<usecase>-dynamodb-<table>-throttles-alarm`

**Meaning**: DynamoDB rejected 1+ requests in 5 minutes.

**Investigation**:

1. CloudWatch → DynamoDB → Table metrics → `ThrottledRequests`.
2. Check if the table is in `PROVISIONED` or `ON_DEMAND` mode.
3. For `PROVISIONED`: inspect `ProvisionedReadCapacityUnits` vs
   `ConsumedReadCapacityUnits` on a 1-minute interval.
4. For `ON_DEMAND`: throttling usually indicates hot-partition.
5. Inspect CloudWatch Contributor Insights (if enabled) to find the hot
   partition key.

**Remediation**:
- Switch table to `ON_DEMAND` billing mode if currently `PROVISIONED` and
  traffic is bursty.
- Add a random suffix to partition keys to distribute writes.
- Introduce application-level throttling or SQS buffering.

---

## Generic deep-dive

If the per-alarm section doesn't lead to root cause:

1. Widen the CloudWatch time range to cover deployment events —
   a recent stack update often correlates with new error classes.
2. Check the EventBridge rule for Step Functions state change events. The
   SNS topic subscription contains a direct link to the failed execution.
3. Ask CloudWatch Logs Insights across all Lambda log groups for the UC:
   ```
   fields @timestamp, @logStream, @message
   | filter @message like /EXCEPTION|ERROR|Traceback/
   | sort @timestamp desc
   | limit 100
   ```
4. If still unclear, re-run the workflow with the same input (see
   `sfn-rerun.md`) and capture X-Ray traces with full sampling.

## Escalation

If the alarm persists after 30 minutes of investigation:
- Page the on-call engineer via the SNS topic subscription.
- Open an internal incident ticket with the alarm ARN and execution ARN.
- If the root cause involves an AWS service fault, open an AWS Support
  case with the service + operation + X-Ray trace ID.
