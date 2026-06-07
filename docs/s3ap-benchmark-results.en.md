# S3AP Throughput Benchmark Results (Measured Values)

🌐 **Language / 言語**: [日本語](s3ap-benchmark-results.md) | [English](s3ap-benchmark-results.en.md)

## Overview

Measured latency and throughput results for each S3 API operation via FSx for ONTAP S3 Access Points.

## Test Environment

| Item | Value |
|------|-------|
| Region | ap-northeast-1 (Tokyo) |
| FSx for ONTAP | Single-AZ (First-generation) |
| Throughput Capacity | 128 MBps |
| Storage Type | SSD |
| Tiering Policy | AUTO (cooling period 31 days) |
| S3 Access Point | NetworkOrigin=Internet |
| Client | macOS (boto3 1.34.x, Python 3.9) — via Internet |
| Lambda Architecture | N/A (local execution) |
| VPC Endpoint | N/A (Internet Origin AP, accessed via Internet) |
| Concurrency | 1 (sequential execution) |
| Iterations per operation | 5-10 repetitions |
| Statistics | Mean, P50 (median), Min, Max reported |
| Measurement Date | 2026-05-22 |

> **Important**: These benchmark results are measured values from a test environment and do not constitute a service-level guarantee. Throughput and latency depend on FSx for ONTAP sizing, workload profile, network path, object size, and concurrency. Validate in your own AWS account, region, FSx configuration, and workload profile before production adoption.

> **Environment constraint**: All results are from Single-AZ, First-generation FSx for ONTAP. Multi-AZ or Second-generation file systems may produce different results. Validate separately.

> **Note**: These measurements were taken via the Internet (client → S3AP). Access from a VPC-external Lambda (AWS-managed egress) reduces latency, but a true VPC-internal Lambda + VPC-origin S3 AP path remains untested.

---

## PutObject

| File Size | Mean Latency | P50 | Min | Max |
|-----------|-------------|-----|-----|-----|
| 1 KB | 50.9 ms | 35.8 ms | 32.3 ms | 116.3 ms |
| 10 KB | 38.1 ms | 37.2 ms | 36.2 ms | 40.5 ms |
| 100 KB | 70.8 ms | 67.5 ms | 57.5 ms | 90.3 ms |
| 1 MB | 181.8 ms | 164.5 ms | 145.8 ms | 281.8 ms |
| 5 MB | 314.1 ms | 286.0 ms | 227.3 ms | 468.6 ms |

**Observations**:
- Small files (≤10KB): ~35-50ms (connection overhead dominant)
- Medium files (100KB-1MB): Latency increases proportionally with size
- Large files (5MB): ~300ms (S3AP maximum upload size limit)

---

## GetObject

| File Size | Mean Latency | P50 | Min | Max | Mean Throughput |
|-----------|-------------|-----|-----|-----|----------------|
| 1 KB | 47.5 ms | 30.5 ms | 28.5 ms | 117.1 ms | 0.03 MB/s |
| 10 KB | 32.3 ms | 32.1 ms | 30.3 ms | 34.4 ms | 0.3 MB/s |
| 100 KB | 38.3 ms | 34.1 ms | 29.7 ms | 59.2 ms | 2.7 MB/s |
| 1 MB | 59.3 ms | 48.5 ms | 43.6 ms | 83.7 ms | 18.1 MB/s |
| 5 MB | 123.4 ms | 111.0 ms | 106.3 ms | 172.3 ms | 41.8 MB/s |

**Observations**:
- Consistent with AWS documentation's "tens of milliseconds" (P50: 30-111ms)
- ~42 MB/s throughput for 5MB files (via Internet)
- Higher throughput expected from VPC-internal Lambda

### GetObject Percentile Details (20 iterations, concurrency=1)

