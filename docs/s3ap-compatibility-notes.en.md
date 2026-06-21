# S3AP Compatibility Notes

🌐 **Language / 言語**: [日本語](s3ap-compatibility-notes.md) | [English](s3ap-compatibility-notes.en.md)

## What FSx for ONTAP S3 Access Points Provide

FSx for ONTAP S3 Access Points provide an S3-facing access boundary for file data stored in FSx for ONTAP. Data remains on FSx for ONTAP and can continue to be accessed through NFS and SMB.

## S3 AP vs NFS/SMB: When to Use Which

| Requirement | Prefer S3 AP | Prefer NFS/SMB |
|---|:---:|:---:|
| Serverless integration (Lambda, Step Functions) | ✅ | — |
| POSIX semantics required (lock, rename, symlink) | — | ✅ |
| Large sequential file processing | △ (5GB limit) | ✅ |
| Permission-aware file access control | ✅ (dual-layer auth) | ✅ (NTFS/UNIX ACL) |
| Low-latency metadata operations (stat, readdir) | △ (tens of ms) | ✅ (sub-ms) |
| Existing application compatibility | — | ✅ |
| AWS service integration (Athena, Bedrock, Textract) | ✅ | — |
| Event-driven file processing | ✅ (FPolicy + S3 AP) | △ (FPolicy + NFS mount) |

> **Note**: S3 AP is not a replacement for NFS/SMB. It is a complementary access path for AWS service integration. The same volume can be accessed via NFS/SMB and S3 AP simultaneously.

## Tested Operations

| Operation | Status |
|-----------|--------|
| ListObjectsV2 | ✅ Tested |
| GetObject | ✅ Tested |
| PutObject (max 5 GB) | ✅ Tested |
| Range GET | ✅ Tested |
| HeadObject | ✅ Tested |
| DeleteObject | ✅ Tested |
| MultipartUpload | ✅ Supported (per AWS docs) |

## Not Equivalent to Full S3 Bucket Semantics

Not all bucket-level features or integration patterns apply directly:

- Native S3 bucket notifications (GetBucketNotificationConfiguration not supported)
- Bucket lifecycle policies
- Bucket versioning
- Object Lock (on the S3AP itself)
- Presigned URLs (**Listed as "Not supported"** — but observed working; see [Presigned URL Support](#presigned-url-support) for AWS Support clarification)

### WORM / Immutable Storage Alternatives

S3 Object Lock / Versioning are not supported. FSx for ONTAP provides native alternatives:

| S3 Feature | ONTAP Alternative | Characteristics |
|---|---|---|
| Object Lock Compliance | **SnapLock Compliance** volume | SEC 17a-4(f), FINRA 4511 compliant WORM. No one can delete during retention |
| Object Lock Governance | **SnapLock Enterprise** volume | Internal compliance WORM. Privileged delete available |
| Versioning (point-in-time) | **ONTAP Snapshot** | Point-in-time file system protection. Stores only changed blocks |
| Replication | **SnapMirror** | Cross-region/cross-account replication |

#### Tamperproof Snapshot

Locks Snapshots for a specified retention period using the SnapLock Compliance clock. Once locked, no one — including ONTAP administrators — can delete the Snapshot until expiration. Protects against Snapshot deletion attacks (e.g., ransomware).

> **Source**: [Snapshot locking — NetApp ONTAP](https://docs.netapp.com/us-en/ontap/snaplock/snapshot-lock-concept.html)

#### Autonomous Ransomware Protection (ARP)

AI-driven monitoring of volume behavior (data entropy changes, file extension changes, IOPS spikes). Automatically creates protective Snapshots when threats are detected. Focuses on detection and automatic response.

> **Source**: [ARP — FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/ARP.html)

> **Tamperproof Snapshot and ARP are distinct functions**:
> - **Tamperproof Snapshot**: Locking mechanism (makes Snapshots indelible)
> - **ARP**: Detection mechanism (creates protective Snapshots when threats detected)
>
> Combined: "ARP detects threat → creates Snapshot → Tamperproof locks it" for multi-layer defense.

> **Note**: SnapLock is an ONTAP-native WORM option, but it is not a drop-in replacement for S3 Object Lock APIs. Validate regulatory requirements before choosing between SnapLock and standard S3 Object Lock.

## Recommended Trigger Patterns

| Pattern | Description |
|---------|-------------|
| POLLING (default) | EventBridge Scheduler + Discovery Lambda |
| EVENT_DRIVEN | FPolicy-based, near-real-time; not native S3 bucket notifications |
| HYBRID | Both polling and event-driven with deduplication |

---

## Presigned URL Support

> ⚠️ **Production Warning**: AWS Support explicitly states that operations marked "Not supported" should NOT be relied upon for production workloads, even when they return success today. Design alternatives for any workflow that requires presigned URL access to FSx for ONTAP S3 Access Points.

### Status: Listed as "Not supported" — but observed working

The AWS documentation compatibility table lists `Presign — Not supported`, but AWS Support responses have clarified the actual situation.

**AWS Support Findings (Summary)**:

1. **Presigning is not a server-side API operation** — It is a client-side SigV4 signature calculation that does not generate a network request
2. **Using a presigned URL with curl etc. actually executes a normal GetObject request** — The signature is simply included as query parameters instead of an Authorization header
3. **Since GetObject is Supported, GetObject via presigned URL cannot be structurally blocked** — It is impossible to disable presigned URLs without breaking GetObject itself
4. **Documentation intent**: Likely indicates "presigned URL workflows have not been officially tested" or "presigning scenarios involving unsupported features (SSE parameters, versioning parameters, etc.) may fail"

**Test Results (confirmed in a separate project)**:

| Operation | Presigned URL | Observed Result | Notes |
|-----------|--------------|-----------------|-------|
| GetObject | ✅ Confirmed working | HTTP 200, correct data returned | SigV4 query string authentication |
| PutObject | Not tested | — | May work based on same principle as GetObject |
| HeadObject | Not tested | — | Same as above |

### ⚠️ Production Use Warning

Clear guidance from AWS Support:

> **Operations listed as "Not supported" should NOT be relied upon for production workloads, even when they return success today.**

Reasons:
- Behavior may change without deprecation notice
- Results may be inconsistent across regions or over time
- May stop working after service-side updates
- May behave differently in edge cases

### Recommended Classification

| Feature | Status | Guidance |
|---------|--------|----------|
| GetObject, PutObject, ListObjectsV2 | **Supported** | Build freely |
| Conditional writes (If-None-Match) | **Blocked** | Cannot use (returns NotImplemented) |
| Presigned URLs | **Not supported (doc)** | Do not depend on. Design alternatives |
| ListObjectVersions | **Not supported (doc)** | Use ListObjectsV2 instead |

### Documentation Improvement Outlook

AWS Support has escalated documentation improvements to the FSx for ONTAP service team:
1. Removal or restructuring of the "Presign" row (since it is not an API)
2. Clarification distinguishing "Not supported + hard-blocked" (returns error) from "Not supported + may incidentally work" (no guarantee)

> **Content was rephrased for compliance with licensing restrictions. Source: AWS Support correspondence (May 2026).**

### AWS Documentation Reference

- [Access point compatibility — FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)
  - Compatibility table lists `Presign — Not supported` (documentation improvement escalation in progress)
- [re:Post: FSx for ONTAP S3 Access Points — Presigned URL behavior clarification](https://repost.aws/questions/QUtD1NGAd6RWGIxGlBRX4xpw)

---

## Troubleshooting Pointers

### Common Issues and Resolutions

| Symptom | Likely Cause | Resolution | Related UC |
|---------|-------------|------------|-----------|
| `AccessDenied` on ListObjectsV2 | Incorrect Resource ARN format in IAM policy | Use `arn:aws:s3:{region}:{account}:accesspoint/{name}` format (not alias) | All |
| `AccessDenied` on GetObject | S3 AP resource policy not configured | Add resource policy with `s3control put-access-point-policy` | All |
| `Connection timed out` from VPC Lambda | Accessing Internet Origin AP via S3 Gateway VPC Endpoint | Switch to VPC-external Lambda, or route via NAT Gateway | All |
| `Connection timed out` from VPC Lambda (VPC Origin AP) | Lambda is outside the AP's bound VPC | Place Lambda in the AP's bound VPC and verify S3 Gateway EP | All |
| Empty ListObjectsV2 response | Incorrect Prefix, or volume junction path mismatch | Verify volume junction path via ONTAP REST API and correct the Prefix | All |
| `ServiceUnavailable` on GetObject | Cannot reach FSx data plane | Verify FSx management IP / data LIF subnet and routing | All |
| `MalformedPolicy` on put-access-point-policy | Policy contains invalid actions (e.g., GetBucketLocation) | Only ListBucket + GetObject + PutObject are usable | All |
| Slow response at high concurrency | FSx Throughput Capacity saturation | Increase FSx Throughput Capacity (256/512 MBps), or reduce concurrency | UC with batch processing |
| Cross-region Textract/Comprehend failure | Service not available in ap-northeast-1 | Specify us-east-1 etc. via `TextractRegion` / `ComprehendMedicalRegion` parameter | UC2, UC5 |
| Lambda timeout (> 15 min) | Large file processing or FSx queuing due to high concurrency | Use Range GET for partial reads, or limit Map State concurrency | UC4, UC5, UC8 |

### Diagnostic Steps

1. **IAM verification**: Confirm the caller with `aws sts get-caller-identity`
2. **ARN verification**: Confirm IAM policy Resource uses `arn:aws:s3:{region}:{account}:accesspoint/{name}` format
3. **Network verification**: Check the combination of Lambda VPC settings and S3 AP NetworkOrigin (Internet/VPC)
4. **S3 AP policy verification**: Check resource policy with `aws s3control get-access-point-policy`
5. **ONTAP-side verification**: Confirm file system identity permissions (UNIX UID or Windows AD user)

---

## Cross-References from Use Cases

Reference points from each UC to this document:

| UC / Pattern | Relevant Compatibility Note |
|-------------|---------------------------|
| UC1-UC28 (All) | Trigger patterns — POLLING is default, S3 Event Notification is not supported |
| UC2, UC14 (Financial) | Cross-region invocation — Textract not available in ap-northeast-1 |
| UC5, UC7 (Healthcare/Genomics) | Range GET — Effective for partial reads of DICOM/genomics headers |
| UC3, UC11 (Real-time) | EVENT_DRIVEN — FPolicy-based, not native S3 notifications |
| UC4 (Media/VFX) | PutObject — Writing back processing results (max 5 GB) |
| FC1 (FlexCache Anycast/DR) | FlexCache × S3AP integration — Awaiting AWS release |
| FC2-FC6 (FlexClone patterns) | S3AP attachment to FlexClone volumes — Junction path configuration required |

---

## Related Documentation

- [S3AP Authorization Model](s3ap-authorization-model.md)
- [Trigger Mode Decision Guide](trigger-mode-decision-guide.md)
- [S3AP Benchmark Results](s3ap-benchmark-results.md)
- [S3AP Performance Considerations](s3ap-performance-considerations.md)
- [Deployment Profiles](deployment-profiles.md)
- [Partner/SI Delivery Checklist](partner-si-delivery-checklist.md)
- [Production Readiness](production-readiness.md)
