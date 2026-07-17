# S3 Standard Bucket User Guide — Differences from FSx for ONTAP S3 Access Points

🌐 **Language / 言語**: [日本語](s3-bucket-user-guide.md) | [English](s3-bucket-user-guide.en.md)

## Purpose of This Document

This document summarizes the key differences that users familiar with Amazon S3 standard buckets need to know when working with FSx for ONTAP S3 Access Points for the first time.

> **Important**: This pattern library is **not a replacement for S3 data lake patterns**. It is a **file-data integration pattern** for processing file data stored on FSx for ONTAP via S3-compatible APIs while maintaining NFS/SMB access paths.

## Standard S3 Bucket vs FSx for ONTAP S3 Access Point

| Feature | Standard S3 Bucket | FSx for ONTAP S3 AP |
|---------|:---:|:---:|
| Object storage backend | S3 | FSx for ONTAP volume |
| Versioning | ✅ Supported | ❌ Not supported |
| Object Lock (WORM) | ✅ Supported | ❌ Not supported (alternative: SnapLock) |
| Lifecycle policies | ✅ Supported | ❌ Not supported (alternative: Snapshot/SnapMirror) |
| S3 Event Notifications | ✅ Supported | ❌ Not supported (alternative: FPolicy) |
| Presigned URLs | ✅ Supported | ⚠️ Works but listed as "Not supported" (docs) |
| S3 Replication | ✅ Supported | ❌ Not supported (alternative: SnapMirror) |
| File protocol access (NFS/SMB) | ❌ | ✅ Alongside S3 API |
| Dual-layer authorization | IAM only | IAM + S3 AP policy + ONTAP file identity |
| Performance dependency | S3 service (auto-scaling) | FSx throughput capacity (provisioned) |
| Cost model | Storage + requests + transfer | Provisioned infrastructure + throughput |

## WORM / Immutable Storage Alternatives

When S3 Object Lock is not available, FSx for ONTAP provides the following alternatives:

| S3 Object Lock Feature | ONTAP Alternative | Characteristics |
|---|---|---|
| Compliance mode (WORM) | **SnapLock Compliance** | SEC 17a-4(f), FINRA 4511 compliant. No one can delete during retention period (including administrators) |
| Governance mode | **SnapLock Enterprise** | For internal compliance. Privileged delete available |
| Object Lock + Versioning | **Tamperproof Snapshot** | Sets lock duration on Snapshots using SnapLock Compliance clock. No one, including administrators, can delete during retention period |

Additionally, for ransomware protection:

| Purpose | ONTAP Feature | Characteristics |
|---|---|---|
| Anomaly detection + automatic protection | **Autonomous Ransomware Protection (ARP)** | Uses AI to monitor volume anomaly patterns (entropy, extension changes, IOPS) and automatically creates Snapshots upon threat detection |
| Snapshot deletion prevention | **Tamperproof Snapshot** | Locks Snapshots using SnapLock technology, preventing ransomware Snapshot deletion attacks |

> **Tamperproof Snapshot and ARP are separate features**:
> - **Tamperproof Snapshot**: Lock protection for Snapshots (mechanism to make them undeletable)
> - **ARP**: Threat detection and automatic response (mechanism to automatically create Snapshots upon anomaly detection)
>
> Combining both enables multi-layered defense: "ARP detects threat → automatic Snapshot creation → Tamperproof prevents deletion."