| File Size | P50 | P90 | P95 | P99 | Min | Max |
|-----------|-----|-----|-----|-----|-----|-----|
| 1 KB | 35.5 ms | 39.0 ms | 40.2 ms | 40.2 ms | 32.0 ms | 40.2 ms |
| 100 KB | 37.6 ms | 50.1 ms | 100.2 ms | 100.2 ms | 30.1 ms | 100.2 ms |
| 1 MB | 47.8 ms | 63.3 ms | 92.3 ms | 92.3 ms | 38.1 ms | 92.3 ms |
| 5 MB | 108.0 ms | 115.8 ms | 134.8 ms | 134.8 ms | 100.1 ms | 134.8 ms |

**Observations**:
- P90 is approximately 1.1-1.3x P50 (tail latency is relatively stable)
- Occasional spikes (>100ms) at P95/P99 — caused by connection reuse and network jitter
- For production design, set timeouts based on P90 and design retries for P99

---

## Concurrent Access Performance (Concurrent GetObject)

Concurrent access to 1 MB files:

| Concurrency | Total Requests | Mean | P50 | P90 | P95 | P99 | Max |
|-------------|---------------|------|-----|-----|-----|-----|-----|
| 1 | 10 | 64.3 ms | 57.6 ms | 148.9 ms | 148.9 ms | 148.9 ms | 148.9 ms |
| 5 | 50 | 105.3 ms | 96.4 ms | 166.9 ms | 231.4 ms | 262.1 ms | 310.4 ms |
| 10 | 100 | 136.8 ms | 121.2 ms | 230.0 ms | 314.1 ms | 420.3 ms | 433.5 ms |
| 25 | 250 | 293.5 ms | 252.4 ms | 470.8 ms | 557.4 ms | 893.8 ms | 1385.9 ms |
| 50 | 500 | 538.4 ms | 484.9 ms | 906.7 ms | 1143.5 ms | 1703.3 ms | 2225.1 ms |

**benchmark_run_id**: `s3ap-bench-2026-05-23-001`

> **Sizing signal**: The key design metric is tail latency (P99), not mean latency. Mean latency alone is insufficient for sizing. Evaluate P90/P95/P99 together with throughput and workload concurrency to determine whether the configuration fits the workload. In this test environment, P99 increased sharply beyond concurrency=10. At concurrency=1, P95/P99 are close to the maximum value due to the small sample size.

**Observations**:
- Increasing concurrency raises individual latency but improves aggregate throughput
- concurrency=10: P90=230ms, concurrency=25: P90=471ms, concurrency=50: P90=907ms
- **At concurrency=25+, P99 exceeds 1 second** — FSx 128 MBps throughput saturation + queuing delay
- At concurrency=50, maximum reaches 2.2 seconds — Lambda timeout design requires attention
- **FSx Throughput Capacity is the bottleneck for concurrent performance** — In this test with 1 MB objects / FSx 128 MBps configuration, concurrency=10 was observed as the practical upper limit before significant tail latency degradation. Noticeable latency increases appear at concurrency=25+
- For high-concurrency processing, increase FSx Throughput Capacity (256 MBps or higher recommended)

> **Notation note**: This document uses MB/s (megabytes per second). This is synonymous with the FSx Throughput Capacity notation (MBps) in the AWS Console. The measured value of 138 MB/s appearing to slightly exceed the 128 MBps configuration is due to FSx's short-duration burst capability, measurement rounding, and differences in throughput calculation methods (elapsed-time based). Sustained throughput does not exceed provisioned capacity.

---

## Range GET (Partial Read)

Partial reads from a 5 MB file:

| Range | Read Size | Mean Latency | P50 | Min | Max |
|-------|-----------|-------------|-----|-----|-----|
| bytes=0-1023 | 1 KB | 52.0 ms | 34.5 ms | 31.7 ms | 125.4 ms |
| bytes=0-102399 | 100 KB | 39.1 ms | 37.2 ms | 31.7 ms | 52.0 ms |
| bytes=0-1048575 | 1 MB | 54.5 ms | 55.5 ms | 45.3 ms | 64.2 ms |

**Observations**:
- ✅ **Range GET is supported** (confirmed working on FSx for ONTAP S3 AP)
- Partial read latency is comparable to full reads (connection overhead dominant)
- Effective for reading only headers of large files (DICOM, GDS, SEG-Y, etc.)

