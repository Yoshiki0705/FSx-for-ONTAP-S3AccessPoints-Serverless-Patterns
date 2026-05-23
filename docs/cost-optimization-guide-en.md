# Cost Optimization Best Practices Guide

🌐 **Language / 言語**: [日本語](cost-optimization-guide.md) | [English](cost-optimization-guide-en.md)

## Overview

This document provides cost optimization best practices across all Phases (1–5) of FSxN S3AP Serverless Patterns. It includes monthly cost estimates by deployment profile, a cost reduction checklist, and CloudFormation parameter recommendations.

---

## Component-by-Component Cost Analysis

### Phase 1–2: Foundation Components

| Component | Billing Model | Monthly Estimate (ap-northeast-1) | Optimization Point |
|-----------|--------------|----------------------------------|-------------------|
| Lambda (14 UCs) | Requests + execution time | $1–42 | Memory optimization, reduce execution time |
| Step Functions | State transitions | $0.50–5 | Adjust Map State parallelism |
| EventBridge Scheduler | Number of schedules | $0 (within free tier) | Disable unnecessary schedules |
| S3 API (via S3 AP) | Requests + data transfer | $0.50–10 | Optimize ListObjects page size |
| Secrets Manager | Number of secrets + API calls | $0.50–1 | Leverage caching |
| Interface VPC Endpoints | Hourly + data processing | $0–36 | **Optional** (largest cost factor) |
| S3 Gateway Endpoint | Free | $0 | Always recommended to enable |
| SNS | Number of messages | $0.01–0.50 | — |

### Phase 3: Streaming, ML & Observability

| Component | Billing Model | Monthly Estimate | Optimization Point |
|-----------|--------------|-----------------|-------------------|
| Kinesis Data Streams | Shard hours + PUT records | $15–30/shard | Consider on-demand mode |
| SageMaker Batch Transform | Job execution time | $0–50 (depends on job frequency) | Consolidate small batches |
| X-Ray | Number of traces | $0–5 | Adjust sampling rate |
| CloudWatch EMF | Number of metrics | $0.30/metric | Avoid high cardinality |
| DynamoDB (state table) | RCU/WCU | $0–1 | Auto-cleanup with TTL |

### Phase 4: Production SageMaker & Multi-Account

| Component | Billing Model | Monthly Estimate | Optimization Point |
|-----------|--------------|-----------------|-------------------|
| SageMaker Real-time Endpoint | Instance hours | $215/ml.m5.large | **Scheduled Scaling** |
| DynamoDB Task Token Store | PAY_PER_REQUEST | ~$0 | Auto-delete with 24h TTL |
| Model Registry | Metadata only | $0 | — |
| Event-Driven Prototype | Number of events | ~$0 | — |

### Phase 5: Serverless Inference & Cost Management

| Component | Billing Model | Monthly Estimate | Optimization Point |
|-----------|--------------|-----------------|-------------------|
| SageMaker Serverless Inference | Requests + processing time | $1–300 | MemorySize optimization |
| Serverless PC | PC count × hours | $50–160/PC | Minimize PC count |
| Scheduled Scaling | Free (Auto Scaling feature) | $0 | Scale down outside business hours |
| Billing Alarms | Number of alarms | $0.10/alarm | — |
| Auto-Stop Lambda | Requests + execution time | ~$0 | — |
| DynamoDB Global Tables | Regions × RCU/WCU | $0–2 | PAY_PER_REQUEST |

---

## Deployment Profiles

### Minimal Profile (Monthly ~$3–10)

**Target**: PoC, demos, learning purposes

```yaml
# CloudFormation Parameters
EnableVpcEndpoints: "false"
EnableCloudWatchAlarms: "false"
EnableKinesisStreaming: "false"
EnableRealtimeEndpoint: "false"
EnableABTesting: "false"
EnableModelRegistry: "false"
InferenceType: "none"
EnableScheduledScaling: "false"
EnableBillingAlarms: "false"
EnableAutoStop: "false"
EnableMultiRegion: "false"
```

| Component | Monthly Cost |
|-----------|-------------|
| Lambda (1–2 UCs only) | $0.50–2 |
| Step Functions | $0.25–1 |
| S3 API | $0.50–2 |
| Secrets Manager | $0.50 |
| EventBridge | $0 |
| **Total** | **~$3–10** |

### Standard Profile (Monthly ~$50–150)

**Target**: Development environments, small-scale production

