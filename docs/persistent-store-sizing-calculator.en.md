# FPolicy Persistent Store Sizing Calculator

🌐 **Language / 言語**: [日本語](persistent-store-sizing-calculator.md) | [English](persistent-store-sizing-calculator.en.md)

## Overview

A guide for calculating the volume size and Replay Recovery Time for ONTAP FPolicy Persistent Store (ONTAP 9.14.1+).

## Formulas

### Volume Size

```
required_size = event_rate_per_sec × max_outage_duration_sec × avg_event_size_bytes × safety_factor
```

### Replay Recovery Time

```
replay_recovery_time = buffered_events / sustainable_processing_rate
```

## Sizing Tables

### Volume Size Estimates

| Scenario | Events/sec | Max Outage Duration | Event Size | Safety Factor | Required Capacity | Bufferable Events |
|----------|-----------|-------------------|-----------|--------------|------------------|------------------|
| Dev/Test | 10 | 5 min (300s) | 500 B | 2.0 | 3 MB | ~6,000 |
| Small Production | 50 | 5 min (300s) | 500 B | 2.0 | 15 MB | ~30,000 |
| Medium Production | 100 | 5 min (300s) | 500 B | 2.0 | 30 MB | ~60,000 |
| Large Production | 500 | 10 min (600s) | 500 B | 2.0 | 300 MB | ~600,000 |
| High Load | 1,000 | 10 min (600s) | 500 B | 2.0 | 600 MB | ~1,200,000 |
| Extreme Load | 5,000 | 10 min (600s) | 500 B | 2.0 | 3 GB | ~6,000,000 |

### Replay Recovery Time Estimates

| Buffered Events | Processing Rate | Recovery Time | Notes |
|----------------|----------------|---------------|-------|
| 10,000 | 100 events/sec | 100 sec (< 2 min) | Small scale, catches up immediately |
| 50,000 | 100 events/sec | 500 sec (≈ 8 min) | Medium scale |
| 100,000 | 100 events/sec | 1,000 sec (≈ 17 min) | Large scale |
| 100,000 | 500 events/sec | 200 sec (≈ 3 min) | High-throughput processing |
| 1,000,000 | 100 events/sec | 10,000 sec (≈ 2.8 hours) | Extreme scale, requires design consideration |
| 1,000,000 | 500 events/sec | 2,000 sec (≈ 33 min) | High-throughput + extreme scale |

## Sustainable Processing Rate Constraints

Throughput during replay is determined by the following bottlenecks:

| Component | Constraint | Mitigation |
|-----------|-----------|-----------|
| FPolicy Server (TCP receive) | CPU/memory dependent | Upgrade to t4g.small or larger |
| SQS SendMessage | 3,000 msg/sec per queue | Batch sending (SendMessageBatch) |
| Bridge Lambda (SQS → EventBridge) | Lambda concurrent executions | Set Reserved Concurrency |
| EventBridge PutEvents | 10,000 entries/sec per account | Usually sufficient |
| DynamoDB (Idempotency) | WCU dependent | On-Demand or sufficient WCU |
| Downstream Lambda | Concurrent executions | MaxConcurrency control |

## Recommended Sizes (Quick Reference)

| Deployment Profile | Recommended Volume Size | Expected Scenario |
|-------------------|------------------------|-------------------|
| PoC/Demo | Not required (no Persistent Store) | Event loss acceptable |
| Production | 100 MB - 1 GB | 5 min outage × 100-1000 events/sec |
| Compliance-sensitive | 1 GB - 5 GB | 10 min outage × 1000+ events/sec |

## Configuration Example

```bash
# Create a 1 GB Persistent Store volume
curl -k -u fsxadmin:PASSWORD \
  -X POST "https://<ONTAP_MGMT_IP>/api/storage/volumes" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "fpolicy_persistent_store",
    "svm": {"uuid": "<SVM_UUID>"},
    "size": "1GB",
    "type": "rw",
    "nas": {
      "path": "/fpolicy_persistent_store",
      "security_style": "unix"
    },
    "guarantee": {"type": "none"}
  }'
```

## Monitoring Recommendations

| Metric | Threshold | Action |
|--------|-----------|--------|
| Volume utilization | > 80% | Alert + consider capacity expansion |
| Replay duration | > SLO target | Improve processing rate or expand volume |
| Buffered event count | > 50% of expected maximum | Reduce outage duration or expand capacity |

## Reference Links

- [FPolicy Persistent Store Configuration Guide](event-driven/fpolicy-persistent-store.md)
- [Deployment Profiles](deployment-profiles.md)
- [ONTAP Persistent Store — NetApp Documentation](https://docs.netapp.com/us-en/ontap/nas-audit/persistent-stores.html)
