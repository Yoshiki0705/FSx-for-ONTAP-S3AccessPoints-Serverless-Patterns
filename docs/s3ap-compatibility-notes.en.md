# S3AP Compatibility Notes

🌐 **Language / 言語**: [日本語](s3ap-compatibility-notes.md) | [English](s3ap-compatibility-notes.en.md)

## What FSx for ONTAP S3 Access Points Provide

FSx for ONTAP S3 Access Points provide an S3-facing access boundary for file data stored in FSx for ONTAP. Data remains on FSx for ONTAP and can continue to be accessed through NFS and SMB.

## S3 AP vs NFS/SMB: When to Use Which

| Requirement | Prefer S3 AP | Prefer NFS/SMB |
|---|:---:|:---:|
| Serverless integration (Lambda, Step Functions) | ✅ | — |
| POSIX semantics required (lock, rename, symlink) | — | ✅ |
| Large sequential file processing | △ (50 GiB object limit) | ✅ |
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
| PutObject | ✅ Tested |
| Range GET | ✅ Tested |
| HeadObject | ✅ Tested |
| DeleteObject | ✅ Tested |
| MultipartUpload (`CreateMultipartUpload` / `UploadPart` / `CompleteMultipartUpload`) | ✅ Tested |

> Size limits differ per API. See the next section, "Upload size limits".

## Upload size limits

### 1. Pick the method from the file size

Once you know the size of the file you want to upload, the method is determined.

| File size | Method to use | Possible |
|-----------|---------------|:---:|
| **Up to 5 GiB** | Single `PutObject` (one API call) | ✅ |
| **Above 5 GiB up to 50 GiB** | Multipart upload (required) | ✅ |
| **Above 50 GiB** | Not possible through the S3 AP | ❌ Place the file on the volume via NFS/SMB |
| Download (`GetObject`) | No size limit | ✅ Files larger than 50 GiB can be retrieved |

> High-level SDK APIs (`upload_file` / `TransferManager`, Amplify Storage Browser, and similar) switch to multipart automatically above a threshold, so you usually do not choose the method yourself. **They do not, however, work around the 50 GiB limit.**

### 2. How methods, APIs, and limits map

**Method A: single `PutObject`** — one API call produces the object. That single call's limit is also the object size limit.

```
PutObject (one call) ──▶ object complete
   limit 5 GiB
```

**Method B: multipart upload** — three APIs called in sequence. Each limit applies to a different thing.

```
CreateMultipartUpload ──▶ UploadPart × N ──▶ CompleteMultipartUpload ──▶ object complete
   no limit                per-part            whole-object total
                           limit 5 GiB         limit 50 GiB
                           (no cumulative      (first checked here)
                            check)
```

| API called | What the limit applies to | Measured | Checked when |
|------------|---------------------------|----------|--------------|
| `PutObject` (Method A) | One object | **5 GiB** = 5,368,709,120 bytes | On Content-Length, immediately |
| `UploadPart` (Method B) | One part | **5 GiB** = 5,368,709,120 bytes | On Content-Length, immediately |
| `CompleteMultipartUpload` (Method B) | Whole-object total | **50 GiB** = 53,687,091,200 bytes | After all parts are transferred |

Measurement details and reproduction: [measured object size limits](s3ap-object-size-limits-verification.en.md)

> **Watch the units**: "5 GB" and "50 GB" in the AWS documentation are both **binary (GiB)**. Read as decimal, that is off by 368 MB at 5 GB and by 3.7 GB at 50 GB.
>
> The increase from 5 GiB to 50 GiB arrived as a documentation update; no corresponding What's New announcement was found (archived copies show 5 GB on 2026-03-08 and 50 GB on 2026-06-25).

### 3. What happens when you exceed a limit — Method B has a trap

⚠️ **The whole-object limit is checked only at `CompleteMultipartUpload`.** `UploadPart` performs no cumulative size check. In the measured 50 GiB + 1 test, all 11 parts were accepted and the rejection came only **after about 10 minutes (590 s) of transferring the entire payload**.

| | Method A (`PutObject`) | Method B (`UploadPart`) | Method B (`CompleteMultipartUpload`) |
|---|---|---|---|
| Checked on | Content-Length | Content-Length | After all parts transferred |
| Time to failure | Immediate (~2.7 s) | Immediate | **After the full transfer** |
| Transfer wasted | Near zero (~12 MB) | Near zero | **Up to 50 GiB** |
| Returns `MaxSizeAllowed` | ✅ Yes | ✅ Yes | ❌ **No** |

```
Code    : EntityTooLarge
Message : Your proposed upload exceeds the maximum allowed size
Extra   : {'ProposedSize': '5368709121', 'MaxSizeAllowed': '5368709120'}   <- PutObject / UploadPart only
```

**Implementation recommendations**:

- **Validate client-side that the object is 50 GiB or smaller before starting the upload.** There is no service-side pre-flight check, and the `CompleteMultipartUpload` error omits `MaxSizeAllowed`, so an overage is only discovered after the transfer finishes.
- `CompleteMultipartUpload` itself is slow (about 557 s for 50 GiB). Set a generous `read_timeout` (1800 s was used in testing).

Sources: [Access point compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html) / [Uploading objects (Amazon S3 User Guide)](https://docs.aws.amazon.com/AmazonS3/latest/userguide/upload-objects.html)
>
> Sources: [Access point compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html) / [Uploading objects (Amazon S3 User Guide)](https://docs.aws.amazon.com/AmazonS3/latest/userguide/upload-objects.html)

## Not Equivalent to Full S3 Bucket Semantics

Not all bucket-level features or integration patterns apply directly:

- Native S3 bucket notifications (GetBucketNotificationConfiguration not supported)
- Bucket lifecycle policies
- Bucket versioning
- Object Lock (on the S3AP itself)
- Presigned URLs (**Listed as "Not supported"** — but observed working; AWS documentation correction submitted, not yet published. See [Presigned URL Support](#presigned-url-support) for ONTAP version requirements and details)

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

---

## S3 Annotations (GA 2026-06-16)

### Overview

Amazon S3 Annotations attach mutable structured metadata (JSON/XML/YAML/text) to an object, up to 1 GB total (1,000 annotations x 1 MB). Annotations propagate automatically when an object is copied or replicated, and are deleted automatically with the object. They are queryable from Athena via S3 Metadata annotation tables.

### API

| API | Description |
|-----|-------------|
| `PutObjectAnnotation` | Add or update an annotation |
| `GetObjectAnnotation` | Retrieve an annotation by name |
| `ListObjectAnnotations` | List an object's annotations |
| `DeleteObjectAnnotation` | Delete an annotation |

### Support status on FSx for ONTAP S3 Access Points

| API | FSx for ONTAP S3 AP status | HTTP status | Notes |
|-----|:--:|:--:|-------|
| PutObjectAnnotation | ❌ Not supported | 501 NotImplemented | Confirmed by hands-on testing on 2026-06-18 |
| GetObjectAnnotation | ❌ Not supported (inferred) | — | Because PutObjectAnnotation is unsupported |
| ListObjectAnnotations | ❌ Not supported (inferred) | — | Same as above |
| DeleteObjectAnnotation | ❌ Not supported (inferred) | — | Same as above |

> **Test result (2026-06-18)**: Calling `PutObjectAnnotation` through an FSx for ONTAP S3 AP alias returns `501 NotImplemented` — `"An access point you provided implies functionality that is not implemented"`. The same API was confirmed working against a standard S3 bucket (HTTP 200).
>
> **Next action**: File a feature request with AWS Support. See `docs/investigations/s3-annotations-fsxn-compatibility.md` for details.

### Recommended pattern (settled)

FSx for ONTAP S3 AP does not support the annotation APIs (501 NotImplemented confirmed). We recommend this pattern:

```
FSx for ONTAP S3 AP (READ) -> Lambda processing -> Standard S3 Bucket (WRITE + Annotations)
```

Apply annotations to the destination used by `OutputDestination=STANDARD_S3`, so that rich metadata is associated with the processing results derived from FSx for ONTAP data.

### How this project would use them

| Usage pattern | Annotation name | Content |
|---------------|-----------------|---------|
| Processing metadata | `processing_metadata` | UC ID, confidence, human review, model ID, lineage |
| Data classification | `data_classification` | Classification level, labels, rationale |
| AI analysis summary | `ai_summary` | LLM-generated summary text |
| Citations | `citations` | Source file path, chunk position, quoted text |
| Audit trail | `audit_trail` | Actor, timestamp, approval state |

### Implementation module

`shared/s3_annotations.py` provides the `AnnotationHelper` class. In environments where the API is unsupported, three fallback behaviours can be selected:

- `skip` (default): log and skip
- `tag`: fall back to Object Tagging (subject to the 10-tag / 256-character limits)
- `error`: raise an exception

### Use cases if annotations become supported on FSx for ONTAP S3 AP

If annotations were supported through an FSx for ONTAP S3 AP, the following would become possible:

- Attach AI analysis results directly to files on FSx for ONTAP as annotations
- NFS/SMB users see only the file itself, while annotations remain exclusive to the serverless pipeline
- Cross-volume metadata search through S3 Metadata annotation tables
- Hold Permission-Aware RAG ACL metadata in annotations

> **Feature request candidate**: Support `PutObjectAnnotation` / `GetObjectAnnotation` on FSx for ONTAP S3 Access Points, enabling AI metadata to be attached to NAS files.

---

## Recommended Trigger Patterns

| Pattern | Description |
|---------|-------------|
| POLLING (default) | EventBridge Scheduler + Discovery Lambda |
| EVENT_DRIVEN | FPolicy-based, near-real-time; not native S3 bucket notifications |
| HYBRID | Both polling and event-driven with deduplication |

---

## Presigned URL Support

> ⚠️ **Production Warning**: The published AWS compatibility table still lists `Presign — Not supported`. In a later response, AWS Support confirmed that presigned URLs are supported at the ONTAP layer (subject to version requirements) and has submitted a documentation correction, but **that correction is not yet published**. Until the published documentation is updated, design alternatives for any production workload that would depend on presigned URLs (see "Additional AWS Support Confirmation" below).

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

### Additional AWS Support Confirmation (ONTAP Version Requirements)

In a subsequent response, AWS Support confirmed — citing NetApp KB articles — that **ONTAP S3 does support presigned URLs**. The supported signature versions depend on the ONTAP release.

| ONTAP version | Presigned URL signature versions |
|---------------|----------------------------------|
| 9.16.1 and later | v4 + v2 presigned URLs |
| 9.11.1 and later | v4 presigned URLs only |
| Earlier than 9.11.1 | Presigned URLs not supported |

- NetApp recommends using v4 signatures where possible
- This repository's verification environment runs ONTAP 9.17.1P6, which satisfies both thresholds
- This confirmation concerns **ONTAP-layer** behavior. Until the AWS compatibility table for FSx for ONTAP S3 Access Points is updated, the production use warning below remains in effect

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
| Presigned URLs | **Not supported (doc) / correction submitted, unpublished** | Do not depend on until the published docs are corrected. Design alternatives (ONTAP 9.11.1+ supports v4) |
| ListObjectVersions | **Not supported (doc)** | Use ListObjectsV2 instead |

### Presigned URL Alternatives

Ways to provide time-limited file access without depending on presigned URLs:

| Alternative | Summary | Use case |
|-------------|---------|----------|
| API Gateway + Lambda proxy | Download through Lambda with IAM/JWT authentication | Web apps, mobile |
| CloudFront signed URLs | Origin controlled via Lambda@Edge | Large-scale distribution |
| Temporary STS credentials | Scoped IAM (time-limited, prefix-limited) | Batch processing, partner integration |
| Application-layer broker | Includes audit logging and access revocation | Regulated industries |

### Documentation Improvement Outlook

AWS Support has escalated documentation improvements to the FSx for ONTAP service team:
1. Removal or restructuring of the "Presign" row (since it is not an API)
2. Clarification distinguishing "Not supported + hard-blocked" (returns error) from "Not supported + may incidentally work" (no guarantee)
3. Reflecting presigned URL support by ONTAP release (v4 from 9.11.1, v2 from 9.16.1)

**Current status**: AWS Support has submitted the documentation correction to the internal documentation team and work is in progress. However, **the correction has not yet been reflected in the published documentation**. Update this section once the published table changes.

> **Content was rephrased for compliance with licensing restrictions. Sources: AWS Support correspondence (May–July 2026) and the NetApp KB articles linked below.**

### AWS Documentation Reference

- [Access point compatibility — FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)
  - Compatibility table lists `Presign — Not supported` (correction submitted, not yet published)
- [re:Post: FSx for ONTAP S3 Access Points — Presigned URL behavior clarification](https://repost.aws/questions/QUtD1NGAd6RWGIxGlBRX4xpw)
- [NetApp KB: What version of ONTAP support pre-signed URLs for S3 bucket](https://kb.netapp.com/on-prem/ontap/da/S3/S3-KBs/What_version_of_ONTAP_support_pre-signed_URLs_for_S3_bucket)
- [NetApp KB: Does ONTAP S3 support AWSv2 signatures?](https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Software/ONTAP_OS/Does_ONTAP_S3_support_AWSv2_signatures)

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
| UC4 (Media/VFX) | PutObject — Writing back processing results (single PUT 5 GiB / up to 50 GiB via multipart) |
| FC1 (FlexCache Anycast/DR) | FlexCache × S3AP integration — Awaiting AWS release |
| FC2-FC6 (FlexClone patterns) | S3AP attachment to FlexClone volumes — Junction path configuration required |

---

## Related Documentation

- [S3AP Authorization Model](s3ap-authorization-model.en.md)
- [Trigger Mode Decision Guide](trigger-mode-decision-guide.en.md)
- [S3AP Benchmark Results](s3ap-benchmark-results.en.md)
- [S3AP Performance Considerations](s3ap-performance-considerations.en.md)
- [Deployment Profiles](deployment-profiles.en.md)
- [Partner/SI Delivery Checklist](partner-si-delivery-checklist.en.md)
- [Production Readiness](production-readiness.en.md)
