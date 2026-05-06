---
title: "Production SageMaker Patterns, Multi-Account Deployment, and Event-Driven Architecture for FSx for ONTAP S3 Access Points — Phase 4"
published: false
description: "Phase 4 adds DynamoDB Task Token Store (Correlation ID pattern), Real-time Inference with A/B Testing, Multi-Account StackSets deployment, and an Event-Driven Architecture prototype achieving 3.5-second E2E latency."
tags: aws, serverless, netapp, python
cover_image: https://raw.githubusercontent.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/main/docs/screenshots/masked/phase4-event-driven-e2e.png
series: "FSx for ONTAP S3 Access Points"
---

## TL;DR

This is **Phase 4** of the FSx for ONTAP S3 Access Points serverless patterns collection. Building on the [Phase 1 foundation](https://dev.to/yoshikifujiwara/fsx-for-ontap-s3-access-points-as-a-serverless-automation-boundary-ai-data-pipelines-ili), the [14 industry patterns from Phase 2](https://dev.to/yoshikifujiwara/9-more-industry-serverless-patterns-with-fsx-for-ontap-s3-access-points-semiconductor-genomics-15e4), and the [near-real-time + ML + observability stack from Phase 3](https://dev.to/yoshikifujiwara/near-real-time-processing-ml-inference-and-observability-for-fsx-for-ontap-s3-access-points--bkd), Phase 4 delivers:

- **DynamoDB Task Token Store**: Correlation ID pattern solving the 256-char SageMaker tag limit for production Step Functions Callback workflows
- **Real-time Inference + A/B Testing**: SageMaker Multi-Variant Endpoints with intelligent routing and automated comparison metrics
- **Multi-Account Deployment**: StackSets, RAM resource sharing, and Cross-Account IAM for enterprise-scale rollout
- **Event-Driven Architecture Prototype**: S3 Events → EventBridge → Step Functions achieving **3.5-second E2E latency**

All features are **opt-in via CloudFormation Conditions** (default disabled, zero additional cost). 681 total tests pass, including 11 property-based tests (Hypothesis).

**Repository**: [github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns)

---

## Introduction

Phase 3 delivered near-real-time streaming, SageMaker Batch Transform with the Callback Pattern, and a full observability stack. But it left several production gaps:

1. **Task Token storage**: The Phase 3 mock mode passed tokens directly, but SageMaker tag values are limited to 256 characters while Task Tokens are ~1,000 characters
2. **Inference latency**: Batch Transform takes minutes — some use cases need millisecond-level responses
3. **Enterprise deployment**: Single-account patterns don't scale to organizations with multiple workload accounts
4. **Event latency**: Even with Kinesis, the polling-based change detection adds a 1-minute floor to end-to-end latency

Phase 4 addresses all four gaps while maintaining the project's core principle: **every feature is opt-in with zero cost when disabled**.

---

## Summary Table

| Feature | Component | AWS Services | Verification |
|---------|-----------|--------------|--------------|
| Task Token Store | Correlation ID + DynamoDB | DynamoDB, Step Functions, Lambda | ✅ E2E (8-char hex round-trip, TTL cleanup) |
| Real-time Inference | Multi-Variant Endpoint | SageMaker, Auto Scaling | ✅ Deployed (ml.m5.large, 1-4 instances) |
| A/B Testing | Traffic Splitting + Comparison | SageMaker, CloudWatch EMF | ✅ Variant metrics aggregation verified |
| Multi-Account | StackSets + RAM + IAM | CloudFormation StackSets, RAM, IAM | ✅ Template validation (cross-account role chain) |
| Event-Driven Prototype | S3 → EventBridge → Step Functions | S3, EventBridge, Step Functions, Lambda | ✅ **E2E: 3.5 seconds** (PutObject → processing complete) |
| Model Registry | Approval Workflow | SageMaker Model Registry | ✅ Governance flow validated |

### Cost Impact

| Feature | Default | Monthly Cost (when enabled) |
|---------|---------|---------------------------|
| DynamoDB Task Token Store | Disabled | ~$0 (PAY_PER_REQUEST, minimal reads/writes) |
| Real-time Endpoint | Disabled | ~$215/month (ml.m5.large, single instance, ap-northeast-1) |
| A/B Testing (Multi-Variant) | Disabled | Included in endpoint cost (traffic split) |
| Auto Scaling (1-4 instances) | Disabled | $215–$860/month depending on load |
| Model Registry | Disabled | $0 (metadata only) |
| Event-Driven Prototype | Disabled | ~$0 (pay-per-event, negligible at test scale) |

> **Cost warning**: The Real-time Endpoint is the only feature with significant ongoing cost (~$7/day for ml.m5.large). The cleanup script (`scripts/cleanup_phase4.sh --endpoint-only`) stops billing within minutes. Always delete the endpoint when not actively testing.

---

## Theme A: DynamoDB Task Token Store

### The Problem

In Phase 3, we implemented the SageMaker Callback Pattern by passing the Step Functions Task Token directly in SageMaker job tags. This works for prototyping but has a critical limitation: **SageMaker tag values are limited to 256 characters**, while Task Tokens are approximately 1,000 characters.

### The Solution: Correlation ID Pattern

```
Step Functions (.waitForTaskToken)
  → SageMaker Invoke Lambda
    → Generate 8-char hex Correlation ID (UUID4 prefix)
    → Store {correlation_id → task_token} in DynamoDB (TTL: 24h)
    → Create Transform Job with tag: CorrelationId=abc12345

SageMaker Job Completes
  → EventBridge Rule triggers Callback Lambda
    → Extract CorrelationId from job tags
    → Retrieve task_token from DynamoDB
    → SendTaskSuccess/Failure to Step Functions
    → Delete DynamoDB record (cleanup)
```

### Key Design Decisions

**Why 8-character hex IDs?** With 32 bits of entropy (4.3 billion possible values), collision probability is negligible for our use case. The short length fits comfortably within SageMaker's 256-character tag value limit while providing sufficient uniqueness for concurrent jobs.

**Why DynamoDB?** Single-digit millisecond latency, automatic TTL cleanup (24-hour expiry), conditional writes for collision prevention, and pay-per-request pricing that costs effectively $0 at our scale.

**Security**: Task Tokens are never logged in plaintext. Only the correlation ID appears in CloudWatch Logs, providing auditability without exposing sensitive tokens.

**Backward Compatibility**: The `TOKEN_STORAGE_MODE` environment variable allows switching between `dynamodb` (new) and `direct` (Phase 3 compatible) modes. The Callback Lambda auto-detects the mode by checking which tag is present on the completed job.

### DynamoDB Table Design

```yaml
TaskTokenStore:
  Type: AWS::DynamoDB::Table
  Properties:
    TableName: !Sub "${AWS::StackName}-task-token-store"
    BillingMode: PAY_PER_REQUEST
    AttributeDefinitions:
      - AttributeName: correlation_id
        AttributeType: S
    KeySchema:
      - AttributeName: correlation_id
        KeyType: HASH
    TimeToLiveSpecification:
      AttributeName: ttl
      Enabled: true
```

### Conditional Write for Collision Prevention

```python
dynamodb_table.put_item(
    Item={
        'correlation_id': correlation_id,
        'task_token': task_token,
        'job_name': transform_job_name,
        'created_at': int(time.time()),
        'ttl': int(time.time()) + 86400  # 24-hour TTL
    },
    ConditionExpression='attribute_not_exists(correlation_id)'
)
```

If a collision occurs (astronomically unlikely with 8-char hex), the Lambda retries with a new ID.

---

## Theme B: Real-time Inference + A/B Testing

### Three Inference Patterns

Phase 4 provides three SageMaker inference patterns, each optimized for different workload characteristics:

| Pattern | Latency | Cost Model | Best For |
|---------|---------|-----------|----------|
| Batch Transform | Minutes | Per-job | Large batch processing (≥10 files) |
| Real-time Endpoint | Milliseconds | Per-instance-hour | Consistent low-latency needs |
| Serverless Inference | Seconds | Per-request | Sporadic, unpredictable traffic |

### Intelligent Routing

The Step Functions workflow uses a Choice state to route requests based on file count:

```
file_count < threshold (default: 10)
  → Real-time Endpoint (low latency, immediate response)

file_count >= threshold
  → Batch Transform (cost-efficient for large batches)
```

This threshold is configurable via CloudFormation parameters, allowing operators to tune the routing based on their specific latency and cost requirements.

### A/B Testing with Multi-Variant Endpoints

SageMaker's native traffic splitting enables A/B testing without additional infrastructure:

```yaml
ProductionVariants:
  - VariantName: "model-v1"
    ModelName: !Ref ModelV1
    InitialInstanceCount: 1
    InstanceType: ml.m5.large
    InitialVariantWeight: 0.7  # 70% traffic
  - VariantName: "model-v2"
    ModelName: !Ref ModelV2
    InitialInstanceCount: 1
    InstanceType: ml.m5.large
    InitialVariantWeight: 0.3  # 30% traffic
```

### Auto Scaling Configuration

```yaml
ScalingTarget:
  Type: AWS::ApplicationAutoScaling::ScalableTarget
  Properties:
    MinCapacity: 1
    MaxCapacity: 4
    ResourceId: !Sub "endpoint/${EndpointName}/variant/model-v1"
    ScalableDimension: sagemaker:variant:DesiredInstanceCount
    ServiceNamespace: sagemaker

ScalingPolicy:
  Type: AWS::ApplicationAutoScaling::ScalingPolicy
  Properties:
    PolicyType: TargetTrackingScaling
    TargetTrackingScalingPolicyConfiguration:
      TargetValue: 70  # Scale when invocations per instance > 70
      PredefinedMetricSpecification:
        PredefinedMetricType: SageMakerVariantInvocationsPerInstance
```

### Inference Comparison Lambda

The Inference Comparison Lambda runs every 5 minutes, aggregating per-variant metrics and emitting CloudWatch EMF metrics:

```python
for variant in endpoint_variants:
    metrics = cloudwatch.get_metric_statistics(
        MetricName='ModelLatency',
        Dimensions=[
            {'Name': 'EndpointName', 'Value': endpoint_name},
            {'Name': 'VariantName', 'Value': variant['VariantName']}
        ],
        Period=300,
        Statistics=['Average', 'p50', 'p90', 'p99']
    )
    emit_emf_metric(
        namespace='FSxN-S3AP-Patterns/Inference',
        dimensions={'Variant': variant['VariantName']},
        metrics={
            'AverageLatency': metrics['Average'],
            'P99Latency': metrics['p99'],
            'InvocationCount': variant['CurrentInvocationCount'],
            'ErrorRate': variant['ErrorRate']
        }
    )
```

### Model Registry Integration

The SageMaker Model Registry provides a governance layer:

```
Training → Registration (PendingManualApproval) → Approval → Deployment
```

Only approved models can be deployed to production endpoints, preventing accidental deployment of untested models.

---

## Theme C: Multi-Account Deployment

### Architecture

```
Management Account
  └── CloudFormation StackSets (deploy UC templates to workload accounts)

Storage Account
  ├── FSx ONTAP File System
  ├── S3 Access Points
  └── AWS RAM Resource Share (share S3 AP with workload accounts)

Shared Services Account
  ├── CloudWatch Observability Sink (cross-account metrics/logs/traces)
  ├── X-Ray Cross-Account Tracing
  └── SNS Aggregated Alerts

Workload Account(s)
  ├── UC Deployments (Lambda + Step Functions)
  ├── Cross-Account IAM Roles (with External ID)
  └── CloudWatch Sharing Links
```

### Security Controls

**External ID**: All cross-account role assumptions require an External ID, preventing confused deputy attacks.

**Permission Boundaries**: Cross-account roles have permission boundaries that cap the maximum permissions, preventing privilege escalation even if the role policy is misconfigured.

**Least Privilege**: Each role has only the permissions required for its specific function (e.g., S3 AP read-only, DynamoDB write-only for token store).

### StackSets for Consistent Deployment

CloudFormation StackSets enable deploying the same UC template across multiple accounts with per-account parameter overrides:

```yaml
# Account-specific overrides
ParameterOverrides:
  - ParameterKey: VpcId
    ParameterValue: "vpc-xxx"  # Account-specific VPC
  - ParameterKey: StorageAccountId
    ParameterValue: "111111111111"
  - ParameterKey: ExternalId
    ParameterValue: "unique-per-account-id"
  - ParameterKey: S3AccessPointAlias
    ParameterValue: "shared-fsxn-s3ap-alias"
```

### AWS RAM for S3 Access Point Sharing

```yaml
ResourceShare:
  Type: AWS::RAM::ResourceShare
  Properties:
    Name: "fsxn-s3ap-share"
    Principals:
      - "arn:aws:organizations::111111111111:ou/o-xxx/ou-xxx"
    ResourceArns:
      - !Sub "arn:aws:s3:${AWS::Region}:${AWS::AccountId}:accesspoint/${AccessPointName}"
```

### Cross-Account Observability

CloudWatch Cross-Account Observability aggregates metrics, logs, and traces from all workload accounts into a single shared services dashboard:

- Unified view of all UC executions across accounts
- Cross-account X-Ray service maps
- Centralized alerting via SNS with per-account routing

---

## Theme D: Event-Driven Architecture Prototype

### The Current State

FSx for ONTAP S3 Access Points do not currently support `GetBucketNotificationConfiguration`, which means we cannot receive native event notifications when files are created or modified. This is why Phases 1–3 use a polling-based architecture (EventBridge Scheduler → Step Functions → Discovery Lambda).

### The Prototype

Phase 4 includes an event-driven prototype using a standard S3 bucket to demonstrate what the architecture will look like when FSx ONTAP S3 AP adds native notification support:

```
S3 Bucket (PutObject)
  → S3 Event Notification
    → EventBridge Rule (pattern filter: suffix=.bin, prefix=sensor-data/)
      → Step Functions (StartExecution)
        → Processing Lambdas (reused from UC11)
          → Output written to results bucket
```

### E2E Verification: 3.5 Seconds

The event-driven prototype was verified end-to-end in ap-northeast-1:

| Stage | Latency |
|-------|---------|
| S3 PutObject → EventBridge delivery | ~500ms |
| EventBridge → Step Functions start | ~200ms |
| Step Functions → Lambda cold start | ~800ms |
| Lambda processing (UC11 pipeline) | ~2,000ms |
| **Total E2E** | **~3.5 seconds** |

Compare this to the polling approach: minimum 1-minute detection interval + processing time = 60+ seconds.

### Processing Equivalence

The same Lambda functions produce identical output regardless of whether they're triggered by polling or events. This is validated by Property Test #11 (processing equivalence), ensuring a safe migration path.

### Migration Strategy

A three-phase migration allows gradual transition when FSx ONTAP S3 AP adds native event support:

1. **Phase A**: Parallel operation (both polling and event-driven active, compare outputs)
2. **Phase B**: Event-driven primary (polling as consistency reconciliation fallback)
3. **Phase C**: Event-driven only (polling disabled, cost savings)

### Future: Native S3 AP Events

When FSx ONTAP S3 AP adds native event notification support, the migration from the prototype to production requires only:
1. Replace the S3 bucket event source with the S3 AP ARN
2. Update the EventBridge rule pattern
3. No changes to processing Lambdas or Step Functions

---

## Design Principles

### Opt-in Everything

Every Phase 4 feature is controlled by a CloudFormation Condition:

```yaml
Conditions:
  EnableDynamoDBTokenStoreCondition: !Equals [!Ref EnableDynamoDBTokenStore, "true"]
  EnableRealtimeEndpointCondition: !Equals [!Ref EnableRealtimeEndpoint, "true"]
  EnableABTestingCondition: !Equals [!Ref EnableABTesting, "true"]
  EnableModelRegistryCondition: !Equals [!Ref EnableModelRegistry, "true"]
```

Default is always `false`. This means:
- Zero additional cost when features are disabled
- No breaking changes to existing Phase 1/2/3 deployments
- Gradual feature adoption at the operator's pace

### Non-Breaking Guarantee

Phase 4 additions do not modify any existing Phase 1/2/3 code:
- New shared modules are only imported by new Phase 4 Lambdas
- Existing Lambda functions continue to work unchanged
- All existing tests pass without modification (573 Phase 1–3 tests + 108 new Phase 4 tests = 681 total)
- CloudFormation templates remain backward compatible

### Property-Based Testing (Hypothesis)

Phase 4 introduces 11 correctness properties:

| # | Property | Examples | Status |
|---|----------|----------|--------|
| 1 | Correlation ID format invariant (8-char hex) | 100 | ✅ |
| 2 | Task Token round-trip integrity (store → retrieve → match) | 100 | ✅ |
| 3 | TTL calculation correctness (created_at + 86400) | 100 | ✅ |
| 4 | Conditional write collision prevention | 100 | ✅ |
| 5 | Mode detection by tag presence (CorrelationId vs TaskToken) | 100 | ✅ |
| 6 | Token never logged in plaintext | 100 | ✅ |
| 7 | Cleanup after callback (DynamoDB record deleted) | 100 | ✅ |
| 8 | File count threshold routing (< threshold → realtime) | 100 | ✅ |
| 9 | Variant weight normalization (sum = 1.0) | 100 | ✅ |
| 10 | Aggregation correctness (per-variant metric math) | 100 | ✅ |
| 11 | Processing equivalence (polling vs event-driven output) | 100 | ✅ |

---

## Verification Results

### AWS Environment Verification

| Test | Result | Details |
|------|--------|---------|
| DynamoDB Task Token Store CRUD | ✅ PASS | Conditional write, TTL, round-trip |
| SageMaker Real-time Endpoint deploy | ✅ PASS | ml.m5.large, InService |
| Multi-Variant traffic split | ✅ PASS | 70/30 split verified via CloudWatch |
| Auto Scaling policy | ✅ PASS | Scale-out triggered at 70 invocations/instance |
| StackSets template validation | ✅ PASS | Cross-account parameter overrides |
| RAM resource share | ✅ PASS | S3 AP shared to target OU |
| Event-Driven E2E | ✅ **PASS** | **3.5 seconds** (PutObject → processing complete) |
| CloudFormation validate-template | ✅ PASS | All templates |
| cfn-lint | ✅ PASS | 0 errors |

### Local Test Results

| Suite | Tests | Status |
|-------|-------|--------|
| shared/token_store/ | 24 (20 unit + 4 property) | ✅ All pass |
| shared/inference/ | 18 (14 unit + 4 property) | ✅ All pass |
| autonomous-driving (Phase 4) | 38 (35 unit + 3 property) | ✅ All pass |
| event-driven-prototype/ | 28 (28 unit) | ✅ All pass |
| **Total (all phases)** | **681** | ✅ **All pass** |

---

## Lessons Learned

### 1. SageMaker Model Requires Pre-existing Model Artifact in S3

SageMaker `CreateModel` expects the model artifact (e.g., `model.tar.gz`) to already exist in S3. Unlike training jobs that produce artifacts, real-time endpoints need the artifact uploaded before stack deployment. Our deploy script includes a `upload_model_artifact()` step that runs before `aws cloudformation deploy`.

### 2. CloudFormation Template > 51KB Requires S3 Bucket Deployment

As Phase 4 templates grew beyond 51KB (the inline template body limit), `aws cloudformation create-stack --template-body` fails. The solution: use `aws cloudformation deploy --template-file` which automatically uploads to an S3 staging bucket, or explicitly use `--template-url` with a pre-uploaded template. Our deploy script uses a dedicated `DeployBucket` parameter for this.

### 3. VPC Lambda ENI Cleanup Takes 5–20 Minutes

When deleting CloudFormation stacks with VPC-attached Lambda functions, ENI (Elastic Network Interface) cleanup can take 5–20 minutes. CloudFormation times out waiting. Our enhanced cleanup script (`scripts/cleanup_phase4.sh`) proactively finds and deletes orphaned ENIs (status=available) before retrying stack deletion.

```bash
# Find orphaned Lambda ENIs
aws ec2 describe-network-interfaces \
  --filters "Name=vpc-id,Values=$VPC_ID" "Name=status,Values=available" \
  --query 'NetworkInterfaces[].NetworkInterfaceId'
```

### 4. Security Group Cross-References Block Deletion

When SG-A references SG-B in its ingress rules, deleting SG-B fails with "has a dependent object". The cleanup script revokes cross-SG references before attempting deletion:

```bash
# Find SGs that reference the target SG
aws ec2 describe-security-groups \
  --filters "Name=ip-permission.group-id,Values=$TARGET_SG"

# Revoke the reference, then delete
aws ec2 revoke-security-group-ingress --group-id $REFERENCING_SG --ip-permissions ...
aws ec2 delete-security-group --group-id $TARGET_SG
```

### 5. S3 Versioned Buckets Require Version-Aware Deletion

Stack deletion fails when S3 buckets have versioning enabled because `aws s3 rm --recursive` only deletes current versions. You must also delete all object versions and delete markers:

```bash
# Delete all versions
aws s3api list-object-versions --bucket $BUCKET \
  --query '{Objects: Versions[].{Key:Key,VersionId:VersionId}}'
aws s3api delete-objects --bucket $BUCKET --delete ...

# Delete all delete markers
aws s3api list-object-versions --bucket $BUCKET \
  --query '{Objects: DeleteMarkers[].{Key:Key,VersionId:VersionId}}'
aws s3api delete-objects --bucket $BUCKET --delete ...
```

### 6. Event-Driven Latency: Sub-4-Second E2E

The event-driven prototype achieved 3.5-second end-to-end latency from S3 PutObject to processing complete. This is a 17x improvement over the 1-minute polling floor. The breakdown: S3 notification (~500ms) + EventBridge routing (~200ms) + Lambda cold start (~800ms) + processing (~2s). With provisioned concurrency, the cold start component can be eliminated.

---

## What's Next

- **FSx ONTAP S3 AP native events**: When available, migrate from prototype to production event-driven architecture (no Lambda/Step Functions changes needed)
- **Serverless Inference**: Add SageMaker Serverless Inference as a third routing option for sporadic workloads
- **Cost optimization**: Implement SageMaker Savings Plans and scheduled scaling for predictable workloads
- **Multi-region active-active**: Extend multi-account patterns to multi-region with DynamoDB Global Tables for token store

---

## Conclusion

Phase 4 transforms the FSxN S3AP Serverless Patterns from a demonstration project into a production-ready reference architecture:

- The **DynamoDB Task Token Store** solves a real production limitation (256-char tag limit) with an elegant 8-char correlation ID pattern
- **Multi-Variant Endpoints** enable safe model iteration with automated A/B comparison metrics
- **Multi-Account templates** support enterprise deployment patterns with proper security controls
- The **Event-Driven prototype** charts the path forward with proven 3.5-second E2E latency

All features remain opt-in, maintaining the project's core principle: **learn from the design decisions without paying for resources you don't need**.

**Repository**: [github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns)

---

*This article is part of the "FSx for ONTAP S3 Access Points" series. See [Phase 1](https://dev.to/yoshikifujiwara/fsx-for-ontap-s3-access-points-as-a-serverless-automation-boundary-ai-data-pipelines-ili), [Phase 2](https://dev.to/yoshikifujiwara/9-more-industry-serverless-patterns-with-fsx-for-ontap-s3-access-points-semiconductor-genomics-15e4), and [Phase 3](https://dev.to/yoshikifujiwara/near-real-time-processing-ml-inference-and-observability-for-fsx-for-ontap-s3-access-points--bkd) for the foundation.*
