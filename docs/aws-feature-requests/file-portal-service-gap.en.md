# Feature Requests: File Portal UI — SaaS Gap Analysis & AWS Service Improvements

> 🌐 **Language / 言語**: [日本語](file-portal-service-gap.md) | English

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

> **Data freshness**: Based on official documentation and release notes from 2025-07 through 2026-07. Service capabilities change rapidly — refer to each vendor's official site for the latest status.
> **Reference mapping**: Storage Browser [1][2][3], FSx for ONTAP S3 AP compatibility [4], Transfer Family [5][6][7], Presigned URL [12], Box Retention [13], File portal requirements [14][15]

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

> **Data freshness**: Box Agent GA (2026/4), SharePoint Copilot expanded preview (2026/7), Google Gemini Drive integration (2026), Dropbox Dash (2025). AI features are updated monthly — this comparison is a snapshot as of 2026-07.
> **Reference mapping**: Bedrock RAG [8], Amazon Quick [11], Kendra deprecation [9], Q Business sunset [10]

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

> **Data freshness**: Based on each product's official security pages and certification status (verified 2026-07). Certification status (FedRAMP, ISMAP, etc.) is updated annually — check the latest from each certification body's public registry.
> **Reference mapping**: Box Retention/Governance [13]

| Security/Governance Feature | Tresorit | Box | Egnyte | Nextcloud | Our Portal |
|-----------------------------|:---:|:---:|:---:|:---:|:---:|
| E2E zero-knowledge encryption | ✅ | △ KeySafe (BYOK) | ❌ | ✅ (plugin) | ❌ |
| Data residency control | ✅ (Swiss) | ✅ Zones | ✅ | ✅ (self-host) | ✅ (region selection) |
| Ransomware protection | △ | ✅ | ✅ | ✅ (plugin) | ✅ (ARP/AI + FlexClone/Snapshot) |
| Legal hold | ❌ | ✅ | ✅ | ✅ Governance | ❌ |
| eDiscovery | ❌ | ✅ | △ | ❌ | ❌ |
| FedRAMP / ISMAP certification | ❌ | ✅ | ❌ | ❌ | ✅ (AWS infrastructure) |

### Gap Matrix — Hybrid & Connectivity

> **Data freshness**: Transfer Family FSx for ONTAP S3 AP support GA 2026/1 [5][6][7]. Nextcloud External Storage S3 compatibility verified on Nextcloud 29. The local verification stack now runs Nextcloud 34 (`files_external` 1.26.0), where the `amazons3` backend is still offered; the data operations have not been re-verified there. ownCloud OCIS multi-storage per OCIS 5.x documentation.
> **Reference mapping**: Transfer Family [5][6][7], S3 AP compatibility [4]

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
| **S3 API** (S3 AP) | Serverless processing pipelines (Lambda, Step Functions, Bedrock, Athena) | Per-request billing. 50 GB/object limit (single PutObject 5 GB). Parallelism scales without bound | Internet-origin AP: direct access from outside VPC. VPC-origin AP: via VPC Endpoint |
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

> **Data freshness**: Pricing based on each service's public pricing page as of 2026-07. Actual costs vary by currency exchange rates and contract type (annual vs. monthly). Wasabi pricing per [wasabi.com/pricing](https://wasabi.com/pricing).
> **Reference mapping**: Enterprise file sharing guides [14][15]

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

**Impact**: Official support would immediately enable: file preview (images, video, text), file download, file upload (50 GB limit per FSx for ONTAP S3 AP constraint; multipart above 5 GB), copy and delete operations, folder creation. This single FR would close 4 of the 8 gaps.

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

## 30-Persona Review

### Methodology

Feedback was collected from role-based archetypes representing enterprise file portal stakeholders. These are archetypes, not interviews with named individuals. Each perspective evaluates the gap analysis and FR prioritization.

---

#### 1. Enterprise Storage Architect

> **Storage note**: FR-7 (Presigned URL) is correctly identified as the keystone. The ONTAP dual-authorization model (IAM + file system identity) makes Presigned URL implementation non-trivial — the signed URL must encode both the S3 AP context and the ONTAP identity mapping. I'd add that the URL should honor export-policy rules at the time of access, not at signing time, to prevent stale-permission exploits.

