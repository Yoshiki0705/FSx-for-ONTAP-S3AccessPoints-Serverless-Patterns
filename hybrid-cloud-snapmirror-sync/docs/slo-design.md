# SLO Design

[日本語](slo-design-ja.md) | [English](slo-design.md)

Service Level Objectives for the hybrid cloud SnapMirror sync pattern,
designed for CloudWatch Application Signals.

> Reference: [CloudWatch Application Signals SLO](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-ServiceLevelObjectives.html)

## SLO Candidates

| # | SLO Name | SLI Metric | Type | Objective | Window |
|---|----------|-----------|------|-----------|--------|
| 1 | Replication Freshness | QuickDashboardDataAgeSeconds | Period-based | 95% of 5-min periods ≤ 600s | 7 days |
| 2 | S3 AP Availability | S3APCanarySuccess | Period-based | 99% success | 7 days rolling |
| 3 | Quick Insight Readiness | QuickRefreshSuccess | Period-based | 95% success | 7 days rolling |
| 4 | Source-to-Insight Latency | SourceToInsightLatencySeconds | Period-based | p95 ≤ 900s | 7 days |
| 5 | Sync Trigger Reliability | SyncTriggerCount vs SyncFailureCount | Request-based | 95% success | 7 days |

## SLO Detail

### 1. Replication Freshness

- **What it measures**: How fresh the data in Amazon Quick is relative to the source
- **SLI**: Percentage of 5-minute periods where `QuickDashboardDataAgeSeconds ≤ 600`
- **Objective**: 95%
- **Error budget**: 5% of periods (~8.4 hours/week) may exceed 10 minutes
- **Alert threshold**: Error budget burn rate > 2x

### 2. S3 AP Availability

- **What it measures**: Whether the S3 Access Point is reachable and returning data
- **SLI**: CloudWatch Synthetics canary success rate
- **Objective**: 99%
- **Error budget**: ~1.7 hours/week of downtime
- **Alert threshold**: 3 consecutive failures

### 3. Quick Insight Readiness

- **What it measures**: Whether Amazon Quick dataset refreshes are succeeding
- **SLI**: QuickRefreshSuccess count / total attempts
- **Objective**: 95%
- **Error budget**: 5% refresh failures tolerated
- **Alert threshold**: 2 consecutive refresh failures

### 4. Source-to-Insight Latency

- **What it measures**: End-to-end time from source file write to Quick visibility
- **SLI**: SourceToInsightLatencySeconds p95
- **Objective**: p95 ≤ 15 minutes (900 seconds)
- **Error budget**: 5% of measurements may exceed 15 minutes
- **Alert threshold**: p95 > 20 minutes for 2 consecutive periods

### 5. Sync Trigger Reliability

- **What it measures**: Whether one-click sync triggers succeed
- **SLI**: (SyncTriggerCount - SyncFailureCount) / SyncTriggerCount
- **Objective**: 95%
- **Error budget**: 5% of triggers may fail
- **Alert threshold**: 3 consecutive trigger failures

## Implementation Notes

- CloudWatch Application Signals supports both period-based and request-based SLOs
- SLOs automatically create the `AWSServiceRoleForCloudWatchApplicationSignals` service-linked role
- Error budgets are tracked automatically and visible in the Application Signals console
- SLOs can be created via Console, CLI, or CloudFormation (`AWS::ApplicationSignals::ServiceLevelObjective`)

## Demo vs Production PoC Thresholds

| SLO | Demo Threshold | Production PoC Threshold |
|-----|---------------|-------------------------|
| Replication Freshness | data age ≤ 10 min | Customer-defined based on RPO (recommended start: ≤ 15 min) |
| S3 AP Availability | 99% (7-day) | 99.5%+ (customer SLA-aligned) |
| Quick Readiness | 95% refresh success | 99% (production dashboards) |
| Source-to-Insight | p95 ≤ 15 min | Customer-defined (recommended: ≤ 10 min) |
| Sync Reliability | 95% trigger success | 99% (automated schedule) |

> **Caution**: Demo thresholds should not be used as production requirements. Production SLOs must be defined in collaboration with the customer based on their RPO, business criticality, and operational capacity.

## Incident Response Flow

When an SLO error budget is consumed:

1. Check CloudWatch Dashboard (HybridCloudSnapMirrorSync-Readiness)
2. Identify which SLI is degraded
3. Check CloudWatch Logs Insights with correlation_id
4. Check CloudTrail for recent S3 AP / FSx / IAM changes
5. Check SnapMirror relationship health via /api/health
6. Decision: fix root cause or switch to demo fallback