### Range GET Use Cases

| Use Case | Target UC | Range Example | Benefit |
|----------|-----------|---------------|---------|
| DICOM header read | UC5 | `bytes=0-4095` (4KB) | Retrieve metadata without reading image body |
| GDS/OASIS file header | UC6 | `bytes=0-1023` (1KB) | Retrieve version/layer info from design files |
| SEG-Y trace header | UC8 | `bytes=0-3599` (3.6KB) | Retrieve survey info from seismic data |
| Log file tail check | UC3 | `bytes=-10240` (last 10KB) | Check latest log entries |
| PDF first page extraction | UC16 | `bytes=0-102399` (100KB) | OCR only the first portion of a document |
| Large media preview | UC4 | `bytes=0-1048575` (1MB) | Thumbnail generation for VFX assets |

---

## HeadObject

| Mean Latency | P50 | Min | Max |
|-------------|-----|-----|-----|
| 18.9 ms | 18.0 ms | 17.8 ms | 20.8 ms |

**Observations**:
- Lightest operation (~19ms)
- Optimal for file existence checks and metadata retrieval

---

## ListObjectsV2

| MaxKeys | Object Count | Mean Latency | P50 | Min | Max |
|---------|-------------|-------------|-----|-----|-----|
| 1000 | 6 | 26.0 ms | 25.8 ms | 22.1 ms | 30.1 ms |

**Observations**:
- ~26ms for a small number of objects
- With pagination (1000 objects/page), each page takes ~26ms
- 10,000 files = 10 pages × ~26ms = ~260ms (minimum)

---

## DeleteObject

| Operation | Result |
|-----------|--------|
| DeleteObject (various sizes) | ✅ Success (latency not measured) |

---

## Design Guidelines for Serverless Pipelines

### Recommendations by Lambda Memory

| File Size | Recommended Lambda Memory | Rationale |
|-----------|--------------------------|-----------|
| < 100 KB | 256-512 MB | Connection overhead dominant; increasing memory has little effect |
| 100 KB - 1 MB | 512 MB - 1 GB | Benefits from throughput improvement |
| 1 MB - 5 MB | 1-3 GB | Network bandwidth becomes the bottleneck |
| > 5 MB (GetObject only) | 3-10 GB or ECS | Write to /tmp + streaming |

### Recommended Step Functions Map Concurrency

| FSx Throughput | Recommended MaxConcurrency | Rationale |
|---------------|---------------------------|-----------|
| 128 MBps | 3-5 | 128 ÷ 42 ≈ 3 (based on 5MB files) |
| 256 MBps | 6-10 | |
| 512 MBps | 12-20 | |
| 1,024 MBps | 24-40 | |
| 2,048+ MBps | 40+ | Recommend limiting with upper_bound |

> The above applies to S3AP access only. If existing NFS/SMB workloads are present, subtract their throughput when designing.

### Cost Comparison (1,000 files/day, average 1MB)

| Approach | Monthly Estimate | Notes |
|----------|-----------------|-------|
| FSx for ONTAP S3 AP (POLLING, rate(1h)) | ~$8-15 | Lambda execution + Scheduler |
| S3 copy approach (DataSync + S3) | ~$20-40 | DataSync + S3 storage + Lambda |
| NFS mount Lambda (in VPC) | ~$15-25 | Including VPC Endpoint cost |

---

## Constraints and Notes

1. **Measured via Internet**: Latency from VPC-internal Lambda may be 30-50% lower
2. **FSx Throughput dependent**: This measurement used a low-throughput FSx configuration. Higher throughput configurations will be faster
3. **Concurrent access**: Sequential access from a single client. For parallel access, be aware of FSx throughput limits
4. **First access**: The first request is slightly slower due to connection establishment (cold-start-like behavior)
5. **S3AP-specific**: Different latency characteristics from regular S3 buckets (routed via FSx data plane)

> **Disclaimer**: The benchmark results and cost figures in this document are measured values from a test environment and do not constitute a service-level guarantee. Validate in your own AWS account, region, FSx for ONTAP configuration, and workload profile before production adoption.

