# ONTAP Integration Notes — Coexistence Guide for S3 AP and Existing NAS Operations

🌐 **Language / 言語**: [日本語](ontap-integration-notes.md) | [English](ontap-integration-notes.en.md)

## Overview

When using FSx for ONTAP S3 Access Points, it is important to understand and design for the impact on existing NFS/SMB operations. This document provides guidance for ONTAP administrators and NAS architects.

## ONTAP Scope Assumptions

| Design Item | Production Considerations |
|-------------|--------------------------|
| SVM | Define SVM boundaries per UC or establish shared SVM policies |
| Volume | Map UC file prefixes to specific volumes |
| Protocol | Verify NFS/SMB/S3 AP access paths independently |
| Identity | Validate S3 AP file system identity (UNIX/AD) mapping |
| Snapshot | Confirm output writes do not conflict with Snapshot/backup policies |
| Export Policy | S3 AP access does not traverse Export Policies (controlled by IAM + S3 AP Policy) |

### Recommended ONTAP Scoping

| Pattern Type | Recommended Boundary |
|---|---|
| Low-risk Demo / PoC | Dedicated prefix within existing volume |
| PII / HR workflow (UC27) | Dedicated volume (access-restricted + audited) |
| Safety-critical inspection (UC22/UC25) | Dedicated output volume + review prefix |
| Multi-team shared data | SVM isolation or per-team S3 AP |
| Regulated workloads | Dedicated volume + SnapLock retention + audit policy |

## How S3 AP Output Files Appear from NFS/SMB

When PutObject is performed via S3 AP:
- **File owner**: The file system identity associated with the S3 AP (UNIX UID or Windows AD user)
- **Permissions**: Follows the default umask/ACL of the file system identity
- **Timestamp**: Write time is recorded as mtime
- **File name**: S3 object key is used directly as the path (`/` serves as directory separator)

> **Source**: [Managing access point access — FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-ap-manage-access-fsxn.html) — "all S3 API operations performed through the access point are authorized using that user's permissions on the file system"

### Verification Items from NFS/SMB Clients

| Verification Item | Method |
|-------------------|--------|
| Output file owner | Check with `ls -la` (NFS) / Properties (SMB) |
| Read permissions | Verify with `cat` (NFS) / `type` (SMB) from client |
| Directory creation | Confirm intermediate directories are auto-created by S3 AP PutObject |
| File naming convention | Pre-define output prefixes (e.g., `reports/daily/YYYY-MM-DD/`) |

## Trigger Mode Guidance

| Workload Characteristics | Recommended Trigger Mode |
|---|---|
| Batch document processing (daily/hourly) | EventBridge Scheduler (POLLING) |
| Immediate processing on new file arrival | FPolicy event-driven |
| Large-scale periodic analysis | Scheduler |
| Safety inspection image upload | FPolicy or HYBRID |
| Low-frequency governance reports | Scheduler |

## UC × FlexCache/FlexClone Pattern Combinations

| UC | Recommended FC Pattern | Reason |
|---|---|---|
| UC22 Transportation inspection | FC1 (FlexCache Anycast DR) | Inspection image caching at remote sites |
| UC25 Power equipment inspection | FC1 / FC5 | Drone image sharing across distributed teams |
| UC28 Chemical SDS/Lab notes | FC5 (Life Sciences) | Secure collaboration on research data |
| UC19 Ad creative | FC2 / FC6 | Creative/render pipeline |
| UC18 Telecom CDR analysis | — | Direct Athena query, no caching needed |

## Data Protection Notes

| Artifact | Snapshot Target | SnapMirror Target | Retention Period |
|----------|:---:|:---:|---|
| Input files (customer data) | ✅ | ✅ | Existing customer policy |
| Extracted JSON results | UC-defined | UC-defined | Based on Success Metrics |
| Human Review decision records | ✅ | ✅ | Audit retention period |
| Intermediate prompts/outputs | Usually No | No | Short-term retention (7-30 days) |
| Manifest JSON | UC-defined | UC-defined | Retained as execution history |

> **Recommendation**: Place output writes in a separate prefix or volume from input data to enable independent Snapshot/SnapMirror policy management.

## Security and Identity Notes

- S3 AP access is not governed by NFS export policies in the same way as NFS clients. Requests are first authorized by AWS policies (IAM + S3 AP policy), then by the FSx for ONTAP file-system identity associated with the access point
- Verify AD/UNIX mapping consistency via ONTAP REST API (`security login show`, `vserver name-mapping show`)
- Test access-denied scenarios: verify that unintended file access is blocked
- Confirm output file permissions from NFS/SMB clients (expected ownership/permissions)
- Be cautious about logging file paths if they contain sensitive information
- Validate S3 AP policy with IAM Access Analyzer before production deployment

## NetApp Support Diagnostic Bundle

Information to provide to NetApp/AWS support during incidents:

```
- FSx file system ID
- SVM name
- Volume name (junction path)
- S3 AP name and NetworkOrigin (Internet/VPC)
- Failing object key (redacted if sensitive)
- NFS/SMB からの同一ファイルアクセス結果
- ONTAP REST API レスポンス (該当する場合)
- CloudWatch Lambda execution ID
- Step Functions execution ARN
- FSx CloudWatch metrics (DataReadBytes, NetworkThroughput)
```

## Notes for OT / Manufacturing Environments

UC22 (Transportation) / UC25 (Power) / UC28 (Chemical) involve workflows near OT environments, however:

> **Important**: These patterns are workflows for **inspection analysis and maintenance prioritization**, not systems for real-time control or safety actuation.

OT environment-specific considerations:
- Separation of batch processing vs real-time requirements
- Preference for VPC-origin S3 AP (private network requirements)
- Data staging for offline/edge scenarios
- Strict change window management
- Definition of manual override processes

## Notes on FSx for ONTAP Costs

> FSx for ONTAP costs vary by region, deployment type (Single-AZ/Multi-AZ), SSD capacity, Capacity Pool capacity, throughput capacity, backups, and data transfer. The $194/month figure cited in this repository is a baseline estimate for Single-AZ / 128 MBps / 1 TB SSD and is not a universal price.

## Three Stages: DemoMode → Clone PoC → Production

| Stage | Data Source | Characteristics |
|---|---|---|
| DemoMode | Synthetic S3 data | No FSx for ONTAP required, can start same day |
| Clone PoC | FlexClone (production-like data) | Validation with near-production data, space-efficient |
| Production | Live FSx for ONTAP S3 AP | Full authorization model + governance |

## Field Feedback Log

| Finding | Impact | Evidence | Request |
|---------|--------|----------|---------|
| S3 AP returns ServiceUnavailable during throughput changes | Operational risk | Phase 14 timeline | Documentation of behavior / availability improvement |
| Presigned URL works but is unsupported | Customer confusion | AWS Support case | Documentation clarification |
| VPC-origin benchmark not conducted | Design gap | Phase 15 Next | Guidance needed |
| FlexCache × S3 AP not supported | Feature gap | FC1 blocker | Roadmap consideration |
| ListObjectsV2 high latency (30-80x vs native S3) | Performance constraint | Benchmark data | Optimization |

---

> **Governance Caveat**: This document provides technical guidance and is not legal, compliance, or regulatory advice.
