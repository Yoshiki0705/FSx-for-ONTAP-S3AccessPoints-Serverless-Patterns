# Feature Requests: File Portal UI — SaaS Gap Analysis & AWS Service Improvements

> 🌐 Language: **English** | [日本語](./file-portal-service-gap.md)

**Submitter**: Yoshiki Fujiwara (AWS Community Builder)
**Date**: 2026-07-18
**Project**: [fsxn-s3ap-serverless-patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns)
**Context**: File Portal UI built with Amplify Gen2 + FSx for ONTAP S3 Access Points
**Status**: Draft — preparing for submission

---

## Executive Summary

Fifteen services across enterprise file portals (Box, Google Drive, SharePoint, Egnyte, Citrix ShareFile), consumer/SMB (Dropbox, OneDrive, iCloud), OSS (Nextcloud, ownCloud, Seafile), security-focused (Tresorit), and cost-optimized (Wasabi) each provide file management experiences with their own strengths. In 2025-2026, AI agent capabilities such as Box Agent, SharePoint Copilot, Google Gemini, and Dropbox Dash have rapidly proliferated, shifting the value of file storage from "store and share" to "AI-powered utilization and automation."

Our File Portal UI (`solutions/amplify-portal/`) currently provides: file listing, folder navigation, file preview (Presigned URL), upload/download (Storage Browser), AI/ML job submission (Bedrock/Rekognition/Comprehend), natural language file operations (Quick MCP), real-time results, job history, FlexClone restore, and breadcrumb navigation. With Presigned URL verification and Storage Browser integration, the basic file management UX gap has narrowed significantly. Remaining gaps (version history, comments, sync client) can be supplemented by Nextcloud coexistence.

This document identifies the remaining gaps, maps them to AWS service limitations, and proposes feature requests that would enable AWS-native file portals to further close the gap — without requiring data movement from FSx for ONTAP.

---

## SaaS Feature Gap Analysis

### Methodology

Compared current Amplify Gen2 File Portal capabilities against 15 representative SaaS/OSS cloud storage services across 4 categories. Data sourced from official documentation, release announcements, and feature pages (2025-07 ~ 2026-07).

**Comparison targets**:

| Category | Service | Key differentiator |
|----------|---------|-------------------|
| Enterprise | Box Enterprise Advanced | AI Agent (GA Apr 2026), governance, retention, AI Studio |
| Enterprise | SharePoint Online (M365) | Copilot (Jul 2026), document library AI, Power Automate |
| Enterprise | Google Drive (Workspace) | Gemini integration (2026), AI file organization, real-time co-editing |
| Enterprise | Citrix ShareFile | StorageZones (hybrid), e-signatures, VDR, granular access |
| Enterprise | Egnyte | Hybrid sync (cloud + on-prem), AI metadata tagging, DLP, ransomware protection |
| Consumer/SMB | Dropbox Business | Dash AI universal search (2025), multimodal search, OpenAI integration |
| Consumer/SMB | OneDrive (M365) | Files On-Demand, Windows/macOS integration, Copilot |
| Consumer/SMB | iCloud Drive | Apple ecosystem, Pages/Numbers/Keynote collaboration |
| Security-focused | Tresorit | E2E zero-knowledge encryption, Swiss privacy law, Engage platform |
| Cost-optimized | Wasabi | S3 100% bit-compatible, $6.99/TB/month, no egress fees |
| OSS Self-hosted | Nextcloud | AGPL-3.0, Hub 26 (Governance tool, Euro-Office), federation |
| OSS Self-hosted | ownCloud Infinite Scale | Go microservices, Spaces, multi-storage, federation (Kiteworks) |
| OSS Self-hosted | Seafile | Block-level delta sync, Git-like data model, AI property automation |
| AWS Native | Storage Browser for S3 | React component (Amplify UI), S3 AP on roadmap |
| AWS Native | Transfer Family | SFTP/FTPS, FSx for ONTAP S3 AP support (2026/1 GA) |

**Excluded**: NAS vendor-provided solutions (Synology Drive, QNAP, TrueNAS, etc.). Direct comparison between NAS vendors in an article about FSx for ONTAP would appear as position-taking.


### Gap Matrix — Basic File Management

Enterprise SaaS (Box / SharePoint / Google Drive / Citrix ShareFile / Egnyte) all satisfy the following, so they are grouped as "Enterprise SaaS" in this table. Consumer/SMB (Dropbox / OneDrive / iCloud) also cover basic features similarly.

