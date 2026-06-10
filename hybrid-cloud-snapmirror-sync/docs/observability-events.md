# Observability Event Schema

Structured event schema for the hybrid cloud SnapMirror sync pipeline.
All events use JSON format and include a `correlation_id` for end-to-end tracing.

## Common Fields

| Field | Type | Description |
|-------|------|-------------|
| event_type | string | Event category (see below) |
| correlation_id | string | Unique ID linking all events in one sync cycle |
| timestamp | ISO 8601 | When the event occurred |
| environment | string | demo / poc / production |
| status | string | success / failed / in_progress |

## Event Types

### replication_triggered

```json
{
  "event_type": "replication_triggered",
  "correlation_id": "demo-2026-06-10-001",
  "timestamp": "2026-06-10T10:00:00Z",
  "environment": "demo",
  "trigger_source": "one_click_ui",
  "client_ip": "192.168.2.5",
  "snapmirror_uuid": "c9a3c6f5-646f-11f1-bfbc-b752054b9c31",
  "status": "success"
}
```

### replication_completed

```json
{
  "event_type": "replication_completed",
  "correlation_id": "demo-2026-06-10-001",
  "timestamp": "2026-06-10T10:00:05Z",
  "environment": "demo",
  "source_volume": "svm_source:vol_source",
  "destination_volume": "svm_dest:vol_dest",
  "bytes_transferred": 7232,
  "duration_seconds": 5,
  "lag_seconds": 0,
  "status": "success"
}
```

### replication_failed

```json
{
  "event_type": "replication_failed",
  "correlation_id": "demo-2026-06-10-002",
  "timestamp": "2026-06-10T10:05:00Z",
  "environment": "demo",
  "error_code": 6619986,
  "error_message": "No common snapshot found",
  "snapmirror_uuid": "c9a3c6f5-646f-11f1-bfbc-b752054b9c31",
  "status": "failed"
}
```

### s3ap_canary

```json
{
  "event_type": "s3ap_canary",
  "correlation_id": "canary-2026-06-10-001",
  "timestamp": "2026-06-10T10:01:00Z",
  "environment": "demo",
  "s3_access_point": "ap-demo-alias",
  "operation": "ListObjectsV2",
  "latency_ms": 145,
  "object_count": 12,
  "status": "success"
}
```

### quick_refresh

```json
{
  "event_type": "quick_refresh",
  "correlation_id": "demo-2026-06-10-001",
  "timestamp": "2026-06-10T10:06:00Z",
  "environment": "demo",
  "dataset_id": "quick-dataset-001",
  "refresh_duration_seconds": 45,
  "records_processed": 150,
  "status": "success"
}
```

## CloudWatch Logs Insights Queries

### Latest replication status

```sql
fields @timestamp, correlation_id, event_type, status, lag_seconds, bytes_transferred
| filter event_type = "replication_completed" or event_type = "replication_failed"
| sort @timestamp desc
| limit 20
```

### Failed S3 AP canary checks

```sql
fields @timestamp, correlation_id, s3_access_point, operation, status, latency_ms, error_message
| filter event_type = "s3ap_canary"
| filter status != "success"
| sort @timestamp desc
| limit 50
```

### Trace a full sync cycle by correlation_id

```sql
fields @timestamp, event_type, correlation_id, status, duration_seconds, lag_seconds, error_message
| filter correlation_id = "demo-2026-06-10-001"
| sort @timestamp asc
```

### Average source-to-insight latency

```sql
fields @timestamp, correlation_id, lag_seconds
| filter event_type = "replication_completed"
| stats avg(lag_seconds) as avg_lag, max(lag_seconds) as max_lag, p95(lag_seconds) as p95_lag by bin(1h)
```

> Reference: [CloudWatch Logs Insights Query Syntax](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CWL_QuerySyntax.html)

### Generic: Trace any sync cycle (copy-paste and replace ID)

```sql
fields @timestamp, event_type, correlation_id, replication_cycle_id, status, lag_seconds, data_age_seconds
| filter correlation_id = "REPLACE_WITH_CORRELATION_ID"
| sort @timestamp asc
```

> **Start here**: When investigating an issue, paste the `correlation_id` from the audit log or alarm notification into this query to see the full timeline of events for that sync cycle.
