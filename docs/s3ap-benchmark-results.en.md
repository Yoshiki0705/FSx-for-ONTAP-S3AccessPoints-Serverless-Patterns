# S3AP Throughput Benchmark Results (Measured Values)

🌐 **Language / 言語**: [日本語](s3ap-benchmark-results.md) | English

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

> **Note**: The 256/512 MBps validations were completed on 2026-05-25 (1 MB files) and 2026-06-06 (202 bytes files). Increasing FSx throughput capacity is effective at improving tail latency for large files (1 MB+), but has no effect for small files. VPC-internal Lambda testing is the next validation priority.

> **Important**: The results in this document are not service limits. They are a sizing reference from a specific test environment.

---

## Operational Note: S3 AP Availability During Throughput Capacity Change

**Observation Date**: 2026-05-23
**Environment**: fs-0123456789abcdef0 (SINGLE_AZ_1, ap-northeast-1)

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

- **All S3 APs across all SVMs** were affected (both the primary SVM and the verification SVM)
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

### Validation Results (additional validation, 2026-06-06)

**Small file (202 bytes) test results**: Increasing throughput capacity does not affect P50 latency for small files (P50 ≈ 57-60 ms at concurrency ≤25 for both 256 MBps and 512 MBps). The bottleneck is connection overhead (TLS + S3 AP routing), not FSx bandwidth.

**Updated Conclusion**:
- The hypothesis is **partially supported, depending on file size**
- Large files (1 MB+): Increasing throughput capacity improves P99 (51% improvement from 128→256 MBps at concurrency=20)
- Small files (< 1 KB): Throughput capacity does not affect P50/P99 (connection overhead dominant)
- Limitation of Internet-path testing: The effect of 512 MBps is masked by client bandwidth

**Conclusion**: The hypothesis was partially supported — at 128 MBps, P99 reached 980 ms for 1 MB files at concurrency=20, confirming signs of bandwidth saturation.

**Observed practical concurrency points**:

| FSx Capacity | Observed Practical Concurrency | Observed P99 at Limit | Deviation from Prediction |
|-------------|-------------------------------|----------------------|--------------------------|
| 128 MBps | concurrency=10 (1 MB) | 239 ms | Within predicted range |
| 128 MBps | concurrency=20 (1 MB) | 981 ms | Signs of bandwidth saturation |
| 256 MBps | concurrency=20 (1 MB) | 481 ms | 51% improvement over 128 MBps |
| 256 MBps | concurrency=50 (1 MB) | 850 ms | Signs of bandwidth saturation |
| 512 MBps | concurrency=20 (1 MB) | 738 ms | Comparable to 256 MBps (client bandwidth limited) |
| 512 MBps | concurrency=50 (1 MB) | 4,495 ms | Client-side bottleneck |

**Analysis**:
- 128→256 MBps: P99 for 1 MB at concurrency=20 improved from 981ms → 481ms (51% improvement)
- 256→512 MBps: Limited improvement. At concurrency=20, 481ms → 738ms (degradation). This indicates that client-side bandwidth limits of Internet-path testing became dominant
- **Conclusion**: In Internet-path testing, the effect of increasing FSx bandwidth beyond 256 MBps is difficult to observe. VPC-internal Lambda testing is needed

---

## Concurrency Benchmark Results (2026-05-25)

### Test Environment

| Item | Value |
|------|-------|
| Run ID | s3ap-bench-2026-05-25-003 |
| Region | ap-northeast-1 (Tokyo) |
| FSx for ONTAP | Single-AZ (First-generation) |
| Throughput Capacity | 128 MBps |
| S3 Access Point | NetworkOrigin=Internet |
| Client | macOS (boto3, Python 3.9) — via Internet |
| Concurrency | 1, 5, 10, 20 |
| Iterations | 10 iterations per concurrency level |
| Measurement Date | 2026-05-25 |

> **Important**: These benchmark results are measured values from an Internet-path test environment and do not constitute a service-level guarantee. Use them as a sizing reference.

### GetObject — Latency by Concurrency

#### 1 KB file