| Feature | Enterprise SaaS | Consumer/SMB | OSS Self-hosted | Our Portal | Gap Severity |
|---------|:---:|:---:|:---:|:---:|:---:|
| File listing & folder navigation | ✅ | ✅ | ✅ | ✅ | — |
| File preview (images/PDF/video/Office) | ✅ | ✅ | ✅ | ✅ (Presigned URL) | — (resolved) |
| File download | ✅ | ✅ | ✅ | ✅ (Presigned URL) | — (resolved) |
| File upload (drag & drop) | ✅ | ✅ | ✅ | ✅ (Storage Browser) | — (resolved) |
| Sharing links (time-limited, password) | ✅ | ✅ | ✅ | ✅ (Presigned URL) | — (resolved) |
| Version history | ✅ | ✅ | ✅ (Nextcloud/ownCloud) | ❌ | Medium |
| Comments / annotations | ✅ | △ (limited) | ✅ (Nextcloud) | ❌ | Low |
| Full-text search | ✅ | ✅ | ✅ (Nextcloud/Seafile) | ❌ | Medium |
| Retention policies (compliance) | ✅ | △ (Vault only) | ✅ (Nextcloud Governance) | ❌ | Medium |
| Desktop sync client | ✅ | ✅ | ✅ | ❌ | Low |
| Collaborative real-time editing | ✅ | ✅ | ✅ (Nextcloud Office) | ❌ | Low |
| Audit trail (who accessed what) | ✅ | ✅ | ✅ | △ (CloudTrail raw) | Medium |
| Mobile responsive UI | ✅ | ✅ | ✅ | △ | Low |

### Gap Matrix — AI / Intelligence Features (2025-2026 New Wave)

Comparison with AI features that SaaS vendors have rapidly shipped in 2025-2026. File storage value is shifting from "storage" to "utilization."

| AI/Intelligence Feature | Box | SharePoint | Google Drive | Dropbox | Egnyte | Our Portal |
|-------------------------|:---:|:---:|:---:|:---:|:---:|:---:|
| AI agent (cross-file tasks via NL) | ✅ Box Agent | ✅ Copilot | ✅ Gemini | ✅ Dash | ❌ | ✅ Quick MCP |
| AI document summarization / Q&A | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ Bedrock |
| AI auto-classification / metadata | ✅ AI Studio | ✅ Copilot | ✅ Gemini | △ | ✅ | ✅ Comprehend |
| AI workflow automation | ✅ | ✅ Power Automate | ✅ AppSheet | △ | ❌ | ✅ Step Functions |
| Image/video AI analysis | △ | △ | ✅ | ✅ Multimodal | ❌ | ✅ Rekognition |
| RAG / Knowledge Base integration | ✅ | ✅ | ✅ NotebookLM | ❌ | ❌ | ✅ Bedrock KB |
| Data classification / DLP | ✅ Shield | ✅ Purview | ✅ DLP | ❌ | ✅ | ✅ (labels) |
| E2E encryption (zero-knowledge) | ✅ KeySafe | ❌ | ✅ CSE | ❌ | ❌ | ❌ |


### Gap Matrix — Security & Governance

| Security/Governance Feature | Tresorit | Box | Egnyte | Nextcloud | Our Portal |
|-----------------------------|:---:|:---:|:---:|:---:|:---:|
| E2E zero-knowledge encryption | ✅ | △ KeySafe (BYOK) | ❌ | ✅ (plugin) | ❌ |
| Data residency control | ✅ (Swiss) | ✅ Zones | ✅ | ✅ (self-host) | ✅ (region selection) |
| Ransomware protection | △ | ✅ | ✅ | ✅ (plugin) | ✅ (ARP/AI + FlexClone/Snapshot) |
| Legal hold | ❌ | ✅ | ✅ | ✅ Governance | ❌ |
| eDiscovery | ❌ | ✅ | △ | ❌ | ❌ |
| FedRAMP / ISMAP certification | ❌ | ✅ | ❌ | ❌ | ✅ (AWS infrastructure) |

### Gap Matrix — Hybrid & Connectivity

