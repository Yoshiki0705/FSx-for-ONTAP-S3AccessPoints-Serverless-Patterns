# S3 Access Points for FSx for ONTAP — Performance Considerations

🌐 **Language / 言語**: [日本語](s3ap-performance-considerations.md) | [English](s3ap-performance-considerations.en.md)

## Overview

Data access via S3 Access Points for FSx for ONTAP depends on the FSx file system's provisioned throughput. This document organizes the factors to consider when designing for performance.

> **Important**: The numbers in this document are not service limits. They are sizing references from a specific test environment. For production workloads, measure with your own AWS account, region, FSx configuration, workload profile, file size distribution, and concurrency level.

> **AWS Documentation Quote**: "Amazon S3 access points for FSx for ONTAP file systems deliver latency in the tens of milliseconds range, consistent with S3 bucket access. The throughput and requests per second you can drive to an Amazon FSx file system via the S3 API depends on the file system's provisioned throughput."
> — [Accessing your data via Amazon S3 access points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)

## Throughput Dependencies

### FSx Provisioned Throughput → S3 AP Throughput

```
┌─────────────────────────────────────────────────────────────┐
│  S3 API Client (Lambda / Step Functions / EC2)              │
└─────────────────────────┬───────────────────────────────────┘
                          │ S3 API (GetObject / PutObject / ListObjectsV2)
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  S3 Access Point                                            │
│  • Latency: tens of milliseconds                           │
│  • Throughput: depends on FSx provisioned throughput        │
└─────────────────────────┬───────────────────────────────────┘
                          │ FSx Data Plane
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  FSx for ONTAP File System                                  │
│  • SSD latency: sub-millisecond                            │
│  • Network I/O: determined by throughput capacity           │
│  • Disk I/O: determined by throughput capacity + SSD IOPS   │
└─────────────────────────────────────────────────────────────┘
```

### FSx Throughput Capacity Limits (Reference)

| File System Type | Max Read Throughput (per HA pair) | Max Write Throughput |
|-----------------|----------------------------------|---------------------|
| Gen1 Single-AZ (major regions) | 4,096 MBps | 1,000 MBps |
| Gen1 Multi-AZ (major regions) | 4,096 MBps | 1,800 MBps |
| Gen2 Single-AZ | 6,144 MBps (per HA pair, up to 12 pairs) | 1,024 MBps |
| Gen2 Multi-AZ | 6,144 MBps | 2,048 MBps |

> **Note**: Throughput via S3 AP cannot exceed these limits. All access via S3 AP, NFS, and SMB shares the same throughput capacity.

## Object Size Profile

### S3 AP Constraints

| Operation | Max Size | Notes |
|-----------|----------|-------|
| Object size limit (upload) | **50 GiB** (53,687,091,200 bytes) | Measured. Enforced at `CompleteMultipartUpload` |
| PutObject (single) | **5 GiB** (5,368,709,120 bytes) | Amazon S3 API-wide single PUT limit. Use Multipart Upload above 5 GiB |
| UploadPart (per part) | **5 GiB** (5,368,709,120 bytes) | Cumulative size is not checked |
| GetObject | No limit | Files larger than 50 GiB can be downloaded |
| Multipart Upload | 50 GiB (completed object) | Upload in parts. Required for objects between 5 GiB and 50 GiB |
| Storage Class | FSX_ONTAP only | Other storage classes cannot be specified |
| Encryption | SSE-FSX only | SSE-KMS / SSE-S3 cannot be used |

### Recommended Strategy by Object Size

| Size Range | Recommended Approach | Lambda Memory Guideline |
|-----------|---------------------|------------------------|
| < 1 MB | Direct GetObject, in-memory processing | 256-512 MB |
| 1-100 MB | GetObject + streaming processing | 512 MB - 1 GB |
| 100 MB - 1 GB | Range GET (partial read) or write to /tmp | 1-3 GB |
| 1 GB - 5 GiB | /tmp (10 GB) + streaming, or EFS mount | 3-10 GB |
| 5 GiB - 50 GiB | Multipart Upload (single PutObject not available). Read via Range GET streaming | ECS/Batch recommended |
| > 50 GiB | Readable. Write-back exceeds the object limit, so split it or place the file via NFS/SMB | ECS/Batch recommended |