> **Sources**: [How SnapLock works — FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/how-snaplock-works.html), [Snapshot locking — NetApp ONTAP](https://docs.netapp.com/us-en/ontap/snaplock/snapshot-lock-concept.html), [ARP — FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/ARP.html)

**Recommended Design**:
- For audit artifacts requiring regulatory WORM → Output to SnapLock Compliance volume, or copy to standard S3 bucket (Object Lock enabled)
- For Snapshot tamper prevention → Enable Tamperproof Snapshot
- For ransomware detection/automatic response → Enable ARP at volume level (no additional cost)
- For point-in-time recovery → ONTAP Snapshot (alternative to S3 Versioning)

> **Note**: SnapLock is ONTAP's native WORM option, but it is not a drop-in replacement for the S3 Object Lock API. Verify whether SnapLock or standard S3 Object Lock is appropriate based on your regulatory requirements.

## Versioning Alternatives

S3 Versioning and ONTAP Snapshot represent different recovery models:

| Characteristic | S3 Versioning | ONTAP Snapshot |
|----------------|---|---|
| Protection granularity | Per individual object | Point-in-time of entire file system |
| Retention cost | Storage for all versions | Differential blocks only (space-efficient) |
| Restore | Retrieve specific version | Individual file restore from Snapshot or volume restore |
| Deletion protection | Delete Marker + version retained | Retained in Snapshot (even if file deleted on volume) |

## Event Notification Alternatives

| S3 Feature | ONTAP Alternative | Description |
|---|---|---|
| S3 Event Notifications | **FPolicy** (event-driven pipeline) | Notifies file creation/write/rename via TCP |
| EventBridge S3 events | **EventBridge Scheduler** (polling) | Periodically detects new files via ListObjectsV2 |

This pattern library primarily uses EventBridge Scheduler, but for real-time event processing requirements, refer to the FPolicy pipeline in Phase 10-12.

## Performance Differences

| Characteristic | Standard S3 | FSx for ONTAP S3 AP |
|---|---|---|
| Scaling | Automatic based on request rate | Depends on FSx throughput capacity (provisioned) |
| Latency | Single-digit ms (same region) | Tens of ms (via S3 AP data plane) |
| Parallelism | 5,500+ req/s/prefix with prefix parallelism | FSx throughput capacity is the bottleneck |
| During throughput changes | No impact | S3 AP may return ServiceUnavailable |

> Unlike standard S3 buckets, FSx for ONTAP S3 AP availability may be affected by FSx file system operational changes (such as throughput capacity modifications).

## Security Differences

With standard S3 buckets, allowing access via Bucket Policy is sufficient, but with FSx for ONTAP S3 AP:

> **FSx for ONTAP S3 AP requests must pass both AWS authorization (IAM + S3 AP policy) and file system authorization (ONTAP file identity). IAM Allow alone is insufficient.**

Recommended checks:
- Validate S3 AP policy with IAM Access Analyzer before deployment
- Pre-verify file system identity permissions from NFS/SMB clients
- Test Access Denied scenarios (verify that unintended file access is blocked)

## NetworkOrigin Considerations

| Standard S3 Bucket | FSx for ONTAP S3 AP |
|---|---|
| VPC Endpoint is a routing choice | NetworkOrigin is **determined at creation, immutable** |
| Gateway/Interface EP can be added/changed later | Internet-origin ↔ VPC-origin cannot be changed |

## Retention / Lifecycle Alternative Designs

Since S3 Lifecycle policies are not available:

- **Short-term retention** (intermediate artifacts): ONTAP volume quota + periodic deletion scripts
- **Long-term retention** (audit artifacts): SnapLock Compliance volume, or copy to standard S3 bucket (Object Lock)
- **Tiering**: ONTAP auto-tiering (SSD → Capacity Pool) as alternative to S3 Intelligent-Tiering
- **Expiration deletion**: Lambda-based periodic cleanup + data classification labels for decision-making

## Data Strategy Decision Criteria

| Strategy | Use When |
|---|---|
| Keep on FSx for ONTAP + process via S3 AP | File semantics, NFS/SMB compatibility, migration cost avoidance |
| Copy analysis results to standard S3 | Data lake governance, Lifecycle, Object Lock, Lake Formation needed |
| Full S3 migration | Object-native application modernization |

## Observability Differences

In addition to standard S3 bucket auditing (CloudTrail data events, S3 Server Access Logs, Storage Lens), FSx for ONTAP provides:

```
AWS API plane:  CloudTrail, CloudWatch, Step Functions execution history
Application:    Lambda logs, EMF metrics, lineage records
File-system:    FSx CloudWatch metrics, ONTAP REST API, FPolicy audit logs
```

> Observe both planes (AWS + file system).

---

## FAQ

| Question | Answer |
|----------|--------|
| Is this a regular S3 bucket? | **No**. It is an S3 API access path to an FSx for ONTAP volume |
| Can I use Lifecycle? | **No**. Use Snapshot/SnapMirror/auto-tiering |
| Can I use Versioning? | **No**. ONTAP Snapshot is the alternative |
| Can I use Object Lock? | **No**. SnapLock (Compliance/Enterprise) is the alternative |
| Can I use Presigned URLs? | **Works** (listed as "Not supported" in docs, but succeeds as a signed GetObject request. AWS Support advises against production reliance) |
| Can I also access via NFS/SMB? | **Yes**. Concurrent access to the same data is possible |
| Should I use this as a data lake? | **Typically No**. Use as an integration boundary, route analysis output to standard S3 |
| Can I use S3 Event Notifications? | **No**. Use FPolicy or EventBridge Scheduler |

---

> **Governance Caveat**: This document provides technical guidance and is not legal, compliance, or regulatory advice.