```yaml
# CloudFormation Parameters
EnableVpcEndpoints: "true"
EnableCloudWatchAlarms: "true"
EnableKinesisStreaming: "false"
EnableRealtimeEndpoint: "false"
InferenceType: "serverless"
ServerlessMemorySizeInMB: 4096
ServerlessMaxConcurrency: 5
ServerlessProvisionedConcurrency: 0
EnableScheduledScaling: "false"
EnableBillingAlarms: "true"
BillingWarningThreshold: 100
BillingCriticalThreshold: 200
BillingEmergencyThreshold: 500
EnableAutoStop: "true"
EnableMultiRegion: "false"
```

| Component | Monthly Cost |
|-----------|-------------|
| Lambda (all 14 UCs) | $5–42 |
| Step Functions | $2–5 |
| Interface VPC Endpoints | $36 |
| Serverless Inference | $1–30 |
| CloudWatch Alarms | $1 |
| Billing Alarms | $0.30 |
| Others | $5–10 |
| **Total** | **~$50–150** |

### Full Profile (Monthly ~$300–700)

**Target**: Production environments, high availability requirements

```yaml
# CloudFormation Parameters
EnableVpcEndpoints: "true"
EnableCloudWatchAlarms: "true"
EnableKinesisStreaming: "true"
EnableRealtimeEndpoint: "true"
EnableABTesting: "true"
EnableAutoScaling: "true"
MinCapacity: 1
MaxCapacity: 4
InferenceType: "provisioned"
EnableScheduledScaling: "true"
BusinessHoursStart: 9
BusinessHoursEnd: 18
EnableBillingAlarms: "true"
BillingWarningThreshold: 500
BillingCriticalThreshold: 1000
BillingEmergencyThreshold: 2000
EnableAutoStop: "true"
EnableMultiRegion: "true"
PrimaryRegion: "ap-northeast-1"
SecondaryRegion: "us-east-1"
```

| Component | Monthly Cost |
|-----------|-------------|
| Lambda (all 14 UCs) | $10–42 |
| Step Functions | $3–5 |
| Interface VPC Endpoints | $36 |
| SageMaker Real-time Endpoint | $215–430 |
| Kinesis Data Streams | $15–30 |
| DynamoDB Global Tables | $1–5 |
| CloudWatch (Alarms + Metrics) | $5–10 |
| X-Ray | $2–5 |
| Others | $10–20 |
| **Total** | **~$300–700** |

---

## Cost Reduction Checklist

### 1. Disabling Features via CloudFormation Conditions

The most effective cost reduction is disabling unnecessary features with Conditions:

| Feature | Parameter | Monthly Savings |
|---------|-----------|----------------|
| Interface VPC Endpoints | `EnableVpcEndpoints=false` | ~$36 |
| SageMaker Real-time Endpoint | `EnableRealtimeEndpoint=false` | ~$215+ |
| Kinesis Data Streams | `EnableKinesisStreaming=false` | ~$15–30 |
| A/B Testing (additional variants) | `EnableABTesting=false` | ~$215/variant |
| Multi-Region Replication | `EnableMultiRegion=false` | ~$5–20 |

### 2. Scheduled Scaling (Business Hours Scaling)

Running SageMaker Endpoints only during business hours can reduce costs by up to 60%:

```yaml
# shared/cfn/scheduled-scaling.yaml
BusinessHoursStart: 9    # 09:00 JST scale up
BusinessHoursEnd: 18     # 18:00 JST scale down
EnableWeekendShutdown: "true"  # Weekend shutdown
```

| Configuration | Monthly Cost | Reduction |
|--------------|-------------|-----------|
| 24/7 operation | $215 | — |
| Weekdays 9–18 only | $90 | 58% |
| Weekdays 9–18 + weekend shutdown | $65 | 70% |

### 3. DynamoDB TTL for Automatic Cleanup

Auto-delete Task Token Store records with 24-hour TTL:

```python
# TTL configuration (shared/task_token_store.py)
'ttl': int(time.time()) + 86400  # Auto-delete after 24 hours
```

- Reduces storage costs
- Prevents accumulation of unnecessary data
- Reduces Global Tables replication costs

### 4. Lambda Memory Optimization

Optimizing Lambda memory settings improves the balance between execution time and cost:

| Lambda Type | Recommended Memory | Reason |
|------------|-------------------|--------|
| Discovery Lambda | 256 MB | S3 ListObjects only, low CPU load |
| Processing Lambda (text) | 512 MB | Text processing, moderate CPU |
| Processing Lambda (image) | 1024 MB | Image processing, high CPU |
| Report Lambda | 256 MB | Report generation, low CPU |
| Auto-Stop Lambda | 256 MB | API calls only |
| Realtime Invoke Lambda | 512 MB | SageMaker API calls + retries |

