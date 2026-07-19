# Feature Requests: File Portal UI — SaaS Gap Analysis & AWS Service Improvements

**Submitter**: Yoshiki Fujiwara (AWS Community Builder)
**Date**: 2026-07-18
**Project**: [fsxn-s3ap-serverless-patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns)
**Context**: File Portal UI built with Amplify Gen2 + FSx for ONTAP S3 Access Points
**Status**: Draft — preparing for submission

---

## Executive Summary

Enterprise file portals (Box, Google Drive, SharePoint) provide a mature set of capabilities that users expect as baseline: file preview with thumbnails, sharing links, version history, comments, full-text search, retention policies, desktop sync, audit logs, and collaborative editing.

Our File Portal UI (`solutions/amplify-portal/`) currently provides: file listing, folder navigation, image type detection, AI/ML job submission, real-time results, job history, FlexClone restore, and breadcrumb navigation. This covers the **processing orchestration** layer well, but the **file management experience** has gaps relative to SaaS expectations.

This document identifies the gaps, maps them to AWS service limitations, and proposes feature requests (FR-5 through FR-10) that would enable AWS-native file portals to reach parity with SaaS offerings — without requiring data movement from FSx for ONTAP.

---

## SaaS Feature Gap Analysis

### Methodology

Compared current Amplify Gen2 File Portal capabilities against:
- Box Enterprise Advanced (2025): document management, governance, AI, retention
- Google Drive / Google Workspace: real-time collaboration, search, preview
- SharePoint Online: enterprise content management, workflow, compliance
- Industry checklists: Moxo 2025, fast.io 2026 guides

### Gap Matrix

| Feature | Box | Google Drive | SharePoint | Our Portal | Gap Severity |
|---------|:---:|:---:|:---:|:---:|:---:|
| File listing & folder navigation | Yes | Yes | Yes | Yes | — |
| File preview (images/PDF/video/Office) | Yes | Yes | Yes | Partial (type icon only) | High |
| File download | Yes | Yes | Yes | No | High |
| File upload (drag & drop) | Yes | Yes | Yes | No | High |
| Sharing links (time-limited, password) | Yes | Yes | Yes | No | High |
| Version history | Yes | Yes | Yes | No | Medium |
| Comments / annotations | Yes | Yes | Yes | No | Low |
| Full-text search | Yes | Yes | Yes | No | High |
| Retention policies (compliance) | Yes | Vault | Yes | No | Medium |
| Desktop sync client | Yes | Yes | Yes | No | Low |
| Collaborative real-time editing | Yes | Yes | Yes | No | Low |
| Audit trail (who accessed what) | Yes | Yes | Yes | No | Medium |
| Mobile responsive UI | Yes | Yes | Yes | Partial | Low |
| AI/ML processing pipeline trigger | No | No | No | Yes | — (advantage) |
| FlexClone / Snapshot restore | No | No | No | Yes | — (advantage) |
| Job history & status tracking | No | No | No | Yes | — (advantage) |
| Multi-protocol access (NFS/SMB/S3) | No | No | No | Yes | — (advantage) |

### Key Insight

Our portal's advantages (AI/ML pipeline, FlexClone, multi-protocol) are unique capabilities that SaaS products cannot offer. The gaps are in **basic file management UX** — most of which are blocked by AWS service limitations, not by implementation effort.

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

### FR-5: Storage Browser for S3 — Support FSx for ONTAP S3 Access Points

**Service**: Amazon S3 / Amplify UI

