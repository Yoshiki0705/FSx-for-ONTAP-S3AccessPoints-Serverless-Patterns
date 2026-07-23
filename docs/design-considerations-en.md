> 🌐 Language: [日本語](design-considerations.md) | [English](design-considerations-en.md)

# FSx for ONTAP S3 Access Points — Design Considerations

This document systematically covers technical considerations for designing and implementing serverless patterns that leverage FSx for ONTAP S3 Access Points (hereafter "S3 AP").

It covers directory design optimized for S3 API access from Lambda / Step Functions, understanding of performance characteristics, feature compatibility awareness, and security design.

---

## Table of Contents

1. [Directory Design](#1-directory-design)
2. [Object Key and Path Length Constraints](#2-object-key-and-path-length-constraints)
3. [Performance Characteristics](#3-performance-characteristics)
4. [ListObjectsV2 Design Patterns](#4-listobjectsv2-design-patterns)
5. [Multi-Protocol Access Consistency](#5-multi-protocol-access-consistency)
6. [Feature Compatibility](#6-feature-compatibility)
7. [Security Design](#7-security-design)
8. [PoC Checklist](#8-poc-checklist)

---

## 1. Directory Design

### Problem: Large File Concentrations in a Single Directory

In the ONTAP file system, as the file count within a single directory increases, the following effects are observed:

| Impact | Cause | Threshold Estimate |
|--------|-------|--------------------|
| Increased `readdir` response time | Linear scan of directory entries | ~100K+ files |
| File creation failure from `maxdir-size` | Directory metadata area limit reached | Depends on default limit |
| FlexGroup constituent imbalance | Hash distribution is per-directory | When files concentrate heavily |
| ListObjectsV2 response delay | In-memory sort cost increases | ~100K+ files |

**Reference**: [How do I avoid maxdir-size issues (NetApp KB)](https://kb.netapp.com/on-prem/ontap/Ontap_OS/OS-KBs/How_do_I_avoid_maxdir-size_issues)

### Recommended Patterns

#### Hive-Style Hierarchical Partitioning

```
s3://<ap-alias>/data/year=2026/month=07/day=22/sensor_001.json
s3://<ap-alias>/data/year=2026/month=07/day=22/sensor_002.json
```

With S3 AP, "/" is interpreted as a directory separator, so hierarchical partitions automatically map to directory structures.

#### Hash Bucketing

```
s3://<ap-alias>/objects/a3/b2/object-uuid-001.bin
s3://<ap-alias>/objects/f7/e1/object-uuid-002.bin
```

Uses the first 2-4 characters of the filename as hash buckets to distribute files across directories.

#### Tenant + Date Hybrid

```
s3://<ap-alias>/tenant-a/2026/07/22/report.pdf
s3://<ap-alias>/tenant-b/2026/07/22/invoice.csv
```

Satisfies both tenant isolation and time-series access patterns in multi-tenant scenarios.

### Files Per Directory Guidelines

| Scenario | Recommended Limit | Rationale |
|----------|------------------|-----------|
| General workloads | 100K or fewer | Practical upper bound for ListObjectsV2 response and directory traversal |
| High-frequency writes (IoT/logs) | 10K or fewer | Finer partitioning needed for write-heavy patterns |
| FlexGroup usage | 50K or fewer / constituent | Maintain even distribution across constituents |

### FlexVol vs FlexGroup Selection Criteria

| Criteria | FlexVol | FlexGroup |
|---------|---------|-----------|
| Max single volume size | ~100 TB (practical) | PB scale |
| Max file count | ~2 billion | constituents × 2 billion |
| FlexCache Origin support | 9.12.1+ | 9.13.1+ (with constraints) |
| SnapMirror support | Full | Full |
| S3 AP support | ✅ | ✅ |
| Recommended use | Single workload / PoC | Large-scale / multi-tenant |

**Reference**: [FlexGroup volumes overview (NetApp Docs)](https://docs.netapp.com/us-en/ontap/flexgroup/definition-concept.html)

---

## 2. Object Key and Path Length Constraints

### Length Limits

| Constraint | Maximum | Notes |
|-----------|---------|-------|
| S3 object key total length | 1,024 bytes | UTF-8 byte length. CJK character = 3-4 bytes |
| Directory / file name | 255 characters | ONTAP file system constraint |
| Path depth | No limit (practical: ~30 levels) | No explicit nesting limit, but deep nesting reduces operability |

### Multi-byte Character Considerations

```
# Japanese filename example
"レポート_2026年07月.pdf"
→ UTF-8: 31 bytes ("レ" = 3B × 7 chars + ASCII = 31B)
→ Within 255-char limit, but the entire path counts toward the 1,024B key limit
```

### Safe Characters for Both S3 and NFS/SMB

| Category | Safe Characters | Avoid |
|---------|-----------------|-------|
| ASCII | `a-z`, `A-Z`, `0-9`, `-`, `_`, `.` | `\`, `:`, `*`, `?`, `"`, `<`, `>`, `|` |
| Unicode | CJK Unified Ideographs, Hangul, Latin Extended | Control chars (U+0000-U+001F), BOM |
| Special | `/` (S3 delimiter = directory separator) | Leading/trailing spaces, consecutive slashes `//` |

**Design guideline**: When generating keys from Lambda, normalize filenames (NFKC) before use. When reading files created via NFS/SMB through S3 AP, avoid characters that depend on client OS encoding.

---

## 3. Performance Characteristics

### Performance Trends by File Size

| File Size | Characteristics | Impact on Lambda Patterns |
|-----------|----------------|--------------------------|
| < 64 KB | Metadata processing overhead is relatively larger | Batching/aggregation can be advantageous |
| 64 KB – 1 MB | Typical document / JSON size range | Optimal for most serverless patterns |
| > 1 MB | Data transfer dominates. Performance gap with Amazon S3 narrows for larger objects | Consider Multipart Upload |
| > 5 GB | S3 AP PutObject limit (5 GB) applies | Multipart Upload required (ONTAP 9.16.1+) |

### Throughput Design

FSx for ONTAP throughput capacity is shared across NFS/SMB/S3 AP. Increased S3 AP traffic can affect NFS/SMB performance on the same volume.

**Design points**:
- Schedule batch processing (high-volume S3 API calls) outside NFS/SMB peak hours
- Use EventBridge Scheduler for off-peak job execution
- Monitor throughput capacity (CloudWatch `TotalThroughputUtilization`)

### Mitigation Patterns

| Challenge | Mitigation |
|-----------|-----------|
| Efficiency of mass small-file writes | Aggregate into TAR/ZIP then single PutObject, or combine via Kinesis Data Firehose |
| ListObjectsV2 latency | Prefix-limited queries, external catalogs (DynamoDB / Glue Data Catalog) |
| Read latency | FlexCache read acceleration (same-cluster: ~6s propagation, cross-region: <3s) |

---

## 4. ListObjectsV2 Design Patterns

### Internal Processing in ONTAP

S3 AP's ListObjectsV2 is processed internally in ONTAP as follows:

1. Traverse the directory corresponding to the specified Prefix via `readdir`
2. Sort entries in-memory (to satisfy S3 API's lexicographic ordering guarantee)
3. Return results based on MaxKeys

Sort cost is proportional to the number of files in the directory, so LIST operations on directories with large file counts have increased response times.

### Recommended Patterns

| Pattern | Description | Use Case |
|---------|-------------|----------|
| Prefix-limited LIST | `Prefix=data/2026/07/22/` to scope to daily partition | Identifying batch processing input files |
| MaxKeys limiting | `MaxKeys=100` to fetch minimal needed results | Streaming processing |
| LIST-free design | Receive new file S3 keys via SQS/EventBridge | Event-driven patterns |
| External catalog | Register metadata in DynamoDB / Glue Data Catalog | Large-scale data lakes |

### Anti-Patterns

| Anti-Pattern | Problem | Alternative |
|-------------|---------|-------------|
| Full LIST at root (`/`) | Scans entire volume. Tens of seconds to timeout at 100K+ files | Always use Prefix |
| Recursive LIST (no Delimiter) | Recursively traverses all subdirectories | LIST per hierarchy level |
| Polling-based file detection | Repeated LIST execution | EventBridge / FPolicy event-driven |
| Full fetch then client-side filter | Unnecessary data transfer | Prefix + StartAfter scoping |

---

## 5. Multi-Protocol Access Consistency

### Concurrent Access Scenarios

S3 AP data access coexists with NFS/SMB access to the same volume. Be aware of these contention patterns:

| Scenario | Behavior | Risk |
|---------|----------|------|
| S3 AP GET during NFS write | Partially written data may be read | Data inconsistency |
| NFS read after S3 AP PutObject completes | Consistent data immediately readable (WAFL atomic commit) | None |
| S3 AP GET with old key after NFS rename | Old key returns NotFound (rename reflected immediately) | Application key management |
| S3 AP write + FlexCache write-back on same file | Cache dirty data discarded (XLD revoke) | Data contention |

### Recommended Design

1. **Limit write protocol to one**: Do not simultaneously write to the same file via both S3 AP and NFS/SMB
2. **Temp directory → rename pattern**: Write via S3 AP to `/tmp/processing/`, then move to `/data/final/` via NFS after processing
3. **File-level separation**: S3 AP creates new files only; NFS/SMB reads existing files only — separate roles
4. **ONTAP Snapshot consistency points**: Fix batch processing input data with Snapshots to exclude in-flight changes

---

## 6. Feature Compatibility

FSx for ONTAP S3 AP is "S3 compatible" but NOT "identical to Amazon S3." Consider the following differences in design.

### Compatibility Matrix

| Feature | S3 AP Support | Alternative | Notes |
|---------|:------------:|-------------|-------|
| GetObject / PutObject | ✅ | — | Max 5 GB/object |
| Multipart Upload | ✅ | — | ONTAP 9.16.1+ |
| ListObjectsV2 | ✅ | — | Prefix / Delimiter / MaxKeys supported |
| HeadObject | ✅ | — | |
| DeleteObject | ✅ | — | |
| CopyObject | ✅ | — | Same AP only |
| Versioning | ❌ | ONTAP Snapshot (volume-level) | Version management via Snapshot + FlexClone |
| Conditional writes (If-None-Match) | ❌ | Application-level locking | Returns 501 Not Implemented |
| S3 Event Notification | ❌ | FPolicy + EventBridge | FPolicy captures ONTAP-layer file operation events |
| Lifecycle Rules | ❌ | FabricPool / ONTAP Tiering Policy | `AUTO` / `SNAPSHOT_ONLY` for automatic tiering |
| Object Lock / WORM | ❌ | SnapLock | SnapLock Compliance for regulatory requirements |
| S3 Select | ❌ | Athena + Glue Data Catalog | Process with external analytics engines |
| Server-Side Encryption (SSE-S3/KMS) | ❌ | NAE / NVE (ONTAP volume encryption) | At-rest via ONTAP layer. In-transit via TLS |
| Presigned URL | ⚠️ | — | Works in some cases (unofficial). Not recommended for production reliance |
| Cross-AP Copy | ❌ | DataSync / rsync | Cannot copy between different APs |

**Reference**: [Accessing data via S3 Access Points (AWS Docs)](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)

### Serverless Patterns Affected

| Pattern | Affected Constraint | Mitigation |
|---------|-------------------|-----------|
| Delta Lake / Iceberg tables | Conditional writes unsupported | Application-level locking, or place metastore on standard S3 |
| Event-driven processing | S3 Event Notification unsupported | FPolicy + EventBridge for equivalent functionality |
| Lifecycle management | Lifecycle Rules unsupported | ONTAP Tiering Policy + Snapshot auto-delete policy |
| Compliance retention | Object Lock unsupported | SnapLock Compliance volume |

---

## 7. Security Design

### Purpose-Based Access Point Separation

Create multiple S3 APs on a single volume to separate purposes and permissions:

```
Volume: vol_production_data
├── S3 AP: prod-readonly     → GET/LIST only (analytics Lambda)
├── S3 AP: prod-ingestion    → PUT only (data collection Lambda)
├── S3 AP: prod-training     → GET only (ML training)
└── S3 AP: prod-audit        → GET/LIST only (audit Lambda, different UNIX user)
```

### Two-Layer Authorization Model

S3 AP access is controlled at two layers. Both layers must Allow (AND condition):

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: AWS IAM + AP Resource Policy                        │
│ - IAM Identity Policy (Lambda execution role)                │
│ - S3 AP Resource Policy (optional; required for cross-acct)  │
│ - Controls: who / which resource / which API                 │
└─────────────────────────────────────────────────────────────┘
                            ↓ (both Allow to pass)
┌─────────────────────────────────────────────────────────────┐
│ Layer 2: NAS File System Permissions                         │
│ - FileSystemIdentity (UNIX UID/GID or Windows AD user)       │
│ - UNIX permissions / POSIX ACL / NTFS ACL                    │
│ - Controls: file/directory level access                      │
└─────────────────────────────────────────────────────────────┘
```

### IAM Policy Best Practices

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "S3APReadOnly",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/prod-readonly",
        "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/prod-readonly/object/*"
      ]
    }
  ]
}
```

**Design points**:
- Assign a dedicated IAM role to each Lambda function (no shared roles)
- S3 AP ARNs require region and account ID (bucket-style ARN does not work)
- Same-account access does not require AP Resource Policy (IAM Identity Policy alone is sufficient)
- Add AP Resource Policy only for cross-account access

---

## 8. PoC Checklist

Items to verify in a PoC for serverless patterns using FSx for ONTAP S3 AP:

### Architecture

- [ ] Determine S3 AP NetworkOrigin (Internet / VPC)
- [ ] Determine Lambda placement (VPC = ONTAP REST API access / VPC-external = Internet-origin S3 AP)
- [ ] Confirm throughput capacity covers combined NFS/SMB + S3 AP traffic
- [ ] For AD-joined SVMs: confirm AD DC reachability is a prerequisite for S3 AP data operations

### Namespace

- [ ] Determine directory hierarchy partitioning design
- [ ] Confirm files per directory will not exceed 100K
- [ ] Confirm object keys fit within 1,024 bytes
- [ ] Determine multi-byte filename handling (NFKC normalization needs)

### Performance

- [ ] Confirm target file size distribution (whether small-file aggregation is needed)
- [ ] Confirm ListObjectsV2 execution patterns (prefix-limited / any full-scan)
- [ ] Confirm throughput allocation when coexisting with NFS/SMB workloads
- [ ] Measure FlexCache cache-hit ratio and data propagation latency

### Features

- [ ] Confirm dependency on conditional writes (Delta Lake / Iceberg, etc.)
- [ ] Confirm dependency on S3 Event Notification (need for FPolicy alternative)
- [ ] Confirm Multipart Upload needs (ONTAP version requirement: 9.16.1+)
- [ ] Confirm dependency on Presigned URLs (not recommended for production)

### Security

- [ ] Confirm purpose-based S3 AP separation design
- [ ] Confirm least-privilege IAM roles
- [ ] Confirm FileSystemIdentity (UNIX user) selection and NAS permission alignment
- [ ] Confirm Secrets Manager credential management pattern

### Operations

- [ ] Configure CloudWatch metrics alarms (TotalThroughputUtilization, S3APIRequests)
- [ ] S3 AP lifecycle management (detach AP before volume deletion)
- [ ] Document S3 AP re-creation procedure for SnapMirror DR failover
- [ ] Document teardown order (SM-VAL-011 compliant)

---

## FlexCache / SnapMirror Additional Considerations

Additional design points when distributing data collected via S3 AP using FlexCache (read acceleration) or SnapMirror (DR):

| Consideration | Details | Reference |
|--------------|---------|-----------|
| S3 AP metadata is NOT transferred via SnapMirror | New S3 AP must be created at destination | [SnapMirror DR Pattern](../solutions/flexcache/snapmirror-cross-region-dr/) |
| S3 AP on FlexCache Cache Volume | Requires ONTAP 9.18.1+ | [FlexCache Same-Region Pattern](../solutions/flexcache/same-region-s3ap/) |
| write-back + S3 AP same-file conflict | XLD revoke discards Cache dirty data | [FlexCache Cross-Region Pattern](../solutions/flexcache/cross-region-s3ap/) |
| DP Volume must be created via FSx API | SM-VAL-009: ONTAP REST API alone makes volume invisible for S3 AP attachment | [SnapMirror DR Pattern](../solutions/flexcache/snapmirror-cross-region-dr/) |
| Teardown order | SM-VAL-011: SVM Peer deletion must complete before VPC Peering deletion | Each FlexCache/SnapMirror pattern Clean Up section |

Detailed compatibility tables and version matrix: [FlexCache / SnapMirror Considerations (fsxn-lakehouse-integrations)](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations/blob/main/docs/en/s3ap-flexcache-snapmirror-considerations.md)

---

## References

- [AWS Docs: Accessing data via S3 Access Points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)
- [AWS Docs: Optimizing S3 Performance](https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance.html)
- [NetApp KB: How do I avoid maxdir-size issues](https://kb.netapp.com/on-prem/ontap/Ontap_OS/OS-KBs/How_do_I_avoid_maxdir-size_issues)
- [NetApp KB: Performance impacts of changing maxdirsize](https://kb.netapp.com/on-prem/ontap/Ontap_OS/OS-KBs/What_are_the_performance_impacts_of_changing_the_size_of_maxdirsize)
- [NetApp Docs: FlexGroup volumes](https://docs.netapp.com/us-en/ontap/flexgroup/definition-concept.html)
- [NetApp Docs: S3 multiprotocol](https://docs.netapp.com/us-en/ontap/s3-multiprotocol/index.html)
- [NetApp Docs: FlexCache supported features](https://docs.netapp.com/us-en/ontap/flexcache/supported-unsupported-features-concept.html)
