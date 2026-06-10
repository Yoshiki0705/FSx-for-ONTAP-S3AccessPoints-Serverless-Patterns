# AWS-Native Observability Design

This document defines the observability architecture for the hybrid cloud SnapMirror sync pattern using AWS-native services only.

> This observability design does not require third-party observability platforms. The goal is to make the hybrid data pipeline **explainable** using AWS-native services — so that any operator can answer "Is the data fresh? Is the pipeline healthy? What failed and why?" at any point in time.

## AWS Services Used

| Service | Role |
|---------|------|
| Amazon CloudWatch Metrics | Custom metrics (EMF), SnapMirror lag, data age |
| Amazon CloudWatch Logs | Structured event logs from Sync Server |
| Amazon CloudWatch Logs Insights | Ad-hoc investigation and correlation |
| Amazon CloudWatch Dashboards | Operational readiness dashboard |
| Amazon CloudWatch Alarms | Threshold alerting on lag, failures |
| Amazon CloudWatch Synthetics | External canary for S3 AP / UI health |
| CloudWatch Application Signals | SLO tracking for data freshness |
| AWS X-Ray | Distributed tracing across sync pipeline |
| AWS Distro for OpenTelemetry (ADOT) | Instrumentation collector |
| AWS CloudTrail | API audit trail |

## CloudWatch Custom Metrics (Namespace: HybridCloud/SnapMirrorSync)

| Metric | Unit | Description |
|--------|------|-------------|
| SnapMirrorLagSeconds | Seconds | Time since last successful replication |
| LastReplicationAgeSeconds | Seconds | Age of the latest replicated data |
| S3APCanarySuccess | Count | 1 = success, 0 = failure per canary run |
| S3APListLatencyMs | Milliseconds | ListObjectsV2 response time via S3 AP |
| S3APGetLatencyMs | Milliseconds | GetObject response time via S3 AP |
| QuickRefreshSuccess | Count | 1 = dataset refresh succeeded |
| QuickDashboardDataAgeSeconds | Seconds | Time since Quick dashboard data was updated |
| SourceToInsightLatencySeconds | Seconds | End-to-end: source write to Quick visibility |
| SyncTriggerCount | Count | Number of one-click sync triggers |
| SyncFailureCount | Count | Number of failed sync attempts |

### Dimensions

| Dimension | Values | Purpose |
|-----------|--------|---------|
| Environment | demo, poc, production | Separate metrics by stage |
| Volume | vol_source, vol_dest | Track per-volume metrics |
| SVMName | svm_source, svm_dest | SVM-level attribution |

> **Note**: Avoid high-cardinality dimensions (e.g., request_id, user_id) in CloudWatch metrics to control costs. Use structured logs for high-cardinality correlation.

## CloudWatch Dashboard: HybridCloudSnapMirrorSync-Readiness

| Widget | Metric / Source | Purpose |
|--------|----------------|---------|
| SnapMirror Lag | SnapMirrorLagSeconds | Current replication delay |
| Last Replication | LastReplicationAgeSeconds | When data was last synced |
| S3 AP Canary | S3APCanarySuccess (sum/period) | External health check |
| S3 AP Latency | S3APListLatencyMs p50/p95/p99 | Performance baseline |
| Quick Refresh | QuickRefreshSuccess | Dataset freshness |
| Data Age | QuickDashboardDataAgeSeconds | Business data staleness |
| Source-to-Insight | SourceToInsightLatencySeconds p95 | End-to-end SLI |
| Sync Triggers | SyncTriggerCount | Usage pattern |
| Failures | SyncFailureCount | Error rate |
| Demo Readiness | Composite (all green = ready) | Go/no-go for demo |

## Embedded Metric Format (EMF) Example

The Sync Server emits structured logs with embedded metrics:

```json
{
  "_aws": {
    "Timestamp": 1718006400000,
    "CloudWatchMetrics": [{
      "Namespace": "HybridCloud/SnapMirrorSync",
      "Dimensions": [["Environment", "Volume"]],
      "Metrics": [
        {"Name": "SnapMirrorLagSeconds", "Unit": "Seconds"},
        {"Name": "SyncTriggerCount", "Unit": "Count"}
      ]
    }]
  },
  "Environment": "demo",
  "Volume": "vol_source",
  "SnapMirrorLagSeconds": 3,
  "SyncTriggerCount": 1,
  "correlation_id": "demo-2026-06-10-001",
  "event_type": "sync_completed",
  "status": "success"
}
```

> Reference: [CloudWatch Embedded Metric Format Specification](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Embedded_Metric_Format_Specification.html)

## CloudWatch Synthetics Canaries

| Canary | Type | Schedule | Validates |
|--------|------|----------|-----------|
| S3AP-List | API canary | 5 min | ListObjectsV2 via S3 AP alias returns objects |
| S3AP-Get | API canary | 5 min | GetObject of health marker file succeeds |
| SyncUI-Health | Heartbeat | 5 min | Sync Server /api/health returns status: ok |

> Reference: [CloudWatch Synthetics Blueprints](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Synthetics_Canaries_Blueprints.html)

## X-Ray / ADOT Tracing

For production deployments, instrument the Sync Server with ADOT to trace:
- HTTP request → ONTAP REST API call → SnapMirror trigger → status polling → completion

Annotations for X-Ray:
- `snapmirror.uuid`
- `transfer.state`
- `transfer.bytes`
- `environment`

> Reference: [AWS Distro for OpenTelemetry](https://docs.aws.amazon.com/xray/latest/devguide/xray-concepts-tracingheader.html)
