# Feature Requests: FSx for NetApp ONTAP S3 Access Points Improvements

**Submitter**: Yoshiki Fujiwara (NetApp Inc.)
**Date**: 2026-05-10
**Project**: [fsxn-s3ap-serverless-patterns](https://github.com/Yoshiki0705/fsxn-s3ap-serverless-patterns)
**Status**: Draft for AWS Support / re:Post submission

---

## Executive Summary

Amazon FSx for NetApp ONTAP (FSxN) integration with Amazon S3 Access Points (AP) enables enterprise file data to be consumed by AWS AI/ML and analytics services without data movement. This is a breakthrough integration for use cases spanning 17 industries (EDA, DICOM imaging, VFX rendering, FOIA archives, satellite imagery, etc.).

However, during production implementation of 17 serverless use cases (UC1–UC17) against FSxN S3AP in `ap-northeast-1`, we identified **four critical gaps** that force customers to fall back to standard S3 buckets for output and orchestration — undermining the core value proposition of "one copy of data, accessed everywhere".

This document captures the gaps, their business impact, and requested improvements, with direct references to the current AWS documentation.

---

## Background: Why This Matters

The tagline of the FSxN S3AP integration is that **"Data continues to reside on the FSx for ONTAP file system and remains accessible via NFS and SMB protocols alongside the S3 API"** ([Accessing your data via Amazon S3 access points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)). For the customer, this means:

- Design engineers keep editing GDS/OASIS files via SMB
- Data scientists query the same files in place via Athena
- ML pipelines write enrichment data back so the SMB user sees the AI output alongside the source file

The third bullet is where the current gaps bite. AI/ML pipelines built on Rekognition, Textract, Comprehend, Bedrock, and Athena today must write their outputs to **a separate standard S3 bucket** because either the output API path is unsupported on FSxN S3AP, or the event-driven orchestration primitives don't exist.

This breaks the "one copy" story: SMB/NFS users cannot see the AI enrichment without a separate sync step. Customers we've talked with (semiconductor EDA, government archives, insurance) explicitly requested this capability.

---

## FR-1: Enable Athena to Write Query Results to FSxN S3 Access Points

### Current State (verbatim-limited citation)

From [Query files with SQL using Amazon Athena (FSx ONTAP User Guide)](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-query-data-with-athena.html):

> "Athena writes query results to an Amazon S3 bucket, not to the FSx for ONTAP volume."
>
> "Read-only access. Athena reads data from your FSx for ONTAP volume through the access point. Athena query results are written to the Amazon S3 results bucket, not back to the FSx for ONTAP volume."

*Content was rephrased for compliance with licensing restrictions; see linked page for the authoritative wording.*

This means Athena Workgroup `ResultConfiguration.OutputLocation` must point to a regular `s3://bucket/...` URI. A customer who wants the query output to live alongside the source data on FSxN has to run a post-processing job to copy results from the Athena S3 bucket back into FSxN via the S3AP.

### Impact on Our Patterns

| UC | Impact |
|----|--------|
| UC6 semiconductor-eda | DRC aggregation Athena results cannot be written to `athena-results/` on FSxN S3AP |
| UC7 genomics-pipeline | FASTQ analysis summary tables forced to separate S3 |
| UC8 energy-seismic | Seismic survey statistics cannot be colocated with `.segy` files |
| UC13 education-research | Research paper metadata queries forced to separate S3 |

### Requested Behavior

Allow Athena Workgroup `ResultConfiguration.OutputLocation` to accept an FSxN S3AP alias or ARN (e.g., `s3://my-ap-alias-ext-s3alias/athena-results/` or the equivalent ARN form). The service must honor SSE-FSX as the encryption mode and the 5 GB object size limit automatically.

### Workaround in this Project

Standard S3 bucket (`AWS::S3::Bucket` resource) provisioned per stack for Athena results only; all other output is on FSxN S3AP.

---

## FR-2: S3 Event Notifications / EventBridge Events for FSxN S3 Access Points

### Current State

From [Access point compatibility (FSx ONTAP User Guide)](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html) — partial operation compatibility table:

| Operation | FSxN S3AP status |
|-----------|------------------|
| `GetBucketNotificationConfiguration` | Not supported |
| `PutBucketNotificationConfiguration` | *(not listed; equivalent to not supported)* |

There is no documented path to configure S3 Event Notifications (SNS / SQS / Lambda / EventBridge) when an object is put, updated, or deleted on the FSx volume via S3AP.

### Impact on Our Patterns

All 17 UCs must use a **polling model**: EventBridge Scheduler → Discovery Lambda → `ListObjectsV2` on the S3AP → diff with previous snapshot stored in DynamoDB. This is wasteful and introduces latency of up to the scheduler interval (default 1 hour in our stacks).

A production event-driven architecture would reduce detection-to-processing latency from ~1 hour to seconds and cut Lambda invocation cost by orders of magnitude for low-change workloads.

### Requested Behavior

Either:
- **Option A**: Support `PutBucketNotificationConfiguration` on the S3AP and deliver `s3:ObjectCreated:*`, `s3:ObjectRemoved:*`, etc. to SNS / SQS / Lambda
- **Option B**: Emit ONTAP file events (create/update/delete on the junction-pathed volume) to Amazon EventBridge as native `aws.fsx` events (source: `aws.fsx`, detail-type: `FSxN Object Event`) — delivered at the S3AP abstraction layer, so the event payload carries the S3 key form

Option B would also help non-S3AP consumers that use NFS/SMB for writes.

### Workaround in this Project

`shared/discovery_handler.py` implements the polling pattern with a DynamoDB-backed change tracker table (`TableClass: Standard`, TTL enabled, partition key = `file_key`). Each UC pays the cost of ListObjectsV2 over the entire prefix every `ScheduleExpression` cycle.

---

## FR-3: S3 Object Lifecycle Policies for FSxN S3 Access Points

### Current State

From [Access point compatibility (FSx ONTAP User Guide)](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html) — Limitations section:

> Object Lifecycle is listed alongside Object Versioning, Object Lock, Static Website Hosting, and conditional writes as not supported.

*Content was rephrased for compliance with licensing restrictions.*

### Impact on Our Patterns

| UC | Lifecycle requirement |
|----|----------------------|
| UC1 legal-compliance | 7-year contract retention (WORM-equivalent) |
| UC16 government-archives | Federal Records Act classifications (permanent / 30 years / 7 years / 3 years) |
| UC5 healthcare-dicom | HIPAA retention (6 years minimum in US) |
| UC14 insurance-claims | State-specific claim retention (typically 5–10 years) |

Without lifecycle rules at the S3AP layer, customers must either (a) run a parallel lifecycle sweep via a custom Lambda/Batch job, or (b) use ONTAP-native SnapMirror / tiering policies which are not surfaced to application developers through the S3 API.

### Requested Behavior

Support `PutBucketLifecycleConfiguration` / `GetBucketLifecycleConfiguration` on the S3AP. Map S3 lifecycle `Transition` actions to ONTAP tiering (`to AWS_CLOUD`) where feasible, and `Expiration` actions to ONTAP file deletion on the volume.

### Workaround in this Project

Custom retention sweeper Lambda (not yet implemented, tracked as backlog for UC1 / UC16).

---

## FR-4: Object Versioning and Presigned URL Support

### Current State

From [Access point compatibility (FSx ONTAP User Guide)](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html):

| Operation | Status |
|-----------|--------|
| `ListObjectVersions` | Not supported |
| `Presign` | Not supported |

Object Versioning is also listed in the Limitations section.

### Impact on Our Patterns

| UC | Pain point |
|----|-----------|
| UC1 legal-compliance | Contract version history requires external versioning DB |
| UC16 government-archives | FOIA release versions (redacted vs unredacted) cannot be tracked as S3 versions |
| UC9 autonomous-driving | ML model version tagging pattern breaks |
| All | Sharing a generated report with an external auditor requires a presigned URL; today we must proxy via a standard S3 copy + presign |

### Requested Behavior

- **Versioning**: Expose ONTAP Snapshots as S3 object versions, similar to how SnapMirror exposes NetApp volume history. Customers would opt in per S3AP.
- **Presign**: Support `CreatePresignedUrl` with SigV4 against the S3AP alias or ARN, so applications can share time-limited access to FSxN objects without a copy step.

### Workaround in this Project

External DynamoDB table for document version tracking; standard S3 copy + presign for external sharing (not implemented, backlog).

---

## Secondary / Informational Findings

While preparing these FRs, we also noted the following which are *documented but not addressed by this request* — we accept them as fundamental design choices of the integration:

1. **5 GB upload size limit** — documented, aligned with pre-multipart-upload S3 semantics.
2. **SSE-FSX as the only encryption mode** — expected given FSx-managed encryption.
3. **`FSX_ONTAP` as the only storage class** — expected.
4. **`GetObjectAcl` / `PutObjectAcl` limited to `bucket-owner-full-control`** — acceptable; ONTAP file-level NTFS ACLs provide the granular access control via the dual-authorization model described in [the AWS Storage Blog](https://aws.amazon.com/blogs/storage/enabling-ai-powered-analytics-on-enterprise-file-data-configuring-s3-access-points-for-amazon-fsx-for-netapp-ontap-with-active-directory/).
5. **`CopyObject` / `UploadPartCopy` limited to same-region and same-access-point** — understood, cross-AP copy forces a download-upload cycle.

---

## Priority Ranking (From Customer Perspective)

| Rank | FR | Why this ordering |
|------|-----|-------------------|
| 1 | FR-2 (Event Notifications) | Architecturally unlocks event-driven patterns across all 17 UCs. Current polling is wasteful. |
| 2 | FR-1 (Athena result location) | Cleanly closes the "one copy" story for analytics use cases. |
| 3 | FR-3 (Lifecycle) | Critical for regulated industries (finance, healthcare, government). |
| 4 | FR-4 (Versioning + Presign) | Nice-to-have; workarounds exist. |

---

## Business Case Summary

- **Direct customer signal**: The three Public Sector UCs (UC15 defense satellite, UC16 FOIA, UC17 smart city geospatial) were added to this project in response to customer requests in Q1 2026. Customers explicitly asked "why do our ML pipeline outputs live in a different S3 bucket from the source data on our FSx?"
- **Integration value erosion**: Every time a customer has to provision a separate standard S3 bucket for outputs, the integration's promise of "no data movement" weakens. Most PoCs end up with 2-3 S3 buckets per use case.
- **Cost implication**: Polling at 1-hour intervals over 17 UCs × N accounts = tens of thousands of wasted ListObjectsV2 calls per day per customer.

---

## References

All references are to AWS-authored documentation or AWS-authored blog posts, accessed 2026-05-10:

1. [Access point compatibility — FSx for ONTAP User Guide](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)
2. [Query files with SQL using Amazon Athena — FSx for ONTAP User Guide](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-query-data-with-athena.html)
3. [Accessing your data via Amazon S3 access points — FSx for ONTAP User Guide](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)
4. [Amazon FSx for NetApp ONTAP now integrates with Amazon S3 for seamless data access — AWS News Blog](https://aws.amazon.com/blogs/aws/amazon-fsx-for-netapp-ontap-now-integrates-with-amazon-s3-for-seamless-data-access/)
5. [Enabling AI-powered analytics on enterprise file data: Configuring S3 Access Points for Amazon FSx for NetApp ONTAP with Active Directory — AWS Storage Blog](https://aws.amazon.com/blogs/storage/enabling-ai-powered-analytics-on-enterprise-file-data-configuring-s3-access-points-for-amazon-fsx-for-netapp-ontap-with-active-directory/)
6. [Troubleshooting S3 access point issues — FSx for ONTAP User Guide](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/troubleshooting-access-points-for-fsxn.html)
7. [Using access points — FSx for ONTAP User Guide](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-usage-examples.html)

---

## Appendix A: Our Workaround Architecture (For AWS Team Context)

Each of the 17 UCs in this project follows this pattern:

```
┌─────────────────────────────┐    ┌──────────────────────────────┐
│ EventBridge Scheduler       │───▶│ Discovery Lambda             │
│ (rate: 1 hour, workaround   │    │ - ListObjectsV2 on S3AP      │
│  for FR-2)                  │    │ - Diff with DynamoDB state   │
└─────────────────────────────┘    └──────┬───────────────────────┘
                                          │
                                          ▼
                                    ┌────────────────────────────┐
                                    │ Step Functions Map         │
                                    │ - Per-file processing      │
                                    │ - GetObject from S3AP  ✅  │
                                    │ - Rekognition/Textract/    │
                                    │   Comprehend/Bedrock       │
                                    │ - PutObject OUTPUT:        │
                                    │     • S3AP  (this FR)      │
                                    │     • Standard S3 (today)  │
                                    └──────┬─────────────────────┘
                                           │
                                           ▼
                                    ┌────────────────────────────┐
                                    │ Athena query Workgroup     │
                                    │ - OutputLocation:          │
                                    │   Standard S3 (FR-1)       │
                                    └────────────────────────────┘
```

The `PutObject OUTPUT` line with the two options is what our `OutputDestination` CloudFormation parameter (introduced 2026-05-10) now toggles — demonstrating that customers **can** use S3AP for outputs with the current API surface, but without FR-1/FR-2/FR-3, the pattern is incomplete.

---

## Appendix B: Japanese Summary (日本語サマリー)

### 要望の背景

FSx for NetApp ONTAP の S3 Access Points (S3AP) 連携により、NAS データに S3 API でアクセスでき、Athena / Bedrock / Rekognition 等から直接ファイルを読めるようになった。業界横断で 17 ユースケース（半導体 EDA、医療 DICOM、VFX、FOIA、衛星画像 等）の本番実装を行ったところ、以下 4 点の機能不足により、パイプラインの出力先に標準 S3 バケットを併用せざるを得ず、「データをコピーしない」というインテグレーションの価値が損なわれている。

### 改善要望

1. **FR-1**: Athena の Workgroup で Query Result Output Location に FSxN S3AP を指定できるようにする（現状は標準 S3 必須）
2. **FR-2**: S3AP で S3 Event Notifications / EventBridge イベントを発行できるようにする（現状は全 UC がポーリング実装）
3. **FR-3**: S3AP で Object Lifecycle Policy をサポートする（金融・医療・政府機関の保管義務対応に必須）
4. **FR-4**: S3AP で Object Versioning と Presigned URL をサポートする

優先順位: **FR-2 > FR-1 > FR-3 > FR-4**。FR-2 が最優先なのは全 UC に影響するため。

### 顧客の声

2026 Q1 に追加した UC15/16/17（Public Sector）では顧客から明示的に「ML パイプラインの出力が、なぜ FSx のソースデータと別の S3 バケットにあるのか」という質問を受けた。PoC では通常 2〜3 個の S3 バケットが必要になり、インテグレーションの "single copy" メッセージが弱まっている。

---

*Submission targets: AWS Support Case, aws/containers-roadmap GitHub equivalent for FSx (if available), AWS re:Post community feedback, direct outreach to FSx service team via NetApp alliance contact.*