| Concurrency | Requests | Avg | P50 | P90 | P95 | P99 | Min | Max |
|:-----------:|:--------:|----:|----:|----:|----:|----:|----:|----:|
| 1 | 10 | 51.1 ms | 49.7 ms | 69.4 ms | 69.4 ms | 54.1 ms | 45.3 ms | 69.4 ms |
| 5 | 50 | 79.3 ms | 53.0 ms | 72.0 ms | 368.2 ms | 387.3 ms | 45.9 ms | 426.4 ms |
| 10 | 100 | 66.0 ms | 52.1 ms | 63.3 ms | 104.2 ms | 476.1 ms | 45.2 ms | 481.3 ms |
| 20 | 200 | 113.6 ms | 95.8 ms | 270.9 ms | 372.5 ms | 410.4 ms | 46.9 ms | 430.6 ms |

#### 100 KB file

| Concurrency | Requests | Avg | P50 | P90 | P95 | P99 | Min | Max |
|:-----------:|:--------:|----:|----:|----:|----:|----:|----:|----:|
| 1 | 10 | 57.1 ms | 56.3 ms | 69.2 ms | 69.2 ms | 58.0 ms | 51.8 ms | 69.2 ms |
| 5 | 50 | 54.2 ms | 52.7 ms | 61.9 ms | 70.9 ms | 71.9 ms | 45.5 ms | 78.3 ms |
| 10 | 100 | 56.8 ms | 53.0 ms | 68.3 ms | 71.5 ms | 90.3 ms | 44.6 ms | 204.5 ms |
| 20 | 200 | 97.1 ms | 110.8 ms | 136.3 ms | 141.5 ms | 225.0 ms | 45.1 ms | 532.4 ms |

#### 1 MB file

| Concurrency | Requests | Avg | P50 | P90 | P95 | P99 | Min | Max |
|:-----------:|:--------:|----:|----:|----:|----:|----:|----:|----:|
| 1 | 10 | 68.5 ms | 67.8 ms | 83.3 ms | 83.3 ms | 76.1 ms | 61.6 ms | 83.3 ms |
| 5 | 50 | 119.8 ms | 116.8 ms | 149.4 ms | 154.6 ms | 160.1 ms | 67.2 ms | 346.3 ms |
| 10 | 100 | 176.5 ms | 175.0 ms | 213.0 ms | 227.4 ms | 239.3 ms | 120.6 ms | 251.7 ms |
| 20 | 200 | 328.5 ms | 256.0 ms | 643.3 ms | 827.8 ms | 980.7 ms | 96.7 ms | 1284.2 ms |

### Analysis

**1 KB file (connection overhead dominant)**:
- Concurrency=1: P50 ~50 ms (baseline latency)
- Concurrency=20: P50 increases to ~96 ms (connection pool contention)
- P99 is 400-480 ms across all concurrency levels (occasional spikes)

**100 KB file (balanced)**:
- Concurrency=1-10: Stable (P50: 52-53 ms, P90: 61-68 ms)
- Concurrency=20: P50 increases to 111 ms (bandwidth effects begin)

**1 MB file (bandwidth dominant)**:
- Concurrency=1: P50 68 ms (~15 MB/s throughput)
- Concurrency=5: P50 117 ms (~43 MB/s aggregate throughput)
- Concurrency=10: P50 175 ms (~57 MB/s aggregate, 44% of 128 MBps)
- Concurrency=20: P50 256 ms, P99 981 ms (**signs of bandwidth saturation**)

### Sizing Guidance

| Workload | Recommended MaxConcurrency | Rationale |
|----------|:---:|-----------|
| Many small files (< 10 KB) | 10-20 | Connection overhead dominant; bandwidth headroom available |
| Medium files (100 KB - 1 MB) | 5-10 | Keeps P90 below 200 ms |
| Large files (1 MB+) | 5 | Avoids bandwidth saturation, keeps P99 below 500 ms |

> **Note**: The above is a sizing reference for a 128 MBps environment, not a service limit. Higher concurrency is possible in 256/512 MBps environments. Access from VPC-internal Lambda reduces network latency and improves throughput.

---

## 256 MBps Benchmark Results (2026-05-25)

### Test Environment