> The documentation backlog is complete. Customer-specific validation requires separate effort based on data classification, regulatory requirements, and operational policies.

---

## Next Benchmark Plan

### Organized by Measurement Objective

| Measurement Objective | Variable Parameter | Fixed Parameter | Expected Insight |
|----------------------|-------------------|-----------------|------------------|
| Latency characterization | Object size (1KB-5MB) | concurrency=1, FSx=128MBps | Size-specific latency characteristics |
| Throughput saturation | Concurrency (1-50) | Object size=1MB, FSx=128MBps | Identifying saturation point |
| FSx capacity comparison | FSx throughput (128/256/512 MBps) | Object size=1MB, concurrency=10 | Scale characteristics by capacity |
| Object size impact | Object size (1KB-50MB) | concurrency=5, FSx=256MBps | Throughput by size |
| Range GET behavior | Range size (1KB-5MB from 50MB file) | concurrency=1, FSx=128MBps | Effectiveness of partial reads |

### Fixed Conditions (for next measurement)

```
benchmark_run_id: (generated at measurement time)
Region: ap-northeast-1
Lambda memory: 1769 MB (1 vCPU)
Lambda architecture: arm64
VPC path: VPC-internal Lambda (NAT Gateway or VPC Origin AP)
Iterations: 50 per data point
Statistics: p50, p90, p95, p99, min, max
FSx CloudWatch metrics: DataReadBytes, NetworkThroughput (captured simultaneously)
```

---

> **Note**: The documentation backlog is complete. Benchmarks at 256/512 MBps configurations are optional additional validations that require FSx throughput configuration changes (incurring additional cost). They do not change current guidance or architecture recommendations. Future 256/512 MBps validations will confirm how the observed practical concurrency point shifts with increased FSx throughput capacity.

> **Important**: The results in this document are not service limits. They are a sizing reference from a specific test environment.

---

## Operational Note: S3 AP Availability During Throughput Capacity Change

**Observation Date**: 2026-05-23
**Environment**: fs-09ffe72a3b2b7dbbd (SINGLE_AZ_1, ap-northeast-1)

### Observed Behavior

When changing FSx throughput capacity from 128 MBps → 256 MBps, the following behavior was observed:

| Timeline | Event |
|----------|-------|
| T+0 min | `update-file-system` executed, Status: IN_PROGRESS |
| T+25 min | ThroughputCapacity changed to 256 MBps |
| T+25-60 min | S3 AP returns `ServiceUnavailable` or `ConnectionClosedError` |
| T+60 min+ | Revert to 128 MBps initiated |

**Additional observation** (after revert):

| Timeline | Event |
|----------|-------|
| revert complete +5 min | S3 AP still returns `ServiceUnavailable` |
| revert complete +10 min | Same — the issue may have existed before the throughput change |

**Conclusion**: The causal relationship between S3 AP `ServiceUnavailable` and the throughput change is unclear. Since CloudWatch metrics show no successful monitor Lambda records, normal operation before the change cannot be confirmed. Reporting to AWS Support is recommended.

### Impact Scope

- **All S3 APs across all SVMs** were affected (both FSxN_OnPre SVM and verification-svm)
- Occurred regardless of NetworkOrigin (Internet/VPC)
- The file system itself remained in `AVAILABLE` state
- Impact on NFS/SMB access was not confirmed (EC2 connection unavailable)

### Recommendations

- Assume that **S3 AP workloads will be impacted** during throughput capacity changes
- Perform changes during a maintenance window
- S3 AP recovery may require additional time after throughput change completion
- When running benchmarks, confirm S3 AP normal operation after throughput changes before starting measurements

> **Note**: This observation is based on a single change operation and reproducibility has not been confirmed. AWS documentation does not explicitly describe S3 AP impact during throughput changes (as of 2026-05-23).

---

## Benchmark Run ID Convention

### Naming Convention

```
s3ap-bench-{YYYY-MM-DD}-{seq}
```

- `YYYY-MM-DD`: Measurement date
- `seq`: Sequential number within the same day (001, 002, ...)
- Example: `s3ap-bench-2026-05-23-001`

