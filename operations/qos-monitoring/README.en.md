# OPS6: QoS Monitoring

🌐 **Language / 言語**: [日本語](README.md) | English

## Overview

Monitors QoS policy compliance for FSx for ONTAP, detects bandwidth contention
(noisy-neighbor) risks, and recommends workload isolation.

## Detections

| Detection | Severity | Description |
|-----------|:--------:|-------------|
| Volumes without QoS policy | Medium | No policy = unlimited bandwidth → affects other workloads |
| Policies without throughput limits | Low | No max_throughput → burst contention risk |
| Many volumes on single policy | Low | 10+ volumes sharing → recommend splitting |

## Testing

```bash
python3 -m pytest operations/qos-monitoring/tests/ -v
```
