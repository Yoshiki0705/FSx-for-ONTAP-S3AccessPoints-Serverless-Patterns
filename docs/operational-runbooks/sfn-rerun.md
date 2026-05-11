# Step Functions Re-execution Runbook

**Scope**: Safely re-running a failed Step Functions workflow after
root-causing and remediating the underlying issue.

---

## When to re-execute

Re-execute after:
- The root cause of the failure is identified and remediated.
- Any input payload corrections are complete.
- Idempotency keys (if any) have been considered.

Do NOT re-execute:
- While the alarm is still active — fix the underlying issue first.
- If the failure may have partial side effects that are not safely
  re-entrant (e.g. UC17 DynamoDB optimistic locking was broken in a
  specific commit range).

---

## Identifying the original execution

1. CloudWatch Alarms → failed alarm → View in Step Functions.
2. Or: Step Functions console → state machine → Executions → filter Failed.
3. Record the **Execution ARN**, **input payload**, and **failed state**.

```
arn:aws:states:<region>:<account>:execution:<sm-name>:<exec-id>
```

## Option A: Re-execute with identical input

Use when the failure was transient (e.g., Bedrock cold model, DynamoDB
throttle) and the original input is still valid.

```bash
# 1. Retrieve the original input payload
aws stepfunctions describe-execution \
  --execution-arn <EXECUTION_ARN> \
  --query 'input' --output text > original-input.json

# 2. Start a new execution with the same input
aws stepfunctions start-execution \
  --state-machine-arn <STATE_MACHINE_ARN> \
  --input file://original-input.json \
  --name "rerun-$(date +%Y%m%d-%H%M%S)"
```

## Option B: Redrive (Distributed Map only)

If the state machine uses a Distributed Map and only some iterations
failed, use `RedriveExecution` to restart from the failure point without
re-processing successful iterations:

```bash
aws stepfunctions redrive-execution --execution-arn <EXECUTION_ARN>
```

This is more cost-efficient for partial failures in large Map states.

## Option C: Re-execute with corrected input

Use when the original input contained invalid data (e.g., wrong S3 key
prefix, malformed JSON).

```bash
# 1. Fetch original input
aws stepfunctions describe-execution \
  --execution-arn <EXECUTION_ARN> \
  --query 'input' --output text > original-input.json

# 2. Edit locally
cp original-input.json corrected-input.json
vi corrected-input.json

# 3. Start a new execution with the corrected payload
aws stepfunctions start-execution \
  --state-machine-arn <STATE_MACHINE_ARN> \
  --input file://corrected-input.json \
  --name "rerun-corrected-$(date +%Y%m%d-%H%M%S)"
```

## Idempotency considerations per UC

| UC | Idempotent on re-run? | Notes |
|----|----------------------|-------|
| UC1 legal-compliance | ✅ | Output keys include execution id via ULID |
| UC2 financial-idp | ✅ | Textract/Comprehend outputs overwrite safely |
| UC3 manufacturing-analytics | ⚠️ | Athena query results append — review before rerun |
| UC4 media-vfx | ⚠️ | Deadline Cloud job creation has no dedup key |
| UC5 healthcare-dicom | ✅ | DICOM metadata is keyed by SOP instance UID |
| UC6 semiconductor-eda | ⚠️ | Athena query results append — review before rerun |
| UC7 genomics-pipeline | ⚠️ | Athena query results append — review before rerun |
| UC8 energy-seismic | ⚠️ | Athena query results append — review before rerun |
| UC9 autonomous-driving | ✅ | Output keys include timestamp |
| UC10 construction-bim | ✅ | Output keys include file stem + date |
| UC11 retail-catalog | ✅ | Product tags overwrite safely |
| UC12 logistics-ocr | ✅ | Output keys include file stem + date |
| UC13 education-research | ✅ | Output keys include file stem + date |
| UC14 insurance-claims | ✅ | Claims output keyed by claim ID |
| UC15 defense-satellite | ⚠️ | DynamoDB detection history appends — dedupe by detection_id |
| UC16 government-archives | ⚠️ | DynamoDB retention table updates in place; re-run is safe |
| UC17 smart-city-geospatial | ⚠️ | DynamoDB landuse history appends — dedupe by scene_id |

For ⚠️ UCs, inspect the output bucket / DynamoDB table before rerun to
confirm no stale state will cause duplicate records.

## Verification after rerun

1. Confirm the new execution reached SUCCEEDED within expected duration.
2. Compare output object counts with previous successful runs.
3. Confirm the associated CloudWatch Alarm returns to OK state.
4. Update the original incident ticket with the rerun execution ARN.

## Bulk rerun

When multiple executions failed due to a common root cause (e.g.,
IAM fix propagation), script the reruns:

```bash
aws stepfunctions list-executions \
  --state-machine-arn <SM_ARN> \
  --status-filter FAILED \
  --query 'executions[].executionArn' --output text | \
while read -r arn; do
  input=$(aws stepfunctions describe-execution \
    --execution-arn "$arn" --query 'input' --output text)
  aws stepfunctions start-execution \
    --state-machine-arn <SM_ARN> \
    --input "$input" \
    --name "bulk-rerun-$(date +%s)-$RANDOM"
  sleep 1
done
```

Note: add appropriate rate-limiting based on downstream service quotas
(Bedrock TPS, Textract TPS, etc.).
