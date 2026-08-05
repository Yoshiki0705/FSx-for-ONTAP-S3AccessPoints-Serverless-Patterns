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

## Output

### CloudWatch custom metrics (namespace: `FSxOps`)

| Metric | Unit | Meaning |
|--------|:----:|---------|
| `VolumesWithoutQoS` | Count | Volumes with no QoS policy assigned |
| `QoSPoliciesWithLimits` | Count | Policies that have a throughput ceiling set |
| `QoSRecommendationCount` | Count | Number of recommendations produced |

### S3 report

Carries a `data_classification` field (default `INTERNAL`, overridable via the
`DATA_CLASSIFICATION` environment variable). Policy and volume names are included;
file contents are not.

## Success Metrics

| Outcome | Metric | Target | Human Review |
|---------|--------|--------|:------------:|
| Reduced contention risk | `VolumesWithoutQoS` | Trending to 0 | ✅ |
| Policy coverage | `QoSPoliciesWithLimits` / total policies | 100% | ✅ |
| Workload isolation | Volumes per policy | 10 or fewer | ✅ |
| Detection latency | Time from an unassigned volume to detection | Within the schedule interval | — |
| Execution stability | Workflow success rate | > 99% | — |

> **On the threshold**: "10 volumes per policy" is a guide for workload isolation,
> not a limit established by performance testing. The tolerable consolidation
> depends on the I/O characteristics of the workloads involved.

## Testing

```bash
python3 -m pytest operations/qos-monitoring/tests/ -v
make test-ops6
```

## Governance Note

This pattern **reads and recommends only**. It does not create, modify or assign
QoS policies.

A QoS ceiling set wrongly throttles a production workload. In particular, the
"no throughput limit → set a ceiling" recommendation does **not** propose the value
itself. Measure the workload's peak I/O before choosing one. A ceiling set too low
produces a slowdown caused by configuration rather than by a fault, which is harder
to diagnose.

A volume flagged as "without QoS" is **not necessarily a problem**. On a file
system dedicated to a single workload, running without a policy can be the right
choice. Treat a recommendation as a starting point for the conversation.

> **Performance note**: this analysis is static and based on QoS configuration.
> Whether contention is actually occurring has to be confirmed with ONTAP
> performance statistics or CloudWatch throughput metrics.