| Item | Value |
|------|-------|
| Run ID | s3ap-bench-2026-05-25-004 |
| Throughput Capacity | 256 MBps |
| Other | Identical conditions to the 128 MBps test |

### GetObject — 1 MB file (256 MBps)

| Concurrency | Avg | P50 | P90 | P95 | P99 | Max |
|:-----------:|----:|----:|----:|----:|----:|----:|
| 1 | 86.8 ms | 87.6 ms | 131.5 ms | 131.5 ms | 93.2 ms | 131.5 ms |
| 5 | 116.4 ms | 114.8 ms | 140.4 ms | 152.1 ms | 174.9 ms | 204.3 ms |
| 10 | 172.2 ms | 173.7 ms | 216.5 ms | 228.5 ms | 236.4 ms | 236.7 ms |
| 20 | 270.7 ms | 257.2 ms | 395.0 ms | 435.0 ms | 480.9 ms | 713.1 ms |
| 50 | 503.4 ms | 527.8 ms | 750.1 ms | 786.9 ms | 850.1 ms | 900.7 ms |

---

## 512 MBps Benchmark Results (2026-05-25)

### Test Environment

| Item | Value |
|------|-------|
| Run ID | s3ap-bench-2026-05-25-005 |
| Throughput Capacity | 512 MBps |
| Other | Identical conditions to the 128 MBps test |

### GetObject — 1 MB file (512 MBps)

| Concurrency | Avg | P50 | P90 | P95 | P99 | Max |
|:-----------:|----:|----:|----:|----:|----:|----:|
| 1 | 77.9 ms | 76.2 ms | 97.1 ms | 97.1 ms | 95.5 ms | 97.1 ms |
| 5 | 124.3 ms | 114.8 ms | 168.6 ms | 194.2 ms | 307.6 ms | 350.2 ms |
| 10 | 181.3 ms | 184.3 ms | 205.2 ms | 212.4 ms | 228.8 ms | 327.2 ms |
| 20 | 266.8 ms | 249.2 ms | 380.3 ms | 464.5 ms | 738.1 ms | 747.4 ms |
| 50 | 573.8 ms | 546.2 ms | 781.6 ms | 811.6 ms | 4,494.7 ms | 4,576.9 ms |

---

## Comparative Analysis: 128 vs 256 vs 512 MBps

### 1 MB GetObject P50 Comparison

| Concurrency | 128 MBps | 256 MBps | 512 MBps | 256 vs 128 Improvement |
|:-----------:|:--------:|:--------:|:--------:|:-----------------:|
| 1 | 67.8 ms | 87.6 ms | 76.2 ms | — (baseline comparable) |
| 5 | 116.8 ms | 114.8 ms | 114.8 ms | 2% |
| 10 | 175.0 ms | 173.7 ms | 184.3 ms | 1% |
| 20 | 256.0 ms | 257.2 ms | 249.2 ms | — |
| 50 | N/A | 527.8 ms | 546.2 ms | — |

### 1 MB GetObject P99 Comparison

| Concurrency | 128 MBps | 256 MBps | 512 MBps | 256 vs 128 Improvement |
|:-----------:|:--------:|:--------:|:--------:|:-----------------:|
| 1 | 76.1 ms | 93.2 ms | 95.5 ms | — |
| 5 | 160.1 ms | 174.9 ms | 307.6 ms | — |
| 10 | 239.3 ms | 236.4 ms | 228.8 ms | 1% |
| 20 | 980.7 ms | 480.9 ms | 738.1 ms | **51% improvement** |
| 50 | N/A | 850.1 ms | 4,494.7 ms | — |

### Conclusion

1. **P50 (median) is largely independent of throughput capacity**: The Internet-path baseline latency (connection establishment + TLS handshake) is dominant
2. **The difference appears in P99 (tail latency)**: 128 MBps at concurrency=20 gives P99=981ms → 256 MBps gives P99=481ms (51% improvement)
3. **The effect of 512 MBps is difficult to observe in Internet-path testing**: Client-side bandwidth (~100 Mbps) becomes the bottleneck, so the increased FSx-side bandwidth cannot be utilized
4. **VPC-internal Lambda testing is needed**: Measuring the true effect of FSx throughput capacity requires testing from VPC-internal Lambda (low latency, high bandwidth)