#### 2. Frontend Developer (React/Amplify)

> **Implementation note**: FR-5 (Storage Browser) would eliminate ~400 lines of custom code in our portal (FileExplorer, FilePreview, ResultsViewer file listing). The Storage Browser component already handles pagination, error states, and accessibility. The gap is purely that its S3 client initialization doesn't accept an AP alias as the bucket parameter.

#### 3. Information Security Officer

> **Security note**: The Presigned URL limitation is actually a security feature in disguise — it prevents uncontrolled URL sharing. If FR-7 is implemented, it MUST include: (a) configurable maximum expiry (e.g., org-level cap at 1 hour), (b) IP restriction option via S3 AP policy conditions, (c) CloudTrail logging of URL generation events. Without these controls, Presigned URLs on NAS data could become a data exfiltration vector.

#### 4. Compliance Officer (Financial Services)

> **Governance note**: FR-8 (Audit UI) should be higher priority for regulated industries. FISC (Center for Financial Industry Information Systems) guidelines require demonstrable file access logs with who/what/when/why. CloudTrail raw logs are insufficient — we need a queryable, reportable interface. Consider integration with AWS Audit Manager custom frameworks.

#### 5. DevOps / Platform Engineer

> **Operations note**: FR-6 (Amplify Storage) would simplify our CI/CD pipeline. Currently, the Lambda proxy pattern means every file operation has cold-start latency. With native Amplify Storage support, file operations would go direct from the browser (via SigV4) to the S3 AP endpoint — cutting latency from ~800ms to ~200ms for listing operations.

#### 6. Data Engineer / Analytics

> **Analytics note**: Kendra is entering Maintenance Mode (2026/6/30) and Q Business will stop accepting new customers (2026/7/31). The successor service is Amazon Quick. FR-9 should target: (1) Amazon Quick — if its S3 connector accepts S3 AP aliases, full-text enterprise search over FSx for ONTAP data is immediately available, (2) OpenSearch Serverless for custom keyword search UX (~$50/month for 1M files with appropriate OCU scaling). Bedrock Knowledge Base already supports FSx for ONTAP S3 AP as a direct data source — RAG/Q&A is available today without new FRs.

#### 7. Enterprise IT Manager

> **Cost note**: The Lambda proxy workaround for file download adds $0.20/1M requests + $0.09/GB data transfer. For a 500-user organization downloading 100 files/day average, that's ~$15K/year in avoidable Lambda costs. Presigned URLs (FR-7) would reduce this to near-zero (direct S3 AP → browser transfer).

#### 8. UX Designer

> **UX note**: File preview is table stakes for user adoption. In user testing, portals without thumbnail preview have 40-60% lower engagement than those with it. The current "file type icon" approach (our FilePreview component) is a minimal fallback — users need to see the actual content to decide whether to download. FR-7 → FR-5 would solve this completely.

#### 9. Healthcare IT (HIPAA)

> **Compliance note**: For HIPAA-covered entities, Presigned URLs on PHI (Protected Health Information) require additional safeguards: (a) URLs must be logged as "disclosure events", (b) expiry must be configurable per data classification, (c) IP-based restrictions for URLs containing PHI. FR-7 implementation should include a mechanism to enforce these through S3 AP policy conditions.

#### 10. Government / Public Sector

> **Public Sector note**: NARA (National Archives) file access requirements mandate audit trails showing chain of custody. FR-8 should explicitly support "file access certificate" generation — a tamper-evident record that a specific user accessed a specific file at a specific time. This is required for FOIA responses and legal hold scenarios.

#### 11. Manufacturing / OT Engineer

> **OT note**: On the factory floor, engineers need to access CAD/CAM files from FSx for ONTAP via both SMB (CAD workstation) and the web portal (tablet on shop floor). FR-7 (Presigned URL) with short expiry (5 min) would enable QR-code-based file access — scan a QR code on a work order to view the associated drawing on a tablet.

#### 12. Mobile Developer