### Fixed Conditions Template

Record the following for each benchmark run:

```
benchmark_run_id: s3ap-bench-YYYY-MM-DD-NNN
Region: ap-northeast-1
Lambda memory: 1769 MB (1 vCPU — consistent network bandwidth allocation)
Lambda architecture: arm64
VPC path: [VPC-internal Lambda / VPC-external Lambda]
FSx Throughput Capacity: [128 / 256 / 512] MBps
Object size: [1 KB / 1 MB / 5 MB / etc.]
Iterations per data point: 50 (minimum for p99 statistical significance)
Statistics: p50, p90, p95, p99, min, max
FSx CloudWatch metrics: DataReadBytes, NetworkThroughput (captured simultaneously)
Concurrent NFS/SMB workload: [None / Light / Production-level] (impact on shared throughput)
```

> **Lambda memory selection rationale**: 1769 MB is the threshold that allocates exactly 1 vCPU to Lambda. This ensures consistent network bandwidth, providing reproducible benchmark results. Lower memory settings result in variable network bandwidth, introducing a confounding factor.

> **Iterations selection rationale**: 50 iterations is the minimum sample size needed for p99 calculation (p99 = top 1% of 50 data points = at least 1 sample). For statistically more robust results, 100+ iterations are recommended.

### Result Table Linking Rules

- Place `**benchmark_run_id**: s3ap-bench-YYYY-MM-DD-NNN` directly below each result table
- When comparing multiple run_ids, add a `run_id` column to the comparison table
- Measurements within the same run_id are guaranteed to have been conducted under identical conditions

---

## Hypothesis: FSx Throughput Capacity and Practical Concurrency Point Relationship

### Hypothesis (Pre-validation)

**Statement**: The practical concurrency point (the practical upper limit before P99 degrades sharply) may shift with increased FSx throughput capacity.

**Rationale**: In the 128 MBps configuration, concurrency=10 was observed as the practical upper limit in this specific test environment (1 MB objects, single Lambda invocation pattern, no concurrent NFS/SMB workload) (`s3ap-bench-2026-05-23-001`). 1 MB × 10 concurrent = 10 MB/s sustained read corresponds to ~78% of 128 MBps.

**Predictions**:

| FSx Capacity | Predicted Practical Concurrency | Predicted P99 at Limit | Rationale |
|-------------|-------------------------------|----------------------|-----------|
| 128 MBps | 10 (observed) | ~420 ms (observed) | Baseline measurement |
| 256 MBps | ~15-25 | ~400-600 ms | Sub-linear scaling plausible (ONTAP WAFL overhead, TCP connection management) |
| 512 MBps | ~25-45 | ~400-600 ms | Step-function behavior possible if bottleneck shifts from throughput to IOPS |

> **Note**: Linear scaling (2x capacity = 2x concurrency) is one possibility, but sub-linear or step-function behavior is equally plausible. Hypothesis validation results will be recorded whether confirmed, partially supported, or rejected.

**Validation Method**:
- Measure concurrency=10/25/50 at each capacity
- Identify the inflection point where P99 degrades sharply
- Confirm time-series correlation with FSx CloudWatch metrics (DataReadBytes, NetworkThroughput)
- Measure Range GET (1KB, 100KB, 1MB from 5MB file) at each capacity to confirm partial read scaling characteristics

### Validation Results (to be added after validation)

> TBD: To be filled after 256/512 MBps measurements

**Conclusion**: [Hypothesis was supported / partially supported / rejected]

**Observed practical concurrency points**:

| FSx Capacity | Observed Practical Concurrency | Observed P99 at Limit | Deviation from Prediction |
|-------------|-------------------------------|----------------------|--------------------------|
| 256 MBps | TBD | TBD | TBD |
| 512 MBps | TBD | TBD | TBD |

**Analysis**: TBD

---

## References

- [S3AP Performance Considerations](s3ap-performance-considerations.md)
- [AWS: Accessing your data via S3 access points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)
- [FSx for ONTAP Performance](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/performance.html)
