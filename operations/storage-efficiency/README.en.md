# OPS2: Storage Efficiency

🌐 **Language / 言語**: [日本語](README.md) | English

## Overview

Tracks deduplication and compression efficiency ratios for FSx for ONTAP volumes
and recommends enabling or tuning storage efficiency features on low-efficiency volumes.

## Recommendation Logic

| State | Recommendation |
|-------|----------------|
| dedupe=off, compression=off | Enable both (estimated 2:1 ratio) |
| Enabled but ratio < MinEfficiencyRatio | Review data patterns |
| High efficiency (ratio ≥ 1.5) | No recommendation |

## Output

### CloudWatch custom metrics (namespace: `FSxOps`)

| Metric | Unit | Meaning |
|--------|:----:|---------|
| `AvgEfficiencyRatio` | None | Mean of logical capacity / physical capacity |
| `TotalDedupSavingsGB` | Gigabytes | Capacity saved by deduplication + compression |
| `EfficiencyRecommendationCount` | Count | Number of recommendations produced |

### S3 report

Carries a `data_classification` field (default `INTERNAL`, overridable via the
`DATA_CLASSIFICATION` environment variable). Efficiency ratios and volume
configuration are operational metadata; file contents are not included.

## Success Metrics

| Outcome | Metric | Target | Human Review |
|---------|--------|--------|:------------:|
| Storage cost reduction | Savings (`TotalDedupSavingsGB`) | Increases vs. before enabling | ✅ |
| Efficiency visibility | Share of volumes with a retrievable ratio | 100% | — |
| Recommendation quality | Share of recommendations adopted | > 60% | ✅ |
| Execution stability | Workflow success rate | > 99% | — |
| Detection latency | Time from efficiency drop to detection | Within the schedule interval | — |

> **On these targets**: they are operational guides, not benchmark results. The
> achievable ratio varies widely with the data pattern, so use your first run as
> the baseline and adjust from there.

## Testing

```bash
python3 -m pytest operations/storage-efficiency/tests/ -v
make test-ops2
```

## Governance Note

This pattern **reads and recommends only**. It does not change deduplication or
compression settings; applying a recommendation is a human decision and a human
action.

Enabling deduplication and compression does not affect existing data until the
next background scan. An efficiency ratio that does not improve immediately after
enabling is expected. Compression also consumes CPU, so validate the impact in a
test environment for latency-sensitive workloads.

The 2:1 estimate is a general guide. Encrypted data and already-compressed media
gain almost nothing. The savings figure in a recommendation is an estimate, not a
commitment.

> **Compliance note**: the output is a technical signal for operational
> improvement. It is neither a contractual cost-saving guarantee nor an audit
> record. If it informs a regulatory decision, route it through your compliance
> function first.