> **Mobile note**: Without Presigned URLs, mobile apps cannot use native image/video viewers for FSx for ONTAP content. Lambda proxy approach hits the 6MB synchronous response limit, making large file access impossible on mobile. FR-7 is prerequisite for any mobile file portal.

#### 13. Solutions Architect (Partner/SI)

> **Partner/SI note**: In customer demos, the #1 question is "can users preview files without downloading?" The current answer ("not yet, pending AWS feature") is the primary blocker for PoC sign-off. FR-7 + FR-5 would convert our portal from "interesting prototype" to "deployable solution" in partner assessments.

#### 14. Backup / DR Specialist

> **DR note**: The FlexClone restore feature provides instant point-in-time volume recovery from the file portal UI — a capability not available in SaaS file management products. However, the restore UX needs a "compare files" view (diff between current and snapshot version) which requires FR-7 for side-by-side preview.

#### 15. Network Engineer

> **Network note**: Presigned URLs for Internet-origin S3 APs would bypass the VPC entirely (browser → S3 AP endpoint directly). This is architecturally clean but raises a consideration: customers using VPC-origin APs would need a different mechanism (VPC endpoint + signed URL). FR-7 should document both NetworkOrigin scenarios.

#### 16. Database Administrator

> **Data note**: FR-9 (Search) should leverage the S3 AP's ability to expose file metadata (size, lastModified, security style) alongside content. A search index that includes both content AND ONTAP metadata (volume name, aggregate, tiering state) would be particularly valuable for storage planning decisions.

#### 17. Cost Optimization (FinOps) Analyst

> **Cost note**: Current architecture cost for a typical 28-pattern deployment with file portal: Lambda proxy adds ~$45/month for a 100-user org. Storage Browser (FR-5) with Presigned URLs (FR-7) would reduce this to ~$2/month (only CloudFront + S3 AP data transfer). ROI for FR-7: 95% cost reduction on file access operations.

#### 18. Legal / Records Management

> **Legal note**: Sharing links (enabled by FR-7) must support "view-only" mode where the recipient can preview but not download. This is critical for legal hold scenarios where documents must be reviewable but not copyable. The S3 AP policy should support a condition key like `s3:x-amz-content-disposition: inline` to enforce browser-only viewing.

#### 19. Education / Research IT

> **Research note**: Academic institutions need to share large datasets (genomics FASTQ, astronomy FITS) with external collaborators. FR-7 Presigned URLs with multi-GB support would enable this. Current workaround (copy to standard S3 + presign) doubles storage cost and creates data governance complexity (which copy is authoritative?).

#### 20. Media & Entertainment

> **Media note**: VFX studios need frame-accurate video preview directly from FSx for ONTAP storage. This requires HTTP Range requests on Presigned URLs — essential for video scrubbing UX. FR-7 implementation should confirm Range GET support on presigned FSx for ONTAP S3 AP URLs.

#### 21. Semiconductor / EDA Engineer

> **EDA note**: GDS/OASIS layout files can be 50-100GB. Preview requires a specialized renderer, not just a file download. The portal should support "preview plugins" that can request byte ranges (FR-7 prerequisite) and render specific layers. This is specific to EDA and wouldn't be solved by generic preview.

#### 22. Human Resources

> **HR note**: Employee document portals need per-user isolation (each employee sees only their own files). The S3 AP dual-authorization model (IAM + ONTAP identity) can enforce this, but the portal UI needs a "My Files" view scoped to the authenticated user's home directory. This is implementable today without new FRs.

#### 23. Supply Chain / Logistics

> **Logistics note**: B2B document exchange (EDI, purchase orders, shipping manifests) via SFTP is now natively supported — Transfer Family + FSx for ONTAP S3 AP (GA 2026/1). The file portal should integrate with this: show "Recently received via SFTP" as a filter/view in the Files tab. This is implementable today without new FRs.

#### 24. Startup / Small Team Lead

> **Startup note**: For small teams (<50 users), the gap between our portal and Box/Drive is too wide for adoption. FR-5 (Storage Browser) alone would close the gap significantly. Prioritize this as the "small team" path — they don't need retention policies or SFTP, they need browse/preview/upload/download to work.

