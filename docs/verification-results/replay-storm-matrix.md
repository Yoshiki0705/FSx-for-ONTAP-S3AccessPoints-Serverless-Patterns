# Replay Storm Test Matrix — Results

## Test Matrix Dimensions

| Dimension | Values |
|-----------|--------|
| Event count | 1,000 / 10,000 |
| Protocol | NFSv3 / NFSv4.1 / SMB |
| Operation | create / modify / delete / rename |
| File size | small (1 KB) / large (100 MB) |
| Downtime duration | 5 min / 30 min / 2 hours |

## Summary Results

| Scenario | Events Queued | Events Replayed | Loss Rate | Throughput (eps) | Duration (s) | OOD Distance | Duplicates | Risk Flag |
|----------|--------------|-----------------|-----------|-----------------|--------------|--------------|------------|-----------|
| [TBD] | | | | | | | | |

## Per-Scenario Details

### Scenario 1: 1000 events / NFSv3 / create / small / 5 min downtime

[TBD — to be filled after live testing]

### Scenario 2: 10000 events / NFSv3 / create / small / 30 min downtime

[TBD — to be filled after live testing]

## ONTAP-Side Observations

### Persistent Store Volume Usage

| Scenario | Before (bytes) | After (bytes) | Delta |
|----------|---------------|---------------|-------|
| [TBD] | | | |

### EMS Log Patterns

[TBD — ONTAP EMS logs captured during testing]

## Conclusions

[TBD — to be written after all scenarios are executed]