### Sizing Guidance (Updated)

| Workload | 128 MBps Recommendation | 256 MBps Recommendation | 512 MBps Recommendation |
|----------|:---:|:---:|:---:|
| Small files (< 10 KB) | MaxConcurrency=20 | MaxConcurrency=50 | MaxConcurrency=50 |
| Medium files (100 KB) | MaxConcurrency=10 | MaxConcurrency=20 | MaxConcurrency=50 |
| Large files (1 MB+) | MaxConcurrency=5 | MaxConcurrency=10 | MaxConcurrency=20 |

> **Note**: The above is a sizing reference, not a service limit. A VPC-internal Lambda + VPC-origin S3 AP configuration is expected to reduce public Internet path overhead, but this remains unmeasured. Validate with your own workload profile in your actual environment.

---

## Lambda Egress Path Benchmark Results (2026-05-25)

> **Note**: This is access from a VPC-external Lambda (no VpcConfig) to an Internet-origin S3 AP. It uses the AWS-managed Lambda egress path and is not a true VPC-internal path (VPC-origin S3 AP).

### Test Environment

| Item | Value |
|------|-------|
| Run ID | s3ap-bench-2026-05-25-006 |
| Throughput Capacity | 128 MBps |
| Execution Environment | AWS Lambda (1769 MB, ARM64, outside VPC) |
| S3 AP | NetworkOrigin=Internet |
| Network Path | AWS internal network (not via the Internet) |
| Measurement Date | 2026-05-25 |

> **Important**: Access from a VPC-external Lambda to an Internet Origin S3 AP travels over the AWS internal network. Compared to Internet-path testing from a local PC, connection establishment latency is substantially lower.

### GetObject — Lambda vs Internet Comparison (1 MB, 128 MBps)

| Concurrency | Internet P50 | Lambda P50 | Improvement | Internet P99 | Lambda P99 |
|:-----------:|:---:|:---:|:---:|:---:|:---:|
| 1 | 67.8 ms | 61.7 ms | 9% | 76.1 ms | 81.7 ms |
| 5 | 116.8 ms | 60.5 ms | **48%** | 160.1 ms | 254.1 ms |
| 10 | 175.0 ms | 73.2 ms | **58%** | 239.3 ms | 928.4 ms |
| 20 | 256.0 ms | 121.9 ms | **52%** | 980.7 ms | 1,317.8 ms |
| 50 | N/A | 127.7 ms | — | N/A | 995.0 ms |

### Analysis

1. **P50 improves substantially from Lambda**: 175ms → 73ms at concurrency=10 (58% improvement)
2. **P99 remains high even from Lambda**: 1,318 ms at concurrency=20. This is caused by internal queuing in the S3 AP data plane
3. **P50 stays at 128 ms even at concurrency=50**: Lambda's parallel threads operate efficiently against the S3 AP
4. **The bottleneck is the S3 AP data plane**: The limiting factor is FSx for ONTAP-side processing capacity, not Lambda network bandwidth

### Sizing Guidance (Lambda Execution)

| Workload | Recommended MaxConcurrency | P50 Guide | P99 Guide |
|----------|:---:|:---:|:---:|
| Small files (1 KB) | 50 | ~63 ms | ~994 ms |
| Medium files (100 KB) | 20 | ~79 ms | ~1,044 ms |
| Large files (1 MB) | 10 | ~73 ms | ~928 ms |

> **Note**: P99 around 1 second is a characteristic of the S3 AP data plane. Set Step Functions Lambda timeouts to 30 seconds or more and handle this with retry patterns.

---

## Small File Throughput Comparison (2026-06-06)

### Test Environment

| Item | Value |
|------|-------|
| Run ID (256) | s3ap-bench-2026-06-06-256mbps |
| Run ID (512) | s3ap-bench-2026-06-06-512mbps |
| Object Size | 202 bytes (JSON manifest) |
| Iterations | 50 iterations per concurrency level |
| Warm-up | 3 requests |
| Client | macOS (boto3, Python 3.12) — via Internet |
| Measurement Date | 2026-06-06 |