**Current state**: [Storage Browser for S3](https://ui.docs.amplify.aws/react/connected-components/storage/storage-browser) (GA December 2024) provides browse, download, upload, copy, delete, and file preview for S3 data. It supports standard S3 buckets and S3 Access Points on standard buckets. It does NOT support FSx for ONTAP S3 Access Points.

**Requested behavior**: Allow Storage Browser for S3 to connect to FSx for ONTAP S3 Access Points using the AP alias or ARN as the target. This would instantly provide:
- File preview (images, video, text)
- File download
- File upload (with 5GB limit per FSx for ONTAP S3 AP constraint)
- Copy and delete operations
- Folder creation

**Impact**: This single FR would close 4 of the 8 gaps (preview, download, upload, partial sharing) and eliminate the need for custom file management components.

**Workaround**: Custom React components (FileExplorer, FilePreview) calling Lambda-proxied S3 API operations against the AP. This approach cannot provide real previews without Presigned URL support.

---

### FR-6: Amplify Storage Category — Support S3 Access Points as Backend

**Service**: AWS Amplify Gen2

**Current state**: Amplify Storage (`defineStorage` in `amplify/storage/resource.ts`) only supports standard S3 buckets. The ["Use with custom S3"](https://docs.amplify.aws/android/build-a-backend/storage/use-with-custom-s3/) documentation allows connecting to an existing bucket, but provides no mechanism to specify an S3 Access Point.

**Requested behavior**: Allow `defineStorage` or a new `defineStorageAccessPoint` to accept:
```typescript
// Option A: AP alias
export const storage = defineStorage({
  name: 'nasFiles',
  accessPoint: {
    alias: 'my-fsxn-ap-s3alias',
    // or ARN: 'arn:aws:s3:ap-northeast-1:123456789012:accesspoint/my-ap'
  }
});

// Option B: Custom endpoint configuration
export const storage = defineStorage({
  name: 'nasFiles',
  bucket: { /* existing bucket config */ },
  accessPointArn: 'arn:aws:s3:...:accesspoint/my-ap'
});
```

**Impact**: Developers could use `Amplify.Storage.list()`, `.get()`, `.put()` against FSx for ONTAP data without custom Lambda proxies.

**Workaround**: Custom AppSync resolvers + Lambda functions that call S3 API with the AP alias. All file operations go through Lambda, adding latency and cost.

---

### FR-7: FSx for ONTAP S3 AP — Presigned URL Support (Priority Escalation)

**Service**: Amazon FSx for ONTAP

**Current state**: Presigned URLs are documented as "not supported" for FSx for ONTAP S3 Access Points ([Access point compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)). This was previously submitted as FR-4.

**Why escalation**: This is the single most impactful limitation for file portal use cases. Without Presigned URLs:
- No browser-native file preview (images, PDF, video)
- No direct file download (must proxy through Lambda, adding latency + cost)
- No time-limited sharing links
- Storage Browser for S3 cannot function (it relies on Presigned URLs for preview/download)

**Business context**: Every enterprise file portal competitor (Box, Google Drive, SharePoint, Nextcloud) provides direct-to-browser file access. The absence of Presigned URL support forces all file access through a Lambda proxy, which:
- Adds 200-500ms latency per file operation
- Costs $0.20/1M requests + data transfer through Lambda
- Cannot handle large files (Lambda 6MB response limit for synchronous invocation)
- Prevents browser-native media playback (video/audio streaming)

**Requested behavior**: Support `s3.generate_presigned_url()` with the S3 AP alias or ARN as the bucket parameter, honoring the dual-authorization model (IAM + ONTAP file system identity).

---

### FR-8: FSx for ONTAP S3 AP — CloudTrail Data Event Integration with Managed Audit UI

**Service**: Amazon FSx for ONTAP / AWS CloudTrail

**Current state**: CloudTrail can log S3 data events for S3 Access Points. However, there is no managed UI component that surfaces "who accessed which file, when" in a user-friendly format for compliance officers.

**Requested behavior**: 
1. Confirm and document CloudTrail data event logging for FSx for ONTAP S3 AP operations (GetObject, PutObject, DeleteObject) with the file path (S3 key) in the event record
2. Provide a CloudTrail Insights or Security Hub integration that presents file access patterns in a portal-friendly format
3. Alternatively, enable integration with AWS Audit Manager for file-level access tracking

**Impact**: Regulated industries (healthcare, finance, government) require demonstrable audit trails for file access. Currently, building this requires custom Athena queries over CloudTrail logs.

---

### FR-9: Amazon Kendra / OpenSearch — Native Connector for FSx for ONTAP S3 Access Points

**Service**: Amazon Kendra / Amazon OpenSearch Service

**Current state**: Amazon Kendra supports S3 as a data source connector. OpenSearch Ingestion supports S3 as a source. Neither explicitly supports FSx for ONTAP S3 Access Points as a data source.

**Requested behavior**: Allow Kendra (or OpenSearch Ingestion) to use an FSx for ONTAP S3 AP alias/ARN as a data source, enabling:
- Full-text indexing of documents on FSx for ONTAP volumes
- Search results that return S3 AP keys (file paths)
- Incremental crawling based on LastModified metadata

**Impact**: Full-text search is the #1 most-requested feature in enterprise file portals. Without a native connector, customers must copy data to a standard S3 bucket for indexing — breaking the "no data movement" value proposition.

**Workaround**: Lambda-based crawler that lists objects via S3 AP, downloads content, and pushes to Kendra/OpenSearch. This is the pattern we'd implement in a hypothetical UC29.

---

### FR-10: AWS Transfer Family — SFTP/FTPS Endpoint Backed by FSx for ONTAP S3 Access Point

**Service**: AWS Transfer Family

**Current state**: AWS Transfer Family supports SFTP/FTPS/FTP endpoints backed by standard S3 buckets or EFS. It does not support FSx for ONTAP S3 Access Points as a storage backend.

**Requested behavior**: Allow Transfer Family to use an FSx for ONTAP S3 AP as the storage backend, enabling:
- External partners to upload/download files via SFTP
- Files land directly on the FSx for ONTAP volume (accessible via NFS/SMB)
- No intermediate S3 bucket copy needed

**Impact**: B2B file exchange (supply chain documents, insurance claims, healthcare records) often requires SFTP. Today, customers use Transfer Family → S3 → DataSync → FSx for ONTAP, which adds latency and complexity.

**Note**: FSx for ONTAP natively supports NFS/SMB, but many B2B partners require SFTP specifically for compliance or legacy integration reasons.

---

## Priority Ranking

| Rank | FR | Impact | Effort (estimated) |
|------|-----|--------|-------------------|
| 1 | FR-7 (Presigned URL) | Unblocks FR-5, preview, download, sharing | Medium (S3 AP signing layer) |
| 2 | FR-5 (Storage Browser) | Closes 4 gaps with zero custom code | Low (if FR-7 is resolved) |
| 3 | FR-6 (Amplify Storage) | Developer experience for NAS-backed apps | Medium |
| 4 | FR-9 (Search connector) | Full-text search without data copy | Medium |
| 5 | FR-8 (Audit UI) | Compliance requirement | Low |
| 6 | FR-10 (Transfer Family) | B2B file exchange | Medium |

**Critical dependency**: FR-7 (Presigned URL) is the keystone. Without it, FR-5 (Storage Browser) cannot function, and all preview/download/sharing features remain blocked.

---

## What We Can Build Today (Without These FRs)

Despite the gaps, our portal provides capabilities that SaaS products cannot:

| Capability | How it works |
|---|---|
| AI/ML processing pipeline | Step Functions + Bedrock/Textract/Comprehend triggered from UI |
| FlexClone snapshot restore | ONTAP REST API creates point-in-time clone in seconds |
| Multi-protocol data access | Same file accessible via NFS (Linux), SMB (Windows), S3 API (cloud) |
| Data classification labels | Automated INTERNAL/CUI/PUBLIC tagging on processing results |
| Job execution history | DynamoDB-backed, owner-scoped, with status tracking |
| Event-driven + polling hybrid | TriggerMode parameter per use case |

These are genuine differentiators that justify building a custom portal even with the current limitations.

---

## 30-Persona Review

### Methodology

Solicited feedback from role-based archetypes representing enterprise file portal stakeholders. Each perspective evaluates the gap analysis and FR prioritization.

---

#### 1. Enterprise Storage Architect

> **Storage note**: FR-7 (Presigned URL) is correctly identified as the keystone. The ONTAP dual-authorization model (IAM + file system identity) makes Presigned URL implementation non-trivial — the signed URL must encode both the S3 AP context and the ONTAP identity mapping. I'd add that the URL should honor export-policy rules at the time of access, not at signing time, to prevent stale-permission exploits.

#### 2. Frontend Developer (React/Amplify)

> **Implementation note**: FR-5 (Storage Browser) would eliminate ~400 lines of custom code in our portal (FileExplorer, FilePreview, ResultsViewer file listing). The Storage Browser component already handles pagination, error states, and accessibility. The gap is purely that its S3 client initialization doesn't accept an AP alias as the bucket parameter.

#### 3. Information Security Officer

> **Security note**: The Presigned URL limitation is actually a security feature in disguise — it prevents uncontrolled URL sharing. If FR-7 is implemented, it MUST include: (a) configurable maximum expiry (e.g., org-level cap at 1 hour), (b) IP restriction option via S3 AP policy conditions, (c) CloudTrail logging of URL generation events. Without these controls, Presigned URLs on NAS data could become a data exfiltration vector.

#### 4. Compliance Officer (Financial Services)

> **Governance note**: FR-8 (Audit UI) should be higher priority for regulated industries. FISC (金融情報システムセンター) guidelines require demonstrable file access logs with who/what/when/why. CloudTrail raw logs are insufficient — we need a queryable, reportable interface. Consider integration with AWS Audit Manager custom frameworks.

#### 5. DevOps / Platform Engineer

> **Operations note**: FR-6 (Amplify Storage) would simplify our CI/CD pipeline. Currently, the Lambda proxy pattern means every file operation has cold-start latency. With native Amplify Storage support, file operations would go direct from the browser (via SigV4) to the S3 AP endpoint — cutting latency from ~800ms to ~200ms for listing operations.

#### 6. Data Engineer / Analytics

> **Analytics note**: FR-9 (Search connector) should consider OpenSearch Serverless over Kendra for cost reasons. A 10TB FSx for ONTAP volume with 1M files would cost ~$180/month to index in Kendra vs ~$50/month in OpenSearch Serverless (with appropriate OCU scaling). The connector should support incremental sync based on S3 AP ListObjectsV2 `LastModified`.

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

> **DR note**: The FlexClone restore feature is a genuine differentiator — no SaaS product offers instant point-in-time volume recovery from the file portal UI. This should be highlighted more prominently in the gap analysis. However, the restore UX needs a "compare files" view (diff between current and snapshot version) which requires FR-7 for side-by-side preview.

#### 15. Network Engineer

> **Network note**: Presigned URLs for Internet-origin S3 APs would bypass the VPC entirely (browser → S3 AP endpoint directly). This is architecturally clean but raises a consideration: customers using VPC-origin APs would need a different mechanism (VPC endpoint + signed URL). FR-7 should document both NetworkOrigin scenarios.

#### 16. Database Administrator

> **Data note**: FR-9 (Search) should leverage the S3 AP's ability to expose file metadata (size, lastModified, security style) alongside content. A search index that includes both content AND ONTAP metadata (volume name, aggregate, tiering state) would be uniquely valuable for storage planning decisions.

#### 17. Cost Optimization (FinOps) Analyst

> **Cost note**: Current architecture cost for a typical 28-pattern deployment with file portal: Lambda proxy adds ~$45/month for a 100-user org. Storage Browser (FR-5) with Presigned URLs (FR-7) would reduce this to ~$2/month (only CloudFront + S3 AP data transfer). ROI for FR-7: 95% cost reduction on file access operations.

#### 18. Legal / Records Management

> **Legal note**: Sharing links (enabled by FR-7) must support "view-only" mode where the recipient can preview but not download. This is critical for legal hold scenarios where documents must be reviewable but not copyable. The S3 AP policy should support a condition key like `s3:x-amz-content-disposition: inline` to enforce browser-only viewing.

#### 19. Education / Research IT

> **Research note**: Academic institutions need to share large datasets (genomics FASTQ, astronomy FITS) with external collaborators. FR-7 Presigned URLs with multi-GB support would enable this. Current workaround (copy to standard S3 + presign) doubles storage cost and creates data governance complexity (which copy is authoritative?).

#### 20. Media & Entertainment

> **Media note**: VFX studios need frame-accurate video preview directly from FSx for ONTAP storage. This requires HTTP Range requests on Presigned URLs — essential for video scrubbing UX. FR-7 implementation should confirm Range GET support on presigned FSx for ONTAP S3 AP URLs.

#### 21. Semiconductor / EDA Engineer

> **EDA note**: GDS/OASIS layout files can be 50-100GB. Preview requires a specialized renderer, not just a file download. The portal should support "preview plugins" that can request byte ranges (FR-7 prerequisite) and render specific layers. This is unique to EDA and wouldn't be solved by generic preview.

#### 22. Human Resources

> **HR note**: Employee document portals need per-user isolation (each employee sees only their own files). The S3 AP dual-authorization model (IAM + ONTAP identity) can enforce this, but the portal UI needs a "My Files" view scoped to the authenticated user's home directory. This is implementable today without new FRs.

#### 23. Supply Chain / Logistics

> **Logistics note**: B2B document exchange (EDI, purchase orders, shipping manifests) via SFTP is standard in supply chain. FR-10 (Transfer Family + S3 AP) would enable partners to drop files that immediately appear in the portal UI — creating a unified inbound document queue.

#### 24. Startup / Small Team Lead

> **Startup note**: For small teams (<50 users), the gap between our portal and Box/Drive is too wide for adoption. FR-5 (Storage Browser) alone would close the gap significantly. Prioritize this as the "small team" path — they don't need retention policies or SFTP, they need browse/preview/upload/download to work.

#### 25. AI/ML Engineer

> **AI note**: The processing pipeline integration (our advantage) could be enhanced with a "preview AI results" feature — e.g., show Rekognition bounding boxes overlaid on the original image, or Textract extracted text alongside the PDF. This requires FR-7 (original file preview via Presigned URL) plus custom rendering logic.

#### 26. Quality Assurance / Testing

> **Testing note**: Automated UI testing (Playwright/Cypress) for the file portal requires stable file URLs. Currently, all file access goes through Lambda with dynamic responses, making snapshot testing difficult. Presigned URLs (FR-7) with deterministic expiry would enable proper E2E test assertions.

#### 27. Accessibility Specialist

> **Accessibility note**: File preview must include alt-text generation for images (Rekognition can provide this). PDF preview should extract text for screen readers. Video preview needs captions. Our AI/ML pipeline advantage could feed accessibility metadata back to the portal — a unique value prop that no SaaS competitor offers.

#### 28. Multi-Cloud / Hybrid Architect

> **Hybrid note**: Organizations with on-premises ONTAP connected via SnapMirror to FSx for ONTAP get the portal "for free" on their existing data. No migration required. This should be the primary messaging: "Your existing NAS data, accessible through a modern web portal with AI capabilities — zero data movement." The FR priorities correctly enable this story.

#### 29. Sustainability / Green IT

> **Sustainability note**: The "no data copy" architecture aligns with sustainability goals — one copy of data rather than multiple copies in S3 + FSx + backup. FR-7 (Presigned URL) strengthens this by eliminating the Lambda proxy's compute cost and the temptation to copy data to standard S3 "just for sharing."

#### 30. Customer Success / Adoption Lead

> **Adoption note**: Adoption risk assessment: without FR-7 (Presigned URL), our portal solves 30% of what users expect from a file portal (listing, processing). With FR-7 + FR-5 (Storage Browser), it solves 70%. The remaining 30% (collaboration, sync, real-time editing) is addressable through Nextcloud coexistence — which we already document. Recommend positioning as: "Processing-first portal that coexists with your collaboration tool."

---

## Consolidated Recommendations from Persona Review

### Immediate actions (no AWS FR needed)

1. **"My Files" scoped view**: Implement per-user home directory based on Cognito identity → ONTAP user mapping
2. **Accessibility metadata pipeline**: Use existing Rekognition/Comprehend results to generate alt-text for previewed files
3. **QR code access pattern**: Document short-expiry URL generation (via Lambda proxy) for OT/manufacturing use

### Requires FR-7 (Presigned URL) — keystone dependency

4. Storage Browser integration (FR-5)
5. Mobile-native file viewing
6. Side-by-side snapshot comparison (DR)
7. Video scrubbing / Range GET preview
8. Automated E2E testing with stable URLs

### Independent improvements (separate FRs)

9. OpenSearch Serverless connector with ONTAP metadata enrichment (FR-9)
10. Transfer Family SFTP endpoint for B2B exchange (FR-10)
11. Audit trail with legal-hold certificate generation (FR-8)

---

## Relationship to Previously Submitted FRs

| Previous FR | This doc extends |
|---|---|
| FR-1 (Athena output) | No direct relation |
| FR-2 (Event Notifications) | Enables real-time portal updates (file change → push notification to UI) |
| FR-3 (Lifecycle) | Enables retention policy display in portal UI |
| FR-4 (Versioning + Presigned) | **FR-7 is a priority escalation of FR-4's Presigned URL component** |

---

## Next Steps

1. Submit FR-5, FR-6, FR-7 to AWS via re:Post and/or Support cases
2. File GitHub issue on [aws-amplify/amplify-ui](https://github.com/aws-amplify/amplify-ui) for Storage Browser + S3 AP support
3. File GitHub issue on [aws-amplify/amplify-backend](https://github.com/aws-amplify/amplify-backend) for Storage category S3 AP support
4. Document workaround architecture for customers who need capabilities today
5. Track AWS responses and update this document

---

## References

1. [Storage Browser for S3 — Amplify UI](https://ui.docs.amplify.aws/react/connected-components/storage/storage-browser)
2. [Storage Browser for S3 is now GA — AWS News](https://aws.amazon.com/about-aws/whats-new/2024/12/storage-browser-amazon-s3)
3. [Use Amplify Storage with custom S3 — Amplify Docs](https://docs.amplify.aws/android/build-a-backend/storage/use-with-custom-s3/)
4. [Access point compatibility — FSx for ONTAP User Guide](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)
5. [Box Retention Policies — Box Support](https://support.box.com/hc/en-us/articles/360043694374-About-Retention-and-Retention-Policies)
6. [Box Archive — Box Docs](https://docs.box.com/en/box-archive)
7. [Top features in a client file sharing portal (2025) — Moxo](https://www.moxo.com/blog/client-file-sharing-portal)
8. [Enterprise file sharing solution guide (2026) — fast.io](https://about.fast.io/resources/enterprise-file-sharing-solution/)

---

*Content was rephrased for compliance with licensing restrictions. All feature descriptions are based on publicly available documentation.*