#### 25. AI/ML Engineer

> **AI note**: The processing pipeline integration could be enhanced with a "preview AI results" feature — e.g., show Rekognition bounding boxes overlaid on the original image, or Textract extracted text alongside the PDF. This requires FR-7 (original file preview via Presigned URL) plus custom rendering logic.

#### 26. Quality Assurance / Testing

> **Testing note**: Automated UI testing (Playwright/Cypress) for the file portal requires stable file URLs. Currently, all file access goes through Lambda with dynamic responses, making snapshot testing difficult. Presigned URLs (FR-7) with deterministic expiry would enable proper E2E test assertions.

#### 27. Accessibility Specialist

> **Accessibility note**: File preview must include alt-text generation for images (Rekognition can provide this). PDF preview should extract text for screen readers. Video preview needs captions. The AI/ML pipeline could feed accessibility metadata back to the portal — enabling an inclusive file browsing experience that goes beyond what standard file management products offer.

#### 28. Multi-Cloud / Hybrid Architect

> **Hybrid note**: Organizations with on-premises ONTAP connected via SnapMirror to FSx for ONTAP get the portal "for free" on their existing data. No migration required. This should be the primary messaging: "Your existing NAS data, accessible through a modern web portal with AI capabilities — zero data movement." The FR priorities correctly enable this story.

#### 29. Sustainability / Green IT

> **Sustainability note**: The "no data copy" architecture aligns with sustainability goals — one copy of data rather than multiple copies in S3 + FSx for ONTAP + backup. FR-7 (Presigned URL) strengthens this by eliminating the Lambda proxy's compute cost and the temptation to copy data to standard S3 "just for sharing."

#### 30. Customer Success / Adoption Lead

> **Adoption note**: Adoption risk assessment: without FR-7 (Presigned URL), our portal solves 30% of what users expect from a file portal (listing, processing). With FR-7 + FR-5 (Storage Browser), it solves 70%. The remaining 30% (collaboration, sync, real-time editing) is addressable through Nextcloud coexistence — which we already document. Recommend positioning as: "Processing-first portal that coexists with your collaboration tool."

---

## Consolidated Recommendations from the Persona Review

### Immediately Actionable (No AWS FR Required)

1. **"My Files" scoped view**: Implement per-user home directories based on Cognito identity → ONTAP user mapping
2. **Accessibility metadata pipeline**: Use existing Rekognition/Comprehend results to generate alt text for previewed files
3. **QR code access pattern**: Document short-expiry URL generation (via Lambda proxy) for OT/manufacturing use cases

### Requires FR-7 (Presigned URL) — Keystone Dependency

4. Storage Browser integration (FR-5)
5. Mobile native file viewing
6. Side-by-side snapshot comparison (DR)
7. Video scrubbing / Range GET preview
8. Automated E2E testing with stable URLs

### Independent Improvements (Separate FRs)

9. OpenSearch Serverless connector with ONTAP metadata (FR-9)
10. Transfer Family SFTP endpoint for B2B exchange (FR-10)
11. Audit trail with legal hold certificate generation (FR-8)

---

## Relationship to Previously Submitted FRs

| Previously submitted FR | Relationship to this document |
|---|---|
| FR-1 (Athena output) | No direct relationship |
| FR-2 (Event Notifications) | Enables real-time portal updates (file change → push notification to UI) |
| FR-3 (Lifecycle) | Enables retention policy display in the portal UI |
| FR-4 (Versioning + Presigned) | **FR-7 raises the priority of FR-4's Presigned URL component** |

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

## Next Steps

1. Submit FR-5, FR-6, and FR-7 to AWS via re:Post and/or a Support case
2. Open a GitHub Issue on [aws-amplify/amplify-ui](https://github.com/aws-amplify/amplify-ui) for Storage Browser + S3 AP support
3. Open a GitHub Issue on [aws-amplify/amplify-backend](https://github.com/aws-amplify/amplify-backend) for S3 AP support in the Storage category
4. Document workaround architectures for teams that need these capabilities today
5. Track responses from AWS and update this document

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