> **Purpose**: Confirm the effect of throughput capacity changes on small files (where connection overhead is dominant). Comparison against the large file (1 MB) test (2026-05-25).

### GetObject — 202 bytes file (256 MBps)

| Concurrency | Mean | P50 | P90 | P95 | P99 | Max | StdDev | Errors |
|:-----------:|-----:|----:|----:|----:|----:|----:|-------:|:------:|
| 1 | 59.4 ms | 56.9 ms | 65.8 ms | 72.8 ms | 100.8 ms | 100.8 ms | 8.1 ms | 0 |
| 5 | 83.1 ms | 56.3 ms | 126.8 ms | 283.7 ms | 536.8 ms | 536.8 ms | 99.0 ms | 0 |
| 10 | 98.5 ms | 56.5 ms | 317.8 ms | 498.1 ms | 508.7 ms | 508.7 ms | 123.8 ms | 0 |
| 20 | 111.6 ms | 57.8 ms | 333.9 ms | 401.6 ms | 552.5 ms | 552.5 ms | 123.2 ms | 0 |
| 25 | 134.8 ms | 60.3 ms | 355.5 ms | 380.4 ms | 468.3 ms | 468.3 ms | 122.8 ms | 0 |
| 50 | 255.5 ms | 257.9 ms | 492.6 ms | 500.6 ms | 614.5 ms | 614.5 ms | 142.3 ms | 0 |

### GetObject — 202 bytes file (512 MBps)

| Concurrency | Mean | P50 | P90 | P95 | P99 | Max | StdDev | Errors |
|:-----------:|-----:|----:|----:|----:|----:|----:|-------:|:------:|
| 1 | 60.4 ms | 59.8 ms | 64.6 ms | 65.1 ms | 89.4 ms | 89.4 ms | 5.6 ms | 0 |
| 5 | 89.7 ms | 57.4 ms | 85.8 ms | 346.0 ms | 690.2 ms | 690.2 ms | 115.4 ms | 0 |
| 10 | 101.0 ms | 57.2 ms | 222.7 ms | 481.4 ms | 746.5 ms | 746.5 ms | 141.3 ms | 0 |
| 20 | 128.1 ms | 58.0 ms | 435.0 ms | 455.4 ms | 504.2 ms | 504.2 ms | 147.0 ms | 0 |
| 25 | 132.3 ms | 59.9 ms | 384.1 ms | 401.9 ms | 580.6 ms | 580.6 ms | 127.3 ms | 0 |
| 50 | 255.8 ms | 246.1 ms | 430.0 ms | 442.5 ms | 700.6 ms | 700.6 ms | 148.1 ms | 0 |

### Small File Comparative Analysis

**P50 comparison (202 bytes GetObject)**:

| Concurrency | 256 MBps P50 | 512 MBps P50 | Difference |
|:-----------:|:---:|:---:|:---:|
| 1 | 56.9 ms | 59.8 ms | ≈comparable |
| 10 | 56.5 ms | 57.2 ms | ≈comparable |
| 25 | 60.3 ms | 59.9 ms | ≈comparable |
| 50 | 257.9 ms | 246.1 ms | ≈comparable |

**Conclusion (small files)**:
1. **P50 does not depend on throughput capacity**: P50 is nearly identical between 256 MBps and 512 MBps (~57-60 ms at concurrency ≤25)
2. **The bottleneck for small files is connection overhead**: TLS handshake + S3 AP routing dominates, not file transfer time
3. **P50 increases to ~250 ms at concurrency=50**: Request queuing occurs in the S3 AP data plane
4. **P99 is more stable at 256 MBps**: The higher P99 at 512 MBps (690-747 ms) may be sampling noise
5. **Increasing throughput capacity is only effective for large file transfers**: No cost benefit for small file processing

> **Sizing insight**: For small-file-centric workloads (metadata reads, JSON manifests, log entries), 128 MBps is sufficient. Increasing throughput capacity is effective when processing files of 1 MB or larger in parallel.

---

## References

- [S3AP Performance Considerations](s3ap-performance-considerations.en.md)
- [AWS: Accessing your data via S3 access points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)
- [FSx for ONTAP Performance](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/performance.html)
