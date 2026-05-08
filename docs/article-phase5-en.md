---
title: "Serverless Inference, Cost Optimization, CI/CD Pipelines, and Multi-Region Architecture for FSx for ONTAP S3 Access Points — Phase 5"
published: false
description: "Phase 5 adds SageMaker Serverless Inference as a 3rd routing option, comprehensive cost optimization with Scheduled Scaling and Auto-Stop, GitHub Actions CI/CD pipelines, and Multi-Region architecture with DynamoDB Global Tables and DR Tier definitions."
tags: aws, serverless, netapp, python
cover_image: https://raw.githubusercontent.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/main/docs/screenshots/masked/phase5-sagemaker-serverless-endpoint-settings.png
series: "FSx for ONTAP S3 Access Points"
---

## TL;DR

This is **Phase 5** of the FSx for ONTAP S3 Access Points serverless patterns collection. Building on the [Phase 1 foundation](https://dev.to/yoshikifujiwara/fsx-for-ontap-s3-access-points-as-a-serverless-automation-boundary-ai-data-pipelines-ili), the [14 industry patterns from Phase 2](https://dev.to/yoshikifujiwara/9-more-industry-serverless-patterns-with-fsx-for-ontap-s3-access-points-semiconductor-genomics-15e4), the [near-real-time + ML + observability stack from Phase 3](https://dev.to/yoshikifujiwara/near-real-time-processing-ml-inference-and-observability-for-fsx-for-ontap-s3-access-points--bkd), and the [production SageMaker + Multi-Account + Event-Driven from Phase 4](https://dev.to/yoshikifujiwara/production-sagemaker-patterns-multi-account-deployment-and-event-driven-architecture-for-fsx-for-ontap-s3-access-points-phase-4), Phase 5 delivers:

- **SageMaker Serverless Inference**: 3rd routing option completing the Batch/Real-time/Serverless trifecta with cold start handling and automatic fallback
- **Cost Optimization Suite**: Scheduled Scaling, CloudWatch Billing Alarms (3-tier), Auto-Stop Lambda for idle endpoint detection, and a comprehensive cross-phase cost guide
- **CI/CD Pipeline**: GitHub Actions with OIDC authentication, 4-stage gating (cfn-lint → pytest → cfn-guard → Bandit), staging/production deployment with manual approval
- **Multi-Region Architecture**: DynamoDB Global Tables for Task Token Store replication, CrossRegionClient failover, DR Tier 1/2/3 definitions with failover runbooks

All features remain **opt-in via CloudFormation Conditions** (default disabled, zero additional cost). 15 property-based tests (Hypothesis) validate correctness invariants across all themes.

**Repository**: [github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns)

---

## Introduction

Phase 4 delivered production SageMaker integration, Multi-Account deployment, and an Event-Driven prototype. The "What's Next" section outlined four remaining gaps:

1. **Serverless Inference**: Sporadic workloads need a pay-per-request option without always-on instances
2. **Cost optimization**: Real-time Endpoints cost ~$215/month — operators need automated cost controls
3. **CI/CD automation**: Manual deployment doesn't scale for teams with multiple contributors
4. **Multi-Region resilience**: Single-region architectures have a blast radius equal to the entire system

Phase 5 addresses all four while maintaining the project's core principle: **every feature is opt-in with zero cost when disabled**.

---

## Summary Table

| Feature | Component | AWS Services | Key Metric |
|---------|-----------|--------------|------------|
| Serverless Inference | 3-way routing | SageMaker ServerlessConfig, Step Functions | Cold start: 6–45s |
| Scheduled Scaling | Business hours scaling | Application Auto Scaling | Cost reduction: up to 70% |
| Billing Alarms | 3-tier alerts | CloudWatch, SNS | Warning/Critical/Emergency |
| Auto-Stop | Idle detection | Lambda, CloudWatch Metrics | 60-min idle threshold |
| CI/CD Pipeline | 4-stage gating | GitHub Actions, OIDC | All stages must pass |
| Multi-Region | Global Tables + failover | DynamoDB Global Tables, Route 53 | RPO=0 (Tier 1) |
| Disaster Recovery | Tier 1/2/3 | Route 53, EventBridge, Step Functions | RTO: 5min–4h |

---

## Theme A: SageMaker Serverless Inference

### The Three Inference Paths

Phase 5 completes the inference routing trifecta that was previewed in Phase 4:

| Path | Trigger | Latency | Cost Model | Best For |
|------|---------|---------|-----------|----------|
| Batch Transform | `file_count >= threshold` OR `InferenceType == "none"` | Minutes | Per-job | Large batch processing |
| Real-time Endpoint | `file_count < threshold` AND `InferenceType == "provisioned"` | Milliseconds | Per-instance-hour | Consistent traffic |
| **Serverless Inference** | `InferenceType == "serverless"` | Seconds (warm) / 6–45s (cold) | Per-request | Sporadic, unpredictable traffic |

### Deterministic 3-Way Routing

The routing logic in `shared/routing.py` is deterministic — the same inputs always produce the same output:

```python
def determine_inference_path(file_count: int, batch_threshold: int, inference_type: str) -> InferencePath:
    if inference_type == "none":
        return InferencePath.BATCH_TRANSFORM
    if inference_type == "serverless":
        return InferencePath.SERVERLESS_INFERENCE
    if file_count >= batch_threshold:
        return InferencePath.BATCH_TRANSFORM
    return InferencePath.REALTIME_ENDPOINT
```

This is validated by Property Test #1 (Three-Way Routing Determinism): for any combination of `file_count`, `batch_threshold`, and `inference_type`, exactly one path is selected, and calling the function twice with the same inputs produces the same result.

### Cold Start Handling

Serverless Inference introduces a unique challenge: `ModelNotReadyException` during cold starts. Our implementation handles this with:

1. **Extended initial timeout**: 60 seconds (vs. standard 30s for Real-time)
2. **Retry with backoff**: 3-second delay, maximum 2 retries
3. **Total timeout guard**: `initial_timeout + (retry_delay × max_retries) <= step_functions_task_timeout (120s)`
4. **Cold start detection**: Latency > 5000ms triggers `ColdStartDetected` EMF metric
5. **Automatic fallback**: On timeout, the Step Functions Catch block routes to Batch Transform

```yaml
# Step Functions definition (simplified)
ServerlessInferencePath:
  Type: Task
  TimeoutSeconds: 120
  Catch:
    - ErrorEquals: ["States.TaskFailed", "States.Timeout"]
      Next: BatchTransformFallback
```

### ServerlessConfig Validation

The `validate_serverless_config()` function enforces SageMaker constraints:

- **MemorySizeInMB**: Must be one of {1024, 2048, 3072, 4096, 5120, 6144}
- **MaxConcurrency**: Must be in range [1, 200]

Property Test #2 validates these constraints hold for all possible inputs.

---

## Theme B: Cost Optimization + Scheduled Scaling

### Scheduled Scaling

The most impactful cost optimization for SageMaker Endpoints is time-based scaling. A Real-time Endpoint running 24/7 costs ~$215/month, but most workloads only need it during business hours:

```yaml
# shared/cfn/scheduled-scaling.yaml (nested stack)
ScaleUpAction:
  Type: AWS::ApplicationAutoScaling::ScheduledAction
  Properties:
    Schedule: "cron(0 9 ? * MON-FRI *)"  # 09:00 JST weekdays
    ScalableTargetAction:
      MinCapacity: !Ref BusinessMinCapacity
      MaxCapacity: !Ref BusinessMaxCapacity

ScaleDownAction:
  Type: AWS::ApplicationAutoScaling::ScheduledAction
  Properties:
    Schedule: "cron(0 18 ? * MON-FRI *)"  # 18:00 JST weekdays
    ScalableTargetAction:
      MinCapacity: !Ref OffHoursMinCapacity
      MaxCapacity: !Ref OffHoursMaxCapacity
```

**Cost impact**: Weekday 9–18 only = 58% reduction. Add weekend shutdown = 70% reduction.

Property Test #5 validates that `business_hours_start < business_hours_end` is enforced, and Property Test #6 validates that `off_hours_max_capacity <= business_min_capacity` (guaranteeing cost reduction).

### Billing Alarms (3-Tier)

Three escalation levels with strict ordering:

```yaml
# shared/cfn/billing-alarm.yaml
WarningAlarm:    # Monthly spend > $100 → email notification
CriticalAlarm:   # Monthly spend > $200 → email + escalation
EmergencyAlarm:  # Monthly spend > $500 → immediate action required
```

Property Test #7 validates the invariant: `warning < critical < emergency`.

### Auto-Stop Lambda

Runs hourly via EventBridge Schedule, checking all SageMaker Endpoints for idle status:

```python
# Simplified logic
for endpoint in list_endpoints(project_prefix):
    if has_tag(endpoint, "DoNotAutoStop", "true"):
        continue  # Protected endpoint
    if get_invocations_last_n_minutes(endpoint, idle_threshold) == 0:
        scale_to_zero(endpoint)  # Non-destructive: scale down, don't delete
        emit_metric("EndpointsStoppedCount", 1)
```

Key design decisions:
- **Non-destructive**: Scale to zero, never delete (Property Test #9)
- **Tag protection**: `DoNotAutoStop=true` prevents stopping (Property Test #8)
- **DRY_RUN mode**: Log-only mode for safe testing
- **EMF metrics**: `EstimatedSavingsPerHour` for cost visibility

---

## Theme C: CI/CD Pipeline

### Pipeline Architecture

```
PR → main branch
  ├── Stage 1: cfn-lint (all CloudFormation templates)
  ├── Stage 2: pytest + Hypothesis (coverage ≥ 80%)
  ├── Stage 3: cfn-guard (security compliance)
  └── Stage 4: Bandit + pip-audit (code security)
      ↓ All stages pass
  Deploy to Staging (auto)
      ↓ Smoke test passes
  Manual Approval (Environment Protection Rules)
      ↓ Approved
  Deploy to Production
```

### Strict Gating

Property Test #10 validates the gating invariant: if any stage reports "fail", the final pipeline status is "failure". Only when all stages report "pass" does the pipeline succeed.

### OIDC Authentication

No long-lived AWS credentials stored in GitHub:

```yaml
permissions:
  id-token: write
  contents: read

- uses: aws-actions/configure-aws-credentials@v4
  with:
    role-to-assume: arn:aws:iam::${{ secrets.AWS_ACCOUNT_ID }}:role/github-actions-deploy
    aws-region: ap-northeast-1
```

### Deployment Stage Ordering

Property Test #11 validates: production deployment is only permitted when staging succeeds AND smoke tests pass. Staging failure or smoke test failure blocks production.

### Security Rules (cfn-guard)

Five rule files enforce security compliance:

| Rule | Enforcement |
|------|-------------|
| `iam-least-privilege.guard` | No `Action: "*"` + `Resource: "*"` |
| `encryption-required.guard` | KMS encryption on DynamoDB, S3, SNS |
| `lambda-limits.guard` | Timeout ≤ 900s, Memory ≤ 10240MB |
| `no-public-access.guard` | No public S3, no 0.0.0.0/0 SG ingress |
| `sagemaker-security.guard` | VPC config, encryption required |

Property Test #12 validates: any IAM policy with `Action: "*"` AND `Resource: "*"` is flagged as a violation.

---

## Theme D: Multi-Region Architecture

### DynamoDB Global Tables

The Task Token Store (introduced in Phase 4) is extended to a Global Table for cross-region replication:

```yaml
# shared/cfn/global-task-token-store.yaml
Type: AWS::DynamoDB::GlobalTable
Properties:
  TableName: !Sub "${AWS::StackName}-task-token-store"
  BillingMode: PAY_PER_REQUEST
  StreamSpecification:
    StreamViewType: NEW_AND_OLD_IMAGES
  Replicas:
    - Region: ap-northeast-1
      PointInTimeRecoverySpecification:
        PointInTimeRecoveryEnabled: true
    - Region: us-east-1
      PointInTimeRecoverySpecification:
        PointInTimeRecoveryEnabled: true
  TimeToLiveSpecification:
    AttributeName: ttl
    Enabled: true
```

Key properties:
- **Version 2019.11.21**: Latest Global Tables version
- **PAY_PER_REQUEST**: No capacity planning needed
- **TTL propagation**: Automatic across all replicas
- **Strong consistency**: Within-region writes; eventual consistency for cross-region reads

### CrossRegionClient Failover

The `shared/cross_region_client.py` is extended with automatic failover:

```python
def access_with_failover(self, operation, **kwargs):
    """Primary → Secondary automatic failover."""
    try:
        return self._execute(self.primary_region, operation, **kwargs)
    except (TimeoutError, ConnectionError, ServerError) as e:
        self._emit_metric("CrossRegionFailoverCount", 1)
        return self._execute(self.secondary_region, operation, **kwargs)
```

Property Test #13 validates: Primary region is always tried first, and Secondary is only attempted when Primary fails with timeout, 5xx, or connection error.

### Disaster Recovery Tiers

| Tier | RPO | RTO | Strategy | Monthly Cost Premium |
|------|-----|-----|----------|---------------------|
| Tier 1 | 0 | < 5 min | Active-Active (Global Tables + dual SF) | +100% |
| Tier 2 | < 1 hour | < 30 min | Warm Standby (Global Tables + standby Lambda) | +30–50% |
| Tier 3 | < 24 hours | < 4 hours | Backup & Restore (S3 cross-region + manual) | +5–10% |

### Active-Passive Guarantee

Property Test #15 validates: when the Primary region health check is "healthy", the Secondary region does NOT process events. Only when Primary is "unhealthy" does Secondary activate.

### Resource Isolation

Property Test #14 validates: Primary and Secondary region resource names never collide, preventing accidental cross-region interference.

---

## Design Principles

### Opt-in Everything (Continued)

Phase 5 adds new Conditions:

```yaml
Conditions:
  IsServerlessInference: !Equals [!Ref InferenceType, "serverless"]
  HasProvisionedConcurrency: !Not [!Equals [!Ref ServerlessProvisionedConcurrency, "0"]]
  EnableScheduledScalingCondition: !Equals [!Ref EnableScheduledScaling, "true"]
  EnableBillingAlarmsCondition: !Equals [!Ref EnableBillingAlarms, "true"]
  EnableAutoStopCondition: !Equals [!Ref EnableAutoStop, "true"]
  EnableMultiRegionCondition: !Equals [!Ref EnableMultiRegion, "true"]
```

### Non-Breaking Guarantee

Phase 5 additions do not modify any existing Phase 1/2/3/4 code:
- `shared/routing.py` is a new module (not modifying existing files)
- `shared/cost_validation.py` is a new module
- Existing Lambda functions continue to work unchanged
- All existing tests pass without modification

### Property-Based Testing (Hypothesis)

Phase 5 introduces 15 correctness properties:

| # | Property | Validates |
|---|----------|-----------|
| 1 | Three-Way Routing Determinism | Same inputs → same path, always exactly one path |
| 2 | ServerlessConfig Validation | MemorySizeInMB ∈ {1024..6144}, MaxConcurrency ∈ [1,200] |
| 3 | Serverless Invocation Timeout Bound | Total retry time ≤ Step Functions timeout |
| 4 | Inference Type Response Transparency | Both modes return identical key sets |
| 5 | Scheduled Scaling Time Ordering | start < end enforced |
| 6 | Cost Reduction Guarantee | off_hours_max ≤ business_min |
| 7 | Billing Alarm Threshold Ordering | warning < critical < emergency |
| 8 | Auto-Stop Tag Protection | DoNotAutoStop=true → never stopped |
| 9 | Non-Destructive Stop Guarantee | Action is always "scale to zero", never "delete" |
| 10 | CI Strict Gating | Any "fail" → pipeline "failure" |
| 11 | Deployment Stage Ordering | staging success required for production |
| 12 | No Admin Access in IAM Policies | Action:* + Resource:* → violation |
| 13 | Cross-Region Failover Ordering | Primary first, Secondary only on failure |
| 14 | Multi-Region Resource Isolation | No resource name collisions |
| 15 | Active-Passive Guarantee | Secondary inactive when Primary healthy |

---

## Cost Impact

| Feature | Default | Monthly Cost (when enabled) |
|---------|---------|---------------------------|
| Serverless Inference (no PC) | Disabled | $1–300 (request-based) |
| Serverless Inference (PC=1) | Disabled | ~$50–160 (PC fixed cost) |
| Scheduled Scaling | Disabled | $0 (Auto Scaling feature) |
| Billing Alarms | Disabled | ~$0.30 (3 alarms) |
| Auto-Stop Lambda | Disabled | ~$0 (hourly invocation) |
| CI/CD Pipeline | N/A | $0 (GitHub Actions free tier) |
| DynamoDB Global Tables | Disabled | ~$0–5 (PAY_PER_REQUEST) |
| Multi-Region (full) | Disabled | +30–100% of base cost |

---

## Lessons Learned

### 1. Serverless Inference Cold Start is Highly Variable

Cold start latency varies significantly based on model size, container image size, and framework initialization. Our testing showed 6–45 second range for the same endpoint configuration. The retry strategy (3s delay × 2 retries) handles most cases, but the Batch Transform fallback is essential for reliability.

### 2. Scheduled Scaling Requires Timezone Awareness

AWS Application Auto Scaling scheduled actions use UTC by default. For JST-based business hours, the `Timezone` parameter must be explicitly set to `Asia/Tokyo`. Without this, scaling actions fire at wrong times.

### 3. Global Tables Require Stream Specification

DynamoDB Global Tables (Version 2019.11.21) require `StreamSpecification: NEW_AND_OLD_IMAGES`. Attempting to create a Global Table without streams results in a validation error. This is a hard requirement for cross-region replication.

### 4. GitHub Actions OIDC Requires Careful IAM Trust Policy

The OIDC trust policy must match the exact GitHub repository and branch pattern. A common mistake is using `*` for the subject claim, which allows any repository to assume the role. Always scope to the specific repository and branch.

### 5. cfn-guard Rules Need Careful Scoping

Overly broad cfn-guard rules can block legitimate configurations. For example, a blanket "no wildcard actions" rule blocks `logs:CreateLogGroup` which is commonly needed. Rules should target specific high-risk patterns (Action:* + Resource:*) rather than any individual wildcard.

---

## Screenshots

All screenshots are from the ap-northeast-1 (Tokyo) verification environment. Account IDs and environment-specific information have been masked.

### SageMaker Serverless Inference Endpoint

![SageMaker Serverless Endpoint Settings](https://raw.githubusercontent.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/main/docs/screenshots/masked/phase5-sagemaker-serverless-endpoint-settings.png)

> Serverless Inference Endpoint settings: Memory 4096 MB, Max Concurrency 5. No provisioned instances — compute allocated on-demand per request.

![SageMaker Serverless Endpoint Config](https://raw.githubusercontent.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/main/docs/screenshots/masked/phase5-sagemaker-serverless-endpoint-config.png)

> Endpoint Configuration detail showing the ServerlessConfig parameters. This is the third routing option alongside Batch Transform and Real-time Endpoint.

![SageMaker Serverless Endpoint Creating](https://raw.githubusercontent.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/main/docs/screenshots/masked/phase5-sagemaker-serverless-endpoint-creating.png)

> Endpoint creation in progress. After initial creation, the endpoint scales to zero when idle and cold-starts on the first request (6–45 seconds observed).

### CloudWatch Billing Alarms (3-Tier)

![CloudWatch Billing Alarms](https://raw.githubusercontent.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/main/docs/screenshots/masked/phase5-cloudwatch-billing-alarms.png)

> Three-tier billing alarms: Warning ($100), Critical ($200), Emergency ($500). Each tier triggers SNS notification with escalating urgency. All alarms in OK state during verification.

### DynamoDB Global Table (Multi-Region)

![DynamoDB Global Table](https://raw.githubusercontent.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/main/docs/screenshots/masked/phase5-dynamodb-global-table.png)

> DynamoDB Global Table configuration for the Task Token Store. Multi-Region replication enabled between ap-northeast-1 and us-east-1.

![DynamoDB Global Replicas](https://raw.githubusercontent.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/main/docs/screenshots/masked/phase5-dynamodb-global-replicas.png)

> Global Table replica status showing active replication across regions. TTL propagation and PITR enabled on all replicas.

---

## What's Next

- **FSx ONTAP S3 AP native events**: When available, migrate from polling to event-driven with the Phase 4 prototype as the blueprint
- **SageMaker Inference Components**: Explore hosting multiple models on a single endpoint for further cost optimization
- **AWS CDK migration**: Consider migrating from raw CloudFormation to CDK for better abstraction and testing
- **Observability enhancement**: Add distributed tracing across regions with X-Ray cross-region service maps

---

## Impact Assessment

All Phase 5 features are opt-in and disabled by default. For a comprehensive evaluation of the impact on existing environments when enabling features across all phases (1–5), including safe enablement order, rollback procedures, and cost impact summary, see the [Existing Environment Impact Assessment Guide](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/blob/main/docs/impact-assessment-en.md).

---

## Conclusion

Phase 5 transforms the FSxN S3AP Serverless Patterns into a production-ready, cost-optimized, multi-region reference architecture:

- **Serverless Inference** completes the inference routing trifecta, giving operators the right tool for every traffic pattern
- **Cost Optimization Suite** provides automated controls that can reduce SageMaker costs by up to 70%
- **CI/CD Pipeline** enables team collaboration with automated quality gates and safe deployments
- **Multi-Region Architecture** provides resilience patterns from simple backup (Tier 3) to zero-RPO active-active (Tier 1)

All features remain opt-in, maintaining the project's core principle: **learn from the design decisions without paying for resources you don't need**.

**Repository**: [github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns)

---

*This article is part of the "FSx for ONTAP S3 Access Points" series. See [Phase 1](https://dev.to/yoshikifujiwara/fsx-for-ontap-s3-access-points-as-a-serverless-automation-boundary-ai-data-pipelines-ili), [Phase 2](https://dev.to/yoshikifujiwara/9-more-industry-serverless-patterns-with-fsx-for-ontap-s3-access-points-semiconductor-genomics-15e4), [Phase 3](https://dev.to/yoshikifujiwara/near-real-time-processing-ml-inference-and-observability-for-fsx-for-ontap-s3-access-points--bkd), and [Phase 4](https://dev.to/yoshikifujiwara/production-sagemaker-patterns-multi-account-deployment-and-event-driven-architecture-for-fsx-for-ontap-s3-access-points-phase-4) for the foundation.*