> **About the object size limit**: The maximum object size for uploads is **50 GiB = 53,687,091,200 bytes** (measured). The AWS documentation writes it as "50 GB", but the value is binary. It was previously "5 GB" and was raised in a documentation update (archived copies show 5 GB on 2026-03-08 and 50 GB on 2026-06-25; no corresponding What's New announcement was found). The 5 GiB limit on a single `PutObject` is an Amazon S3 API-wide constraint and has not changed.
>
> ⚠️ The whole-object limit is enforced only at `CompleteMultipartUpload`; `UploadPart` performs no cumulative check. An over-limit object fails only after the full transfer, so **validate size client-side before starting the upload**. Details: [measured object size limits](s3ap-object-size-limits-verification.en.md)
>
> Sources: [Access point compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html) / [Uploading objects](https://docs.aws.amazon.com/AmazonS3/latest/userguide/upload-objects.html)

## ListObjectsV2 Pagination

### Behavior

- **MaxKeys**: Default 1000, maximum 1000
- **Pagination**: When `IsTruncated=true`, use `NextContinuationToken` to fetch the next page
- **Prefix filter**: Server-side filtering (efficient)
- **Delimiter**: Simulates directory hierarchy (returned as `CommonPrefixes`)

### Performance Considerations

```python
# Recommended: Use Prefix to narrow the scope
response = s3.list_objects_v2(
    Bucket=s3ap_alias,
    Prefix="data/2026/05/",  # Date-based filtering
    MaxKeys=1000
)

# For large file counts: consider pagination latency
# Each page retrieval takes tens of milliseconds
# 10,000 files = 10 pages × ~50ms = ~500ms (minimum)
```

### Optimization for Large File Environments

| File Count | Recommended Approach | Estimated Time |
|-----------|---------------------|---------------|
| < 1,000 | Single ListObjectsV2 | < 100 ms |
| 1,000 - 10,000 | Prefix partitioning + parallel List | 1-5 seconds |
| 10,000 - 100,000 | Date/category Prefix + DynamoDB cache | 5-30 seconds |
| > 100,000 | Incremental scan (delta from last run only) | Workload-dependent |

## Large Object Read Strategy

### Using Range GET

S3 AP for FSx for ONTAP supports GetObject, and partial reads via HTTP Range header are possible:

```python
# Range GET to fetch only the first 1MB
response = s3.get_object(
    Bucket=s3ap_alias,
    Key="large-file.bin",
    Range="bytes=0-1048575"  # First 1 MB
)
```

**Use cases**:
- Reading file headers only (DICOM, GDS, SEG-Y and other binary formats)
- Reading the tail of large log files
- Parallel download (fetching multiple Ranges concurrently)

### Streaming Reads

```python
# Memory-efficient streaming processing
response = s3.get_object(Bucket=s3ap_alias, Key="large-file.csv")
for chunk in response["Body"].iter_chunks(chunk_size=8192):
    process_chunk(chunk)
response["Body"].close()
```

## Lambda Memory Size vs Throughput

### Lambda Network Bandwidth

Lambda network bandwidth is allocated proportionally to memory size:

| Lambda Memory | Approx. Network Bandwidth | Time to Fetch 10 MB File |
|--------------|--------------------------|--------------------------|
| 128 MB | ~50 Mbps | ~1.6 s |
| 512 MB | ~200 Mbps | ~0.4 s |
| 1,024 MB | ~400 Mbps | ~0.2 s |
| 1,769 MB (1 vCPU) | ~600 Mbps | ~0.13 s |
| 3,008 MB | ~1 Gbps | ~0.08 s |
| 10,240 MB (6 vCPU) | ~several Gbps | < 0.05 s |

> **Note**: The above are approximate values. Actual throughput is also constrained by S3 AP latency (tens of ms) and FSx provisioned throughput.

### Recommended Memory Size by Use Case

| Use Case | Recommended Memory | Rationale |
|----------|-------------------|-----------|
| Metadata extraction (small files) | 512 MB | Minimal CPU/memory sufficient |
| OCR / image processing | 1-3 GB | Memory needed for image decoding |
| AI/ML inference (Bedrock calls) | 512 MB - 1 GB | Network I/O dominant |
| Large file processing | 3-10 GB | /tmp write + processing |
| Batch aggregation | 1-3 GB | In-memory aggregation of multiple files |

## Step Functions Map Concurrency vs FSx Throughput

### Concurrency Design

When processing multiple files in parallel with Step Functions Map State, FSx throughput capacity becomes the upper bound:

```
Map State (MaxConcurrency=N)
  ├─→ Lambda 1: GetObject (file_1) → Process → PutObject
  ├─→ Lambda 2: GetObject (file_2) → Process → PutObject
  ├─→ Lambda 3: GetObject (file_3) → Process → PutObject
  └─→ ...
      ↓ (all share the same FSx file system throughput)
```

### Concurrency Calculation

```
max_concurrency = fsxn_provisioned_throughput / per_lambda_throughput

Example: FSx 512 MBps provisioned, each Lambda consuming 50 MBps
  → max_concurrency ≈ 10 (for S3 AP access only)

Note: Existing NFS/SMB workloads also consume throughput,
      so actual available bandwidth is lower
```

### Recommended MaxConcurrency Settings

| FSx Throughput Capacity | Recommended MaxConcurrency | Notes |
|------------------------|---------------------------|-------|
| 128 MBps | 2-5 | Small-scale PoC |
| 256 MBps | 5-10 | Development/test |
| 512 MBps | 10-20 | Small-scale production |
| 1,024 MBps | 20-50 | Medium-scale production |
| 2,048+ MBps | 50-100 | Large-scale production |

> **Important**: The above values consider S3 AP access only. If existing NFS/SMB workloads are present, subtract their throughput consumption from the design.

## Retry / Backoff Policy

### S3 AP-Specific Errors and Handling

| Error | Cause | Recommended Action |
|-------|-------|-------------------|
| `SlowDown` (503) | FSx throughput exceeded | Exponential backoff (base: 1s, max: 30s) |
| `ServiceUnavailable` (503) | FSx data plane transient failure | Retry with jitter (max 3 attempts) |
| `RequestTimeout` (408) | Large file read timeout | Extend Lambda timeout + retry |
| `AccessDenied` (403) | IAM or file system permission | No retry needed (fix configuration) |

### Recommended Retry Configuration

```python
import botocore.config

s3_config = botocore.config.Config(
    retries={
        "max_attempts": 5,
        "mode": "adaptive"  # adaptive mode: automatically adjusts backoff
    },
    connect_timeout=10,
    read_timeout=60,  # For large files
)

s3 = boto3.client("s3", config=s3_config)
```

### Step Functions Retry Configuration

```json
{
  "Retry": [
    {
      "ErrorEquals": ["States.TaskFailed"],
      "IntervalSeconds": 2,
      "MaxAttempts": 3,
      "BackoffRate": 2.0,
      "JitterStrategy": "FULL"
    }
  ]
}
```

## Performance Monitoring

### Recommended CloudWatch Metrics

| Metric | Meaning | Alarm Threshold (Reference) |
|--------|---------|----------------------------|
| FSx `DataReadBytes` | Read throughput | > 80% of provisioned |
| FSx `DataWriteBytes` | Write throughput | > 80% of provisioned |
| Lambda `Duration` | Processing time | > timeout × 0.8 |
| Step Functions `ExecutionTime` | Total workflow time | SLO-dependent |
| SQS `ApproximateAgeOfOldestMessage` | Backlog accumulation | > 300 seconds |

### Bottleneck Identification Flow

```
Lambda Duration is high
├── GetObject is slow
│   ├── FSx DataReadBytes near limit → Increase Throughput Capacity
│   ├── Lambda memory is small → Increase memory (improves bandwidth)
│   └── Object is large → Range GET / streaming
├── Processing is slow
│   ├── CPU bound → Increase Lambda memory (increases vCPU)
│   └── External API calls → Parallelize / batch
└── PutObject is slow
    ├── FSx DataWriteBytes near limit → Increase Throughput Capacity
    └── Object is large → Multipart Upload
```

## References

- [Amazon FSx for ONTAP performance](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/performance.html)
- [Accessing your data via Amazon S3 access points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)
- [Access point compatibility (Supported S3 operations)](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)
- [S3 AP dual-layer authorization model](s3ap-authorization-model.en.md)
- [Deployment Profiles](deployment-profiles.md)

## Sharing Bandwidth with KNFSD File Cache

### Background

If you run [KNFSD File Cache](https://github.com/awslabs/knfsd-file-cache) (Preview, July 2026) as an NFS read cache in front of FSx for ONTAP, it **shares the same FSx provisioned throughput** as your S3 AP-based Lambda processing. The design has to prevent the two from competing for bandwidth.

### Throughput sharing model

```
FSx for ONTAP Provisioned Throughput (e.g. 1,024 MBps)
├── KNFSD File Cache source reads (NFS mount)
│   ├── On cache MISS only: fetch from the source
│   └── On cache HIT: no FSx bandwidth consumed  <- this is the key point
├── S3 AP Lambda processing (GetObject / PutObject)
├── Direct NFS clients
└── Direct SMB clients
```

### KNFSD cache hit ratio and its effect on FSx bandwidth

| KNFSD cache hit ratio | Effect on FSx bandwidth | Effect on S3 AP processing |
|:---:|---|---|
| > 95% | KNFSD consumes almost no FSx bandwidth | None |
| 70-95% | Bandwidth consumed during initial warm-up | Possible temporary contention |
| < 70% | Insufficient cache — consumes substantial FSx bandwidth | Risk of `SlowDown` on S3 AP |

### Design recommendations

#### Bandwidth allocation guideline (KNFSD + S3 AP together)

| Phase | KNFSD bandwidth use | S3 AP recommendation |
|-------|:---:|---|
| KNFSD warm-up (first fetch) | High | Hold off S3 AP processing, or lower MaxConcurrency |
| Steady state (cache warm) | Low (misses only) | Normal MaxConcurrency is fine |
| Just after a compute burst starts | Medium to high | Enable adaptive retry on the S3 AP side |

#### How to adjust MaxConcurrency

```
# S3 AP MaxConcurrency when KNFSD is also in use
available_for_s3ap = fsxn_throughput - knfsd_miss_throughput - nfs_smb_direct
max_concurrency = available_for_s3ap / per_lambda_throughput

# Example: 1,024 MBps FSx, KNFSD misses 200 MBps, NFS/SMB 100 MBps
# available_for_s3ap = 1,024 - 200 - 100 = 724 MBps
# with per_lambda_throughput = 50 MBps
# max_concurrency ~= 14
```

#### Time-window separation pattern

Separate read-heavy bursts from S3 AP post-processing by time of day:

```
[06:00-18:00] Compute burst: EDA/VFX reads through KNFSD (bandwidth priority)
[18:00-22:00] S3 AP post-processing: Lambda analysis and reporting (after cache is warm)
[22:00-06:00] Maintenance window: Snapshot, SnapMirror
```

> **Observability note**: Monitor KNFSD's CloudWatch metrics (particularly `cache_hit_ratio` and `read_throughput_source`) alongside the FSx `DataReadBytes` metric on the same dashboard, so bandwidth contention is detected early. KNFSD exposes 70+ metrics via OTel, so integration with Prometheus/Grafana is also possible.

> **See also**: For the detailed architecture guide, see [KNFSD + S3 AP Dual-Path Architecture](./knfsd-s3ap-dual-path-architecture.en.md).
- [S3AP Dual-Layer Authorization Model](s3ap-authorization-model.md)
- [Deployment Profiles](deployment-profiles.md)
