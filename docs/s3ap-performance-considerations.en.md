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
| PutObject (single) | 5 GB | Files larger than this cannot be uploaded |
| GetObject | No limit | Files larger than 5 GB can be downloaded |
| Multipart Upload | 5 GB (completed object) | Upload in parts |
| Storage Class | FSX_ONTAP only | Other storage classes cannot be specified |
| Encryption | SSE-FSX only | SSE-KMS / SSE-S3 cannot be used |

### Recommended Strategy by Object Size

| Size Range | Recommended Approach | Lambda Memory Guideline |
|-----------|---------------------|------------------------|
| < 1 MB | Direct GetObject, in-memory processing | 256-512 MB |
| 1-100 MB | GetObject + streaming processing | 512 MB - 1 GB |
| 100 MB - 1 GB | Range GET (partial read) or write to /tmp | 1-3 GB |
| 1-5 GB | /tmp (10 GB) + streaming, or EFS mount | 3-10 GB |
| > 5 GB | GetObject only (PutObject not available), consider splitting | ECS/Batch recommended |

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
- [S3AP Dual-Layer Authorization Model](s3ap-authorization-model.md)
- [Deployment Profiles](deployment-profiles.md)
