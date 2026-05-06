---
title: "Near-Real-Time Processing, ML Inference, and Observability for FSx for ONTAP S3 Access Points — Phase 3 Architecture Patterns"
published: false
description: "Phase 3 adds near-real-time Kinesis processing, SageMaker Batch Transform with Step Functions Callback Pattern, and X-Ray/CloudWatch EMF observability across 14 FSx for ONTAP S3 Access Point patterns."
tags: aws, serverless, netapp, python
cover_image: https://raw.githubusercontent.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/main/docs/screenshots/phase3-step-functions-uc11-succeeded.png
series: "FSx for ONTAP S3 Access Points"
---

## TL;DR

This is **Phase 3** of the FSx for ONTAP S3 Access Points serverless patterns collection. Building on the [Phase 1 foundation](https://dev.to/yoshikifujiwara/fsx-for-ontap-s3-access-points-as-a-serverless-automation-boundary-ai-data-pipelines-ili) and the [14 industry patterns from Phase 2](https://dev.to/yoshikifujiwara/9-more-industry-serverless-patterns-with-fsx-for-ontap-s3-access-points-semiconductor-genomics-15e4), Phase 3 adds three cross-cutting capabilities:

- **Near-real-time processing**: Kinesis Data Streams integration for minute-level change detection with seconds-level downstream processing after events are emitted (UC11)
- **ML inference pipeline**: SageMaker Batch Transform with Step Functions Callback Pattern for point cloud segmentation (UC9)
- **Observability stack**: X-Ray distributed tracing + CloudWatch EMF metrics across all 14 use cases

Streaming and SageMaker features are **opt-in via CloudFormation Conditions** (default disabled, zero additional cost). Observability features (X-Ray, EMF, Dashboard, Alarms) can also be disabled but are enabled by default in the reference deployment.

**Repository**: [github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns)

---

## Introduction

In Phase 1 and 2, we established a polling-based architecture using EventBridge Scheduler + Step Functions to process files stored on FSx for ONTAP via S3 Access Points. This approach works well for batch workloads with hourly or daily processing cycles, but some use cases demand faster response times.

Phase 3 addresses three gaps:

1. **Latency**: Kinesis does not remove the need to detect changes — FSx for ONTAP S3 AP does not provide native event notifications. Instead, it decouples the discovery cadence (minute-level polling) from downstream processing and enables low-latency fan-out once change events are emitted.
2. **ML Integration**: Large-scale inference jobs (like LiDAR point cloud segmentation) need asynchronous execution without blocking the Step Functions workflow.
3. **Visibility**: As the pattern collection grows to 14 use cases, operators need centralized metrics, distributed tracing, and automated alerting.

---

## Summary Table

| Feature | Component | AWS Services | Verification |
|---------|-----------|--------------|--------------|
| Near-Real-Time Streaming | Stream Producer + Consumer (UC11) | Kinesis Data Streams, DynamoDB, Lambda | ✅ E2E (PutRecord → GetRecords → DynamoDB state transition) |
| ML Inference | SageMaker Batch Transform (UC9) | SageMaker, Step Functions Callback | ✅ Mock mode (Task_Token round-trip verified) |
| Distributed Tracing | X-Ray instrumentation (all 14 UCs) | AWS X-Ray | ✅ X-Ray support added across all Lambda templates (Active by default) |
| Custom Metrics | EMF output (all 14 UCs) | CloudWatch EMF | ✅ 573 tests pass (EMF JSON round-trip property) |
| Centralized Dashboard | CloudWatch Dashboard | CloudWatch | ✅ Deployed (FSxN-S3AP-Patterns-Dashboard) |
| Alert Automation | CloudWatch Alarms + SNS | CloudWatch, SNS, KMS | ✅ Deployed (composite + KMS-encrypted SNS; 15 alarms in reference deployment) |
| Change Detection | DynamoDB state table | DynamoDB | ✅ E2E (pending → completed state transition) |

### Cost Impact

| Feature | Default | Monthly Cost (when enabled) |
|---------|---------|---------------------------|
| Kinesis Streaming | Disabled | ~$14/month (1 shard, ap-northeast-1; approximate, varies by region and retention settings) |
| SageMaker Batch Transform | Disabled | Pay-per-job (no persistent endpoint) |
| X-Ray Tracing | Enabled | Depends on trace volume; free tier includes 100K traces |
| CloudWatch EMF | Enabled | Included in CloudWatch Logs pricing |
| Dashboard + Alarms | Enabled | Varies by alarm count; reference deployment: 15 alarms + 1 dashboard |

> All features can be individually disabled via CloudFormation parameters (`EnableStreamingMode`, `EnableSageMakerTransform`, `EnableXRayTracing`, `EnableCloudWatchAlarms`). In cost-sensitive PoC environments, disable X-Ray and alarms if they are not needed.

---

## Architecture Decision: Streaming vs Polling

### Why Both Patterns?

FSx for ONTAP S3 Access Points don't support `GetBucketNotificationConfiguration` — there's no native event notification when files change. This means we must actively detect changes. The question is: how frequently, and how do we decouple detection from processing?

**Polling** (Phase 1/2 approach):
```
EventBridge Scheduler (rate(1 hour)) → Step Functions → Discovery Lambda → Processing
```

**Streaming** (Phase 3 addition):
```
EventBridge (rate(1 min)) → Stream Producer (detect changes) → Kinesis → Stream Consumer (process) → Pipeline
```

The key insight: **Kinesis doesn't detect changes faster** — the Stream Producer still polls at 1-minute intervals. What Kinesis provides is **decoupled, low-latency fan-out** once change events are emitted. The consumer processes events within seconds of them appearing on the stream.

### When to Use Each

| Criteria | Polling | Streaming |
|----------|---------|-----------|
| Detection latency | Configurable (min 1 min) | 1 minute (producer polling) |
| Processing latency after detection | Seconds to minutes (Step Functions) | Seconds (Kinesis consumer) |
| File change rate | < 1,000/hour | > 1,000/hour |
| Cost priority | ✅ Lower at low volume | ✅ Lower at high volume |
| Operational simplicity | ✅ Simpler | More components |
| Failure handling | Step Functions Retry/Catch | bisect-on-error + DLQ |

### The Hybrid Approach (Recommended)

For production deployments, we recommend running both:

- **Streaming** handles near-real-time processing (seconds-level latency after detection)
- **Polling** runs hourly as a consistency reconciliation pass

This gives you the best of both worlds: fast downstream processing with guaranteed eventual consistency. If the streaming path fails, the polling path catches up automatically.

---

## Kinesis Integration Deep Dive

### Stream Producer Design

The Stream Producer Lambda runs every minute via EventBridge Scheduler. Its job is change detection:

1. Call `ListObjectsV2` on the S3 Access Point to get the current file listing
2. Compare against a DynamoDB state table (partition key: `file_key`, attributes: `last_modified`, `etag`, `processing_status`)
3. For each new or modified file, write a change event to Kinesis Data Streams

```python
# Change detection logic (simplified for illustration)
# Production implementation should avoid full table scans for large namespaces.
# Use paginated scans, BatchGetItem for listed keys, or prefix-partitioned state tracking.
current_objects = s3_client.list_objects_v2(Bucket=s3_ap_alias)
stored_state = dynamodb_table.scan()

for obj in current_objects:
    stored = stored_state.get(obj['Key'])
    if not stored or stored['etag'] != obj['ETag']:
        # New or modified file detected
        streaming_helper.put_records([
            create_event_record(
                key=obj['Key'],
                event_type='CREATED' if not stored else 'MODIFIED',
                timestamp=datetime.utcnow().isoformat(),
                metadata={'size': obj['Size'], 'etag': obj['ETag']}
            )
        ])
```

> **Scaling note**: For clarity, the snippet uses `scan()`. In production with large namespaces (10K+ objects), use paginated scans, `BatchGetItem` for the keys returned by `ListObjectsV2`, or prefix-partitioned state tracking to avoid full-table scans on every producer run.

### Partition Key Strategy

The partition key is derived from the file path prefix (first directory level). This ensures files in the same directory land on the same shard, enabling ordered processing within a directory while distributing load across shards.

> **Hot shard risk**: If most files land under the same prefix (e.g., all in `products/`), this strategy can create a hot shard. For high-throughput workloads, consider adding a hash suffix or implementing a configurable partitioning strategy.

### Stream Consumer and Dead-Letter Handling

The Stream Consumer Lambda is triggered by Kinesis Event Source Mapping with:
- **Batch size**: 10 records
- **bisect-on-error**: Enabled (splits failed batches to isolate problematic records)
- **Maximum retry attempts**: 3

Failed records are captured by the consumer logic and written to a DynamoDB dead-letter table for investigation. This is a custom implementation within the consumer Lambda — not the event source mapping's built-in on-failure destination (which targets SQS/SNS). The DynamoDB DLQ stores:

- Original record data
- Error message and stack trace
- Timestamp of failure
- Retry count

This avoids blocking the entire shard while preserving failed records for manual reprocessing.

### Idempotent Processing

Since both the streaming and polling paths may process the same file, idempotency is critical. We use DynamoDB conditional writes:

```python
dynamodb_table.update_item(
    Key={'file_key': file_key},
    UpdateExpression='SET processing_status = :status, processed_at = :ts, etag = :etag',
    ConditionExpression='attribute_not_exists(etag) OR etag <> :etag',
    ExpressionAttributeValues={
        ':status': 'COMPLETED',
        ':ts': current_timestamp,
        ':etag': current_etag
    }
)
```

> **Note**: In production, the condition should include the source object's ETag or `last_modified` timestamp so that idempotency is tied to the file version, not only to processing time. This prevents stale events (arriving out of order) from overwriting newer processing results.

---

## SageMaker Callback Pattern

### The Problem

SageMaker Batch Transform jobs can run for minutes to hours depending on data volume. We can't have a Step Functions state waiting synchronously — that would block the workflow and incur unnecessary costs.

### The Solution: .waitForTaskToken

Step Functions' Callback Pattern (`.waitForTaskToken`) is perfect for this:

1. The workflow reaches the SageMaker step and pauses, generating a unique Task Token
2. A Lambda function starts the Batch Transform job, storing a correlation ID
3. The workflow waits without holding Lambda compute. With Standard Workflows, you pay for state transitions rather than Lambda runtime during the wait.
4. When the job completes, an EventBridge rule triggers a callback Lambda
5. The callback Lambda calls `SendTaskSuccess` or `SendTaskFailure` with the Task Token

```yaml
# Step Functions state definition (simplified)
SageMakerTransformStep:
  Type: Task
  Resource: arn:aws:states:::lambda:invoke.waitForTaskToken
  Parameters:
    FunctionName: !Ref SageMakerInvokeLambda
    Payload:
      task_token.$: $$.Task.Token
      input_path.$: $.point_cloud_s3_path
      model_name: !Ref SageMakerModelName
```

### Task Token Propagation

> **Important**: AWS resource tags have value length limits (typically 256 characters). Step Functions Task Tokens can be significantly longer. In the production path, the Task Token should be stored in DynamoDB and correlated with the `TransformJobName` or a short correlation ID. The SageMaker job tag should store only the correlation ID, avoiding tag value length limits.

**Recommended production flow:**

```
Step Functions (.waitForTaskToken)
  → SageMaker Invoke Lambda (receives token in payload)
    → Store TaskToken in DynamoDB keyed by TransformJobName
    → CreateTransformJob (tag: "CorrelationId": "<short-id>")
      → Job completes → EventBridge rule fires
        → SageMaker Callback Lambda
          → Read CorrelationId from job tags / TransformJobName
          → Fetch TaskToken from DynamoDB
          → SendTaskSuccess/SendTaskFailure (returns token to Step Functions)
```

**Mock mode flow** (used in this reference implementation):

In mock mode, the Task Token is passed directly since no actual SageMaker job is created and the token doesn't need to survive across service boundaries:

```python
if os.environ.get('MOCK_MODE', 'false') == 'true':
    # Generate mock segmentation output
    mock_labels = [random.randint(0, 10) for _ in range(input_point_count)]
    s3_client.put_object(Bucket=output_bucket, Key=output_key, Body=json.dumps(mock_labels))
    
    # Directly call SendTaskSuccess (no tag length concern in mock mode)
    sfn_client.send_task_success(
        taskToken=task_token,
        output=json.dumps({'output_path': f's3://{output_bucket}/{output_key}'})
    )
```

This lets you verify the entire workflow data flow without a trained model or tag length concerns.

---

## Observability Stack

### X-Ray Tracing

Every Lambda function and Step Functions state machine in all 14 use cases now supports X-Ray active tracing (enabled by default via `EnableXRayTracing=true`). This provides:

- **End-to-end execution visualization**: See the complete path from EventBridge trigger through Discovery, Processing, and Report stages
- **Latency breakdown**: Identify which service calls (S3 AP, ONTAP API, Bedrock, Textract) contribute most to execution time
- **Error correlation**: Trace errors back to their source across distributed components

#### Graceful Degradation

X-Ray SDK is an optional dependency. If not installed or if `ENABLE_XRAY` is set to `false`, the tracing decorators become no-ops:

```python
@xray_subsegment(name="s3ap_list_objects", annotations={"use_case": "retail-catalog"})
def list_objects(s3_ap_alias):
    # If X-Ray SDK is unavailable, this decorator does nothing
    return s3_client.list_objects_v2(Bucket=s3_ap_alias)
```

This means existing deployments continue working without modification — X-Ray is purely additive.

### CloudWatch Embedded Metrics Format (EMF)

Every Lambda function emits structured metrics via EMF:

- **FilesProcessed** (Count): Number of files processed per invocation
- **ProcessingDuration** (Milliseconds): End-to-end processing time
- **ProcessingErrors** (Count): Number of errors encountered
- **BytesProcessed** (Bytes): Total data volume processed

EMF writes metrics as structured JSON log lines — no additional `PutMetricData` API calls needed:

```json
{
  "_aws": {
    "Timestamp": 1700000000000,
    "CloudWatchMetrics": [{
      "Namespace": "FSxN-S3AP-Patterns",
      "Dimensions": [["UseCase", "FunctionName", "Environment"]],
      "Metrics": [
        {"Name": "FilesProcessed", "Unit": "Count"},
        {"Name": "ProcessingDuration", "Unit": "Milliseconds"}
      ]
    }]
  },
  "UseCase": "retail-catalog",
  "FunctionName": "ImageTaggingLambda",
  "Environment": "prod",
  "FilesProcessed": 15,
  "ProcessingDuration": 2340
}
```

### Dashboard and Alerts

A shared CloudFormation template (`shared/cfn/observability-dashboard.yaml`) creates a CloudWatch dashboard with:

- Per-UC widgets: Step Functions success/failure, Lambda error rates, execution duration
- Cross-UC aggregation: Total files processed, overall error rate, P50/P90/P99 latency
- Kinesis widgets (when streaming enabled): Iterator age, incoming records, consumer lag
- SageMaker widgets (when enabled): Job duration, success/failure count

Alert automation (`shared/cfn/alert-automation.yaml`) provides:

- Step Functions failure rate alarms (default: 3 failures in 5 minutes)
- Lambda error rate alarms (default: 5% in 5 minutes)
- Kinesis iterator age alarms (default: 60 seconds)
- Composite alarms for correlated failures
- SNS notifications with structured messages (email, optional Slack/PagerDuty)

---

## Multi-Region Deployment

### Design Principles

All CloudFormation templates use `${AWS::Region}` for dynamic resource construction — no hardcoded region references. This means you can deploy to any region where the required services are available.

### Phase 3 Service Availability

| Service | Availability | Notes |
|---------|-------------|-------|
| Kinesis Data Streams | Nearly all commercial regions | Shard pricing varies by region |
| SageMaker Batch Transform | Nearly all regions | Instance type availability varies |
| X-Ray | All commercial regions | No constraints |
| CloudWatch EMF | All commercial regions | No constraints |

### Pre-Deployment Checklist

1. Check the [AWS Regional Services List](https://aws.amazon.com/about-aws/global-infrastructure/regional-product-services/)
2. For Kinesis: Verify shard pricing in your target region
3. For SageMaker: Confirm your desired instance type is available
4. For Cross-Region UCs (Textract, Comprehend Medical): Confirm target region connectivity

---

## Verification Results

All Phase 3 features were verified in ap-northeast-1 (Tokyo) against a live FSx for ONTAP environment.

### AWS Environment Verification

| Test | Result | Details |
|------|--------|---------|
| S3 Access Point ListObjectsV2 | ✅ PASS | Via fsxn-eda-s3ap alias |
| Kinesis CreateStream + PutRecord + GetRecords | ✅ PASS | 1 shard, SSE-KMS, partition key routing |
| DynamoDB State Table CRUD | ✅ PASS | PAY_PER_REQUEST, conditional writes |
| DynamoDB Dead-Letter Table | ✅ PASS | record_id partition key |
| E2E Streaming Pipeline | ✅ PASS | Producer → Kinesis → Consumer → DynamoDB |
| CloudFormation validate-template | ✅ PASS | All 14 UC templates |
| cfn-lint | ✅ PASS | 0 errors across all templates |
| CloudWatch Dashboard deploy | ✅ PASS | CREATE_COMPLETE |
| Alert Automation deploy | ✅ PASS | CREATE_COMPLETE (KMS + SNS + 3 alarms) |
| UC11 Full Stack deploy | ✅ PASS | 36 resources (EnableStreamingMode=true) |
| UC9 Full Stack deploy | ✅ PASS | 33 resources (EnableSageMakerTransform=true, MockMode=true) |
| **UC11 Step Functions E2E** | ✅ **SUCCEEDED** | Discovery → ImageTagging → CatalogMetadata → QualityCheck (8.974s) |
| X-Ray Tracing | ✅ PASS | TraceId generated, Stream Producer traces visible in X-Ray console |
| CloudWatch Alarms | ✅ PASS | 15 alarms active (12 OK, 1 ALARM from duration baseline, 2 INSUFFICIENT_DATA). The ALARM state was expected due to a deliberately low duration baseline (2x multiplier) used for validation. |

### Local Test Results

| Suite | Tests | Status |
|-------|-------|--------|
| shared/streaming/ | 18 (16 unit + 2 property) | ✅ All pass |
| shared/observability.py | 23 (19 unit + 4 property) | ✅ All pass |
| retail-catalog (Phase 3) | 17 (producer + consumer) | ✅ All pass |
| autonomous-driving (Phase 3) | 22 (invoke + callback + properties) | ✅ All pass |
| **Total (all UCs)** | **573** | ✅ **All pass** |

### Property-Based Tests (Hypothesis)

| # | Property | Examples | Status |
|---|----------|----------|--------|
| 1 | StreamingConfig round-trip serialization | 100 | ✅ |
| 2 | Record batching preserves count and content | 100 | ✅ |
| 3 | EMF JSON round-trip validity | 100 | ✅ |
| 4 | xray_subsegment no-op when disabled | 100 | ✅ |
| 5 | Task_Token propagation round-trip | 100 | ✅ |
| 6 | Point count invariant (input == output) | 100 | ✅ |
| 7 | Error state propagation (failed → SendTaskFailure) | 100 | ✅ |

---

## Lessons Learned

### Networking and Access

#### 1. S3 Access Points Don't Appear in Bucket Lists

`aws s3api list-buckets` and `aws s3 ls` don't show S3 Access Point aliases. You must access them directly via `aws s3 ls s3://<alias>/` or check the FSx console's volume S3 tab. This caught us during initial verification when we thought the access points had been deleted.

#### 2. S3 Access Point IAM Policies Require Two ARN Formats

S3 Access Points require both the alias format (`arn:aws:s3:::${alias}`) and the ARN format (`arn:aws:s3:${region}:${account}:accesspoint/*`) in IAM policies. The alias format handles S3 API routing, while the ARN format satisfies IAM policy evaluation. Missing either format results in `AccessDenied` errors.

At a high level, include both forms in your IAM policy Resource block:
- Alias format: `arn:aws:s3:::${S3AccessPointAlias}` and `.../*`
- Access point ARN format: `arn:aws:s3:${Region}:${AccountId}:accesspoint/*`

See the [Phase 2 article's Design Decisions section](https://dev.to/yoshikifujiwara/9-more-industry-serverless-patterns-with-fsx-for-ontap-s3-access-points-semiconductor-genomics-15e4) or the CloudFormation templates in the repository for the full IAM policy pattern.

#### 3. Verify the Actual DNS and VPC Endpoint Path for S3 Access Points

During verification, S3 AP access from VPC-attached Lambda required careful validation of the DNS resolution path, route table associations, VPC endpoint policies, and access point network origin. Do not assume that creating an S3 Gateway Endpoint alone guarantees successful S3 AP access in every topology.

S3 Access Points can work with both S3 Gateway Endpoints and S3 Interface Endpoints ([AWS docs](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/configuring-network-access-for-s3-access-points.html)). However, the VPC endpoint policy must allow the required S3 Access Point resources and actions, and the IAM policy must include the ARN formats used by the implementation (see Lesson #2 above). Additionally, if the access point uses VPC origin, ensure `enableDnsHostnames` and `enableDnsSupport` are enabled on the VPC.

In our case, the root cause was the S3 Gateway Endpoint not being associated with the Lambda subnet's route table — a simple but easy-to-miss configuration issue.

**Verified**: After associating the S3 Gateway Endpoint with the correct route table and fixing the IAM policy (two ARN formats), S3 AP access via Gateway Endpoint worked successfully. No S3 Interface Endpoint was needed.

#### 4. Interface VPC Endpoint Security Group Design

Interface VPC Endpoints should use a **dedicated security group** (separate from the Lambda SG) with an ingress rule allowing HTTPS (443) from the Lambda security group. Using the same SG for both Lambda and Interface VPC Endpoints creates confusion with self-referencing rules and can lead to connectivity issues. Note that Gateway VPC Endpoints do not use security groups — they rely on route table associations and endpoint policies.

### Deployment and Packaging

#### 5. DynamoDB Table Creation Timing

DynamoDB tables in PAY_PER_REQUEST mode take 5-10 seconds to become ACTIVE after CreateTable. Immediate PutItem calls will fail with `ResourceNotFoundException`. In CloudFormation this is handled by dependency ordering, but in scripts always use `aws dynamodb wait table-exists`.

#### 6. VPC Lambda ENI Cleanup Takes 10-20 Minutes

When deleting CloudFormation stacks with VPC-attached Lambda functions, the ENI (Elastic Network Interface) cleanup can take 10-20 minutes. This is a known AWS behavior. Use `--deletion-mode FORCE_DELETE_STACK` for stuck DELETE_FAILED stacks.

#### 7. Handler Path Flattening with `aws cloudformation package`

When `aws cloudformation package` uploads Lambda code to S3, it flattens the directory structure. If your template uses `Handler: retail-catalog/functions/discovery/handler.handler`, the packaged template must be updated to `Handler: handler.handler`. We automated this with a `sed` post-processing step in the deploy script.

#### 8. Lambda Packaging: Individual ZIPs Required for Shared Modules

`aws cloudformation package` zips the template's directory, but shared modules in parent directories are excluded. For this project, each Lambda function requires an individual ZIP containing both `handler.py` and the `shared/` module at the root level. The deploy script handles this automatically via a `package_lambda()` helper function.

### Workflow and ML Integration

#### 9. Task Token Length and SageMaker Job Tags

AWS resource tags typically have a 256-character value limit. Step Functions Task Tokens can exceed this. For production SageMaker integrations, store the Task Token in DynamoDB and pass only a short correlation ID as a job tag. The mock mode in this reference implementation passes the token directly since no actual SageMaker job is created.

#### 10. Opt-in Design Validates Backward Compatibility

By defaulting streaming and SageMaker features to disabled (CloudFormation Conditions), we confirmed zero impact on existing Phase 1/2 deployments. The same template works for both "Phase 2 mode" (features disabled) and "Phase 3 mode" (features enabled).

---

## Conclusion

Phase 3 transforms the FSx for ONTAP S3 Access Points pattern collection from a batch-oriented toolkit into a near-real-time capable platform with:

- **Faster downstream processing**: Kinesis streaming enables seconds-level processing after minute-level change detection
- **ML integration**: SageMaker Callback Pattern provides scalable, cost-effective inference without persistent endpoints
- **Production visibility**: X-Ray + EMF + Dashboard + Alerts give operators full observability across all 14 use cases

Streaming and SageMaker features are opt-in with zero cost when disabled. Observability is enabled by default but can be individually toggled, maintaining backward compatibility with Phase 1/2 deployments.

### What's Next

- Event-driven architecture exploration (when FSx ONTAP S3 AP supports native notifications — eliminating the polling requirement entirely)
- DynamoDB-based Task Token storage for production SageMaker integrations
- Additional ML patterns (real-time inference endpoints, A/B testing)
- Multi-account deployment patterns with AWS Organizations

**Repository**: [github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns)

---

*This article is part of the "FSx for ONTAP S3 Access Points" series. See [Phase 1](https://dev.to/yoshikifujiwara/fsx-for-ontap-s3-access-points-as-a-serverless-automation-boundary-ai-data-pipelines-ili) and [Phase 2](https://dev.to/yoshikifujiwara/9-more-industry-serverless-patterns-with-fsx-for-ontap-s3-access-points-semiconductor-genomics-15e4) for the foundation.*
