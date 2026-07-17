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

## Testing

```bash
python3 -m pytest operations/storage-efficiency/tests/ -v
```