| Hybrid/Connectivity | Egnyte | Citrix ShareFile | Nextcloud | ownCloud OCIS | Our Portal |
|---------------------|:---:|:---:|:---:|:---:|:---:|
| On-premises sync (NAS/SAN) | ✅ Storage Sync | ✅ StorageZones | ✅ External Storage | ✅ multi-storage | ✅ (SnapMirror + S3 AP) |
| S3-compatible storage connection | ❌ | ❌ | ✅ | ✅ | ✅ (native) |
| SFTP/FTPS endpoint | ❌ | ❌ | ❌ | ❌ | ✅ (Transfer Family) |
| Multi-protocol simultaneous access (NFS/SMB/S3) | ❌ | ❌ | △ (External) | ❌ | ✅ |
| FlexClone instant restore | ❌ | ❌ | ❌ | ❌ | ✅ |
| Federation (server-to-server) | ❌ | ❌ | ✅ | ✅ | ❌ |

### Protocol Accessibility in Detail — Why Multi-Protocol Matters

Simply stating "supports NFS/SMB/S3" is insufficient. In practice, protocol selection directly impacts performance, connectivity, and workflow compatibility. This section provides an overview of why each protocol addresses distinct requirements.

| Protocol | Primary use case | Performance characteristics | Connectivity requirements |
|----------|-----------------|---------------------------|--------------------------|
| **NFSv3** | Linux/UNIX workloads (EDA, HPC, AI training data) | Low latency, high throughput. Stateless design enables fast failover | VPC-internal or Direct Connect/VPN. Stateless nature is stable across NAT |
| **NFSv4.1** | Linux workloads requiring session management | Throughput comparable to NFSv3 + delegation (client cache offloading) reduces metadata load | VPC-internal. Single port (TCP 2049) simplifies firewall rules |
| **SMB 3.x** | Windows workstations (CAD, Office, DTP) | Multichannel aggregates bandwidth. Encryption (AES-128-GCM) adds some overhead | AD environment (Kerberos auth) required. VPC-internal or Direct Connect |
| **S3 API** (S3 AP) | Serverless processing pipelines (Lambda, Step Functions, Bedrock, Athena) | Per-request billing. 5GB/object limit. Parallelism scales without bound | Internet-origin AP: direct access from outside VPC. VPC-origin AP: via VPC Endpoint |
| **SFTP/FTPS** | B2B file exchange, legacy system integration | Via Transfer Family. Throughput depends on instance type | Public or VPC endpoint (Transfer Family) |

#### Why simultaneous access matters — Workload perspectives

> **Semiconductor EDA workloads**: Simulation jobs are submitted via NFSv3 (low latency, high throughput). Result logs are analyzed by AI via S3 AP (Lambda/Bedrock). Without simultaneous multi-protocol access to the same files, data copying would double storage cost and pipeline latency.

> **Manufacturing CAD workflows**: CAD workstations access shared folders via SMB 3.x (AD auth + file locking). Factory tablets browse drawings via S3 AP web portal (Presigned URL). Batch rendering servers read/write intermediate files via NFSv3. All three protocols must coexist on the same volume.

> **ML training pipelines**: Training data is read at high speed from GPU instances via NFSv3 mount. After training, model artifacts are registered to Bedrock Knowledge Base via S3 AP. Business analysts review reports via SMB. The structure where no data movement is required between protocols directly impacts iteration velocity.

> **Operational design considerations**: NFSv3 is stateless, so failover requires no session re-establishment (benefits availability). NFSv4.1 delegation reduces metadata load (effective for many-small-file access patterns). S3 API scales per-request to handle burst AI processing. Understanding each protocol's operational characteristics enables right-tool-for-the-job selection.