### 5. EventBridge Scheduler Optimization

Reduce unnecessary scheduled executions:

```yaml
# Production: every hour
ScheduleExpression: "rate(1 hour)"

# Development: manual execution only (disable schedule)
ScheduleState: "DISABLED"

# Low frequency: once per day
ScheduleExpression: "rate(1 day)"
```

### 6. Auto-Stop Lambda for Unused Resource Detection

```yaml
# shared/cfn/auto-stop-resources.yaml
IdleThresholdMinutes: 60  # Stop after 60 minutes of zero requests
DryRun: "false"           # Production: actually stop
```

- Automatic scale-down of unused SageMaker Endpoints
- EMF metrics output of estimated savings
- Protectable with `DoNotAutoStop=true` tag

### 7. X-Ray Sampling Rate Adjustment

```yaml
# Development: trace all
TracingConfig:
  Mode: Active

# Production: sampling (cost reduction)
# Set to 5% via X-Ray sampling rules
```

---

## CloudFormation Parameter Matrix

### Recommended Parameters by Cost Profile

| Parameter | Minimal | Standard | Full |
|-----------|---------|----------|------|
| `EnableVpcEndpoints` | false | true | true |
| `EnableCloudWatchAlarms` | false | true | true |
| `EnableKinesisStreaming` | false | false | true |
| `EnableRealtimeEndpoint` | false | false | true |
| `EnableABTesting` | false | false | true |
| `InferenceType` | none | serverless | provisioned |
| `ServerlessMemorySizeInMB` | — | 4096 | — |
| `ServerlessMaxConcurrency` | — | 5 | — |
| `ServerlessProvisionedConcurrency` | — | 0 | — |
| `EnableScheduledScaling` | false | false | true |
| `BusinessHoursStart` | — | — | 9 |
| `BusinessHoursEnd` | — | — | 18 |
| `EnableWeekendShutdown` | — | — | true |
| `EnableBillingAlarms` | false | true | true |
| `BillingWarningThreshold` | — | 100 | 500 |
| `BillingCriticalThreshold` | — | 200 | 1000 |
| `BillingEmergencyThreshold` | — | 500 | 2000 |
| `EnableAutoStop` | false | true | true |
| `IdleThresholdMinutes` | — | 60 | 60 |
| `EnableMultiRegion` | false | false | true |
| **Monthly Estimate** | **$3–10** | **$50–150** | **$300–700** |

---

## Cost Monitoring and Alerts

### 3-Tier Billing Alarm Configuration

```yaml
# shared/cfn/billing-alarm.yaml
WarningThreshold: 100    # Notify when monthly exceeds $100
CriticalThreshold: 200   # Notify when monthly exceeds $200
EmergencyThreshold: 500  # Emergency notify when monthly exceeds $500
```

### Recommended Alert Settings

| Level | Threshold | Action |
|-------|-----------|--------|
| Warning | 70% of budget | Email notification, review costs |
| Critical | 90% of budget | Email + Slack notification, consider stopping unnecessary resources |
| Emergency | 120% of budget | Immediately execute Auto-Stop, escalate |

### Auto-Stop Lambda Metrics

| Metric | Description |
|--------|-------------|
| `EndpointsChecked` | Number of endpoints checked |
| `EndpointsStoppedCount` | Number of endpoints stopped |
| `EstimatedSavingsPerHour` | Estimated hourly savings (USD) |

---

## Step-by-Step Cost Optimization Approach

### Step 1: Visibility (Week 1)

1. Enable Billing Alarms
2. Review cost trends on CloudWatch dashboards
3. Analyze per-service costs in Cost Explorer

### Step 2: Quick Wins (Week 2)

1. Disable unnecessary VPC Endpoints
2. Stop unused SageMaker Endpoints
3. Optimize Lambda memory

### Step 3: Automation (Week 3–4)

1. Configure Scheduled Scaling
2. Enable Auto-Stop Lambda
3. Verify DynamoDB TTL settings

### Step 4: Continuous Optimization (Monthly)

1. Review cost reports
2. Adjust profiles based on usage patterns
3. Evaluate cost impact of new features

---

## Related Documents

- [Cost Structure Analysis](cost-analysis.md)
- [Inference Cost Comparison Guide](inference-cost-comparison.md)
- [Serverless Inference Cold Start Characteristics](serverless-inference-cold-start.md)
- [CI/CD Guide](ci-cd-guide.md)

---

*This document is part of FSxN S3AP Serverless Patterns Phase 5.*