> **Audit and compliance considerations**: SMB access is governed by AD + NTFS ACLs. NFSv4.1 access is governed by Kerberos + UNIX permissions. S3 AP access is governed by IAM + File System Identity. Despite different protocols, consistent access control applies to the same file (via ONTAP's multi-protocol identity mapping). From an audit perspective, all protocol accesses are trackable across CloudTrail + ONTAP Audit Log.

> **Network design considerations**: NFSv4.1 operates on a single port (TCP 2049), simplifying firewall configuration. NFSv3 requires portmapper + dynamic ports, making security group setup more complex. S3 AP (Internet-origin) uses only HTTPS/443 and is accessible from outside the VPC, providing network design flexibility. The ability to choose protocol and network path per workload enables integration of diverse workloads on shared data.

#### Performance design considerations

All protocols (NFS/SMB/S3 AP) share the same FSx for ONTAP throughput budget. Key design points:

- **Throughput sharing**: On a 128 MBps file system, if NFS workloads consume 100 MBps, only 28 MBps remains for S3 AP portal access
- **Mitigation 1 — FlexCache**: Offload read-heavy protocols (e.g., S3 AP portal reads) to FlexCache, preserving write bandwidth on the source volume
- **Mitigation 2 — Throughput capacity scaling**: Consider increasing throughput capacity when CloudWatch `ThroughputUtilization` exceeds 80%
- **Mitigation 3 — Workload isolation**: Separate write-intensive (NFS/SMB) and read-intensive (S3 AP portal) onto different volumes to make I/O patterns predictable
- **Monitoring**: Track `ThroughputUtilization`, `DataReadBytes`, `DataWriteBytes` per protocol in CloudWatch. Baseline comparison before/after portal addition is recommended

#### Data consistency model and cross-protocol coherence

The most critical technical aspect of multi-protocol access is data consistency across protocols:

- **Write-immediate visibility**: A file written via NFSv3 is immediately visible in S3 AP's `ListObjectsV2` and SMB directory listings (standard S3 provides strong consistency within S3 operations since December 2020, but cross-protocol consistency between NFS/SMB/S3 API is a characteristic specific to FSx for ONTAP)
- **File lock coexistence**: SMB Opportunistic Locks (oplocks) and NFSv4.1 Delegations coexist on the same volume. However, concurrent writes to the same file from different protocols will break oplocks/delegations, temporarily reducing performance
- **S3 AP reads and locking**: S3 AP's GetObject does not acquire file locks (read-only snapshot read). Reading a file via S3 AP while it's being written via NFS/SMB may expose an in-progress state. Processing pipelines should confirm write completion before S3 AP reads

> **DR/Backup (DR Specialist)**: FlexClone snapshots present data from a single point in time, accessible via all protocols. The consistency model — where no cross-protocol data discrepancies can occur — directly impacts point-in-time recovery reliability.

#### Multi-protocol identity mapping and access control

Authentication mechanisms differ per protocol, but ONTAP's multi-protocol identity mapping provides consistent access control to the same file:

| Protocol | Authentication mechanism | Identity mapping direction |
|----------|------------------------|---------------------------|
| NFSv3 | AUTH_SYS (UID/GID) | — (direct UNIX permission evaluation) |
| NFSv4.1 | Kerberos (RPCSEC_GSS) | Kerberos principal → UNIX UID |
| SMB 3.x | Kerberos (AD) | Windows SID → UNIX UID (name-mapping) |
| S3 API (S3 AP) | IAM (SigV4) | File System Identity → UNIX UID or Windows SID |

> **Security Auditor**: Regardless of access protocol, files are ultimately evaluated against the same UNIX permissions or NTFS ACLs. A state where "accessible via NFS but not via S3 AP" is intentionally controllable through the File System Identity's UID/GID configuration. This can be leveraged for file-level zero-trust design.

### Gap Matrix — Cost Structure

| Cost Model | Wasabi | Dropbox | Box | Google | Nextcloud | Our Portal |
|------------|:---:|:---:|:---:|:---:|:---:|:---:|
| Storage cost (1TB/month) | ~$7 | ~$150 | ~$200+ | ~$144 | $0 (self-host) | ~$21 (Capacity Pool) |
| Egress charges | None | None | None | None | None | Yes (AWS standard) |
| Per-user pricing model | ❌ (TB-based) | ✅ | ✅ | ✅ | ❌ | ❌ |
| Free Tier / OSS available | ❌ | △ (2GB) | △ (15GB) | ✅ (15GB) | ✅ (AGPL) | ✅ (DemoMode) |

> **Cost note**: The above are approximate public price ranges. Actual costs vary significantly by usage volume and contract terms.

### Key Insights (Expanded)

1. **The AI agent wave**: Box Agent, SharePoint Copilot, Google Gemini in Drive, and Dropbox Dash went GA in rapid succession during 2025-2026. File storage value is shifting from "store and share" to "AI-powered utilization and automation." Our portal's Bedrock / Rekognition / Quick MCP integration aligns with this direction.

2. **Structural differences in hybrid connectivity**: Egnyte's Storage Sync and Citrix's StorageZones cover on-premises connectivity, but simultaneous NFS/SMB/S3 multi-protocol access with strong consistency is a structural characteristic of FSx for ONTAP S3 AP. Other approaches may encounter sync delays or cross-protocol inconsistencies as a trade-off.

3. **Rapid OSS evolution**: Nextcloud Hub 26 added a Governance tool, and ownCloud OCIS strengthened federation. Enterprise features are increasingly covered by OSS. The coexistence pattern with Nextcloud remains effective.

4. **Security-focused options**: Tresorit's zero-knowledge encryption has strong demand in strictly regulated industries (legal, healthcare, finance). Our portal covers similar needs with AWS KMS + CloudTrail, but E2E zero-knowledge is a structurally different approach.

5. **Basic file management UX gap is narrowing**: With Presigned URL verification and Storage Browser for S3 integration, file preview, download, upload, and sharing links are implemented. Remaining gaps are version history, comments, desktop sync, and real-time collaborative editing — all supplementable via Nextcloud coexistence.

6. **Symmetry of trade-offs**: Every approach has constraints.
   - SaaS: Vendor lock-in, data movement required, limited flexibility for custom processing pipelines
   - OSS Self-hosted: Operational burden, scalability is self-managed, no support SLA (Community Edition)
   - Our portal: Version history/comments/sync client not yet implemented, requires Nextcloud coexistence for supplementation
   - Wasabi: No file management UI (storage API only), no AI features


---

## Root Cause Analysis: Why Gaps Exist

| Gap | Root cause (AWS service limitation) |
|-----|--------------------------------------|
| No real file preview | FSx for ONTAP S3 AP does not support Presigned URLs (FR-4, previously submitted) |
| No file download | Same — Presigned URL needed for browser-initiated download |
| No sharing links | Same — time-limited Presigned URLs are the standard mechanism |
| No file upload | S3 AP PutObject works, but Amplify Storage component only supports standard S3 buckets |
| No full-text search | No native search/indexing service for S3 AP content; OpenSearch requires data copy |
| No version history | S3 AP does not support Object Versioning |
| No audit trail UI | CloudTrail logs S3 AP data events, but no managed UI component to surface them |
| No retention policies | S3 AP does not support Lifecycle Configuration |

**Conclusion**: 5 of 8 high/medium gaps trace back to the Presigned URL limitation (FR-4) or the lack of Amplify/Storage Browser support for S3 Access Points.

---

## Feature Requests

### FR-5: Storage Browser for S3 — Official Support for FSx for ONTAP S3 Access Points

**Service**: Amazon S3 / Amplify UI

**Current state**: [Storage Browser for S3](https://ui.docs.amplify.aws/react/connected-components/storage/storage-browser) (GA December 2024) provides browse, download, upload, copy, delete, and file preview for S3 data. Its public roadmap explicitly lists **"Support for S3 Access Points"** as a feature under evaluation.

**How it works**: Storage Browser is a React component that calls S3 API (`ListObjectsV2`, `GetObject`, `PutObject`, `DeleteObject`) client-side. FSx for ONTAP S3 AP supports all these operations, and the S3 AP alias (`xxx-s3alias`) can be passed to the SDK as a bucket name. Following the same logic as Presigned URLs (verified working), the client simply uses the S3 AP alias as the bucket name.

**Request**: Officially support S3 AP alias in Storage Browser's `createManagedAuthAdapter` and document FSx for ONTAP S3 AP usage examples.

**Impact**: Official support would immediately enable: file preview (images, video, text), file download, file upload (5GB limit per FSx for ONTAP S3 AP constraint), copy and delete operations, folder creation. This single FR would close 4 of the 8 gaps.

---

### FR-6: Amplify Storage Category — Support S3 Access Points as Backend

**Service**: AWS Amplify Gen2

**Current state**: Amplify Storage (`defineStorage` in `amplify/storage/resource.ts`) only supports standard S3 buckets. No mechanism exists to specify an S3 Access Point.

**Requested behavior**: Allow `defineStorage` or a new `defineStorageAccessPoint` to accept AP alias or ARN.

**Impact**: Developers could use `Amplify.Storage.list()`, `.get()`, `.put()` against FSx for ONTAP data without custom Lambda proxies.

**Workaround**: Custom AppSync resolvers + Lambda functions that call S3 API with the AP alias. All file operations go through Lambda, adding latency and cost.

---

### ~~FR-7: FSx for ONTAP S3 AP — Presigned URL Support~~ (verified working — changed to documentation correction request)

**Service**: Amazon FSx for ONTAP

**Current state**: Presigned URLs are listed as "Not supported" in the FSx for ONTAP S3 AP compatibility table. **However, they actually work.** Verified in this project and other environments. AWS Support confirmed:

1. Presigning is a client-side operation — no network request is made
2. The resulting URL executes as a standard GetObject
3. Since GetObject is supported, blocking Presigned URLs is structurally impossible
4. The "Not supported" documentation reflects that AWS has not officially tested the workflow

**Changed to**: Documentation correction request only — update the compatibility table to reflect actual behavior.

**Production Guidance**: AWS Support states relying on operations classified as "Not supported" in production is not recommended. Working behavior is confirmed, but cross-region consistency and post-update guarantees are not provided. Recommend having a Lambda proxy fallback path for production use.

---

### FR-8: FSx for ONTAP S3 AP — CloudTrail Data Event Integration with Managed Audit UI

**Service**: Amazon FSx for ONTAP / AWS CloudTrail

**Current state**: CloudTrail can log S3 data events for S3 Access Points. However, there is no managed UI component that surfaces "who accessed which file, when" in a user-friendly format for compliance officers.

**Requested behavior**: Confirm/document CloudTrail data event logging for FSx for ONTAP S3 AP operations, provide Security Hub or Audit Manager integration for file-level access tracking.

**Impact**: Regulated industries (healthcare, finance, government) require demonstrable audit trails for file access.

---

### ~~FR-9~~: Amazon Quick + FSx for ONTAP S3 AP (✅ Verified — AWS official blog + Workshop)

**Status**: **Resolved (implementation issue, not service limitation)**

Amazon Quick Suite works with FSx for ONTAP S3 AP when configured with AD-based Windows identity (not UNIX root identity). Documented in [AWS Storage Blog](https://aws.amazon.com/blogs/storage/enabling-ai-powered-analytics-on-enterprise-file-data-configuring-s3-access-points-for-amazon-fsx-for-netapp-ontap-with-active-directory/) and [AWS Workshop](https://catalog.us-east-1.prod.workshops.aws/workshops/9cd82e0b-8348-456b-932a-818b9e5825a1/en-US/08-quicksuite/61-setup).

---

### ~~FR-10: AWS Transfer Family~~ (✅ Resolved — 2026/1 release)

**Status**: **Resolved**

AWS Transfer Family supported FSx for ONTAP S3 Access Points as of January 2026. [What's New](https://aws.amazon.com/about-aws/whats-new/2026/01/aws-transfer-family-amazon-fsx-netapp-ontap), [Docs](https://docs.aws.amazon.com/transfer/latest/userguide/fsx-s3-access-points.html), [Blog](https://aws.amazon.com/blogs/storage/secure-sftp-file-sharing-with-aws-transfer-family-amazon-fsx-for-netapp-ontap-and-s3-access-points/).


---

## Priority Ranking (Final)

| FR | Status | Next Action |
|-----|--------|-------------|
| ~~FR-5~~ (Storage Browser + S3 AP) | Needs verification (works client-side in principle) | Verify with `createManagedAuthAdapter` + S3 AP alias |
| **FR-6** (Amplify Storage + S3 AP) | **Open** | GitHub Issue on amplify-backend |
| ~~FR-7~~ (Presigned URL) | ✅ Verified working | Documentation correction request only |
| **FR-8** (Audit UI) | **Open** | CloudTrail data events visualization component request |
| ~~FR-9~~ (Amazon Quick + S3 AP) | ✅ Verified (AWS blog + Workshop) | Re-verify with AD identity in own environment |
| ~~FR-10~~ (Transfer Family) | ✅ Resolved 2026/1 | — |

**Conclusion**: Only **FR-6 (Amplify Storage category)** and **FR-8 (Audit UI)** are truly "not working." All others are verified or have client-side configurations that work.

**Positive signal**: Storage Browser for S3's official roadmap lists "Support for S3 Access Points" ([Amplify UI Storage Browser docs](https://ui.docs.amplify.aws/react/connected-components/storage/storage-browser)).

---

## What We Can Build Today (Without These FRs)

Despite the gaps, our portal provides capabilities that SaaS products cannot:

| Capability | How it works |
|---|---|
| AI/ML processing pipeline | Step Functions + Bedrock/Textract/Comprehend triggered from UI |
| FlexClone snapshot restore | ONTAP REST API creates point-in-time clone in seconds |
| Multi-protocol data access | Same file accessible via NFS (Linux), SMB (Windows), S3 API (cloud) |
| SFTP/FTPS file exchange | Transfer Family → FSx for ONTAP S3 AP (GA 2026/1) |
| RAG / AI Q&A over NAS data | Bedrock Knowledge Base → FSx for ONTAP S3 AP (direct data source) |
| Data classification labels | Automated INTERNAL/CUI/PUBLIC tagging on processing results |
| Job execution history | DynamoDB-backed, owner-scoped, with status tracking |
| Event-driven + polling hybrid | TriggerMode parameter per use case |

These capabilities are not available in SaaS file management products, which makes a custom portal worth building even with the current limitations in basic file management UX.

---

## Already Resolved (since original FR submission)

| Capability | Resolution | Source |
|---|---|---|
| SFTP/FTPS access to FSx for ONTAP | ✅ Transfer Family + S3 AP (2026/1 GA) | [docs](https://docs.aws.amazon.com/transfer/latest/userguide/fsx-s3-access-points.html) |
| RAG over NAS data | ✅ Bedrock Knowledge Base + S3 AP | [FSx User Guide tutorial](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-build-rag-with-bedrock.html) |
| Enterprise search / AI Q&A | ✅ Amazon Quick + S3 AP (AD identity required) | [AWS Storage Blog](https://aws.amazon.com/blogs/storage/enabling-ai-powered-analytics-on-enterprise-file-data-configuring-s3-access-points-for-amazon-fsx-for-netapp-ontap-with-active-directory/) |
| Video streaming from NAS | ✅ CloudFront + S3 AP | [FSx User Guide](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-access-points-with-aws-services.html) |
| Presigned URL for file preview/download | ✅ Verified (client-side SigV4) | [Project verification record](../repost-draft-presigned-url-compatibility.md) |

---

## References

1. [Storage Browser for S3 — Amplify UI](https://ui.docs.amplify.aws/react/connected-components/storage/storage-browser)
2. [Storage Browser for S3 is now GA — AWS News (2024/12)](https://aws.amazon.com/about-aws/whats-new/2024/12/storage-browser-amazon-s3)
3. [Use Amplify Storage with custom S3 — Amplify Docs](https://docs.amplify.aws/android/build-a-backend/storage/use-with-custom-s3/)
4. [Access point compatibility — FSx for ONTAP User Guide](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)
5. [AWS Transfer Family + FSx for ONTAP — AWS News (2026/1)](https://aws.amazon.com/about-aws/whats-new/2026/01/aws-transfer-family-amazon-fsx-netapp-ontap)
6. [Transfer Family User Guide — FSx for ONTAP S3 AP](https://docs.aws.amazon.com/transfer/latest/userguide/fsx-s3-access-points.html)
7. [Secure SFTP file sharing — AWS Storage Blog (2026/3)](https://aws.amazon.com/blogs/storage/secure-sftp-file-sharing-with-aws-transfer-family-amazon-fsx-for-netapp-ontap-and-s3-access-points/)
8. [Build RAG with Bedrock KB + FSx for ONTAP — User Guide](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-build-rag-with-bedrock.html)
9. [Amazon Kendra Maintenance Mode (2026/6/30)](https://docs.aws.amazon.com/kendra/latest/dg/kendra-availability-change.html)
10. [Amazon Q Business availability change (2026/7/31)](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/qbusiness-availability-change.html)
11. [Amazon Quick — Enterprise AI Productivity Assistant](https://aws.amazon.com/quick/enterprise/)
12. [ONTAP 9.11+ Presigned URL support — NetApp KB](https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Software/ONTAP_OS/What_version_of_ONTAP_support_pre-signed_URLs_for_S3_bucket)
13. [Box Retention Policies — Box Support](https://support.box.com/hc/en-us/articles/360043694374-About-Retention-and-Retention-Policies)
14. [Enterprise file sharing features (2025) — Moxo](https://www.moxo.com/blog/client-file-sharing-portal)
15. [Enterprise file sharing solution guide (2026) — fast.io](https://about.fast.io/resources/enterprise-file-sharing-solution/)

---

*Content was rephrased for compliance with licensing restrictions. All feature descriptions are based on publicly available documentation.*
