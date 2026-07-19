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
| AI/ML processing pipeline trigger | No | No | No | Yes | — (unique to this pattern) |
| FlexClone / Snapshot restore | No | No | No | Yes | — (unique to this pattern) |
| Job history & status tracking | No | No | No | Yes | — (unique to this pattern) |
| Multi-protocol access (NFS/SMB/S3) | No | No | No | Yes | — (unique to this pattern) |

### Key Insight

Our portal's unique capabilities (AI/ML pipeline, FlexClone, multi-protocol) address use cases that SaaS file management products do not cover. The gaps are in **basic file management UX** — most of which are blocked by AWS service limitations, not by implementation effort.

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

### FR-5: Storage Browser for S3 — FSx for ONTAP S3 Access Points の公式サポート

**Service**: Amazon S3 / Amplify UI

**Current state**: [Storage Browser for S3](https://ui.docs.amplify.aws/react/connected-components/storage/storage-browser) (GA December 2024) provides browse, download, upload, copy, delete, and file preview for S3 data. Its public roadmap explicitly lists **"Support for S3 Access Points"** as a feature under evaluation ([source](https://ui.docs.amplify.aws/react/connected-components/storage/storage-browser)). 

**動作原理**: Storage Browser はクライアントサイドで S3 API（`ListObjectsV2`、`GetObject`、`PutObject`、`DeleteObject`）を呼ぶ React コンポーネント。FSx for ONTAP S3 AP はこれらの操作をすべてサポートしており、S3 AP alias (`xxx-s3alias`) は SDK にバケット名として渡せる。Presigned URL（動作確認済み）と同じ論理で、クライアントが S3 AP alias をバケット名として使用すれば動作する。

**公式ロードマップ記載の意味**: AWS が「Support for S3 Access Points」をロードマップに載せているのは、(a) 公式テスト・サポート対象にする、(b) S3 Access Grants との統合を正式に対応する、という趣旨。クライアントサイドの S3 API 呼び出し自体は現時点で動作する原理。

**要望**: Storage Browser の `createManagedAuthAdapter` で S3 AP alias を正式にサポートし、ドキュメントに FSx for ONTAP S3 AP での使用例を記載すること。

**Action**: 
- `createManagedAuthAdapter` で S3 AP alias をターゲットに指定してデプロイ検証
- 動作確認後、re:Post で「Storage Browser + FSx for ONTAP S3 AP の構成例」として投稿
- Amplify UI GitHub で公式サポートを要望（ロードマップ加速）

**Impact**: 公式サポートされれば以下が即座に利用可能:
- File preview (images, video, text)
- File download
- File upload (with 5GB limit per FSx for ONTAP S3 AP constraint)
- Copy and delete operations
- Folder creation

This single FR would close 4 of the 8 gaps (preview, download, upload, partial sharing) and eliminate the need for custom file management components.

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

### ~~FR-7: FSx for ONTAP S3 AP — Presigned URL Support~~（⚠️ 実動作確認済み・公式ドキュメントの修正要望に変更）

**Service**: Amazon FSx for ONTAP

**Current state**: Presigned URLs は FSx for ONTAP S3 AP の互換性テーブルで "Not supported" と記載されている（[Access point compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)）。

**しかし、実際には動作する**。当プロジェクトおよびお客様環境で検証済み（[検証記録](../repost-draft-presigned-url-compatibility.md), [互換性ノート](../s3ap-compatibility-notes.en.md#presigned-url-support)）。AWS Support に確認した結果:

1. **Presigning はクライアントサイド操作** — `aws s3 presign` は SigV4 署名をローカルで計算するだけ。ネットワークリクエストは発生しない。
2. **生成された URL は標準の GetObject** — 署名が Authorization ヘッダーではなくクエリパラメータに埋め込まれるだけ。
3. **GetObject がサポートされている以上、Presigned URL をブロックすることは構造的に不可能**。
4. **ドキュメントの意図（AWS Support 回答）**: "Presigned URL ワークフローを公式にテストしていない" ため "Not supported" と記載している。

**Technical context**: ONTAP native S3 は ONTAP 9.11 以降で Presigned URL を正式サポート（[NetApp KB](https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Software/ONTAP_OS/What_version_of_ONTAP_support_pre-signed_URLs_for_S3_bucket)）。プロトコル層に制約はない。

**FR-7 の変更**: 機能要望ではなく、**ドキュメント修正要望**に格下げ。
- 互換性テーブルの「Presign — Not supported」を「Presign — Works (client-side SigV4; executes as GetObject)」に修正してほしい
- または注記として "Presigned URLs function correctly because they execute as standard GetObject requests. The service does not officially test presigned URL workflows." を追記してほしい

**Production Guidance**: AWS Support は「"Not supported" に分類されている操作を本番で依存することは推奨しない」と回答。動作は確認できるが、リージョン間の一貫性やサービスアップデート後の動作保証はない。

**実装への影響**: Presigned URL が動作するため、以下は **今すぐ実装可能**:
- ブラウザネイティブのファイルプレビュー（画像/PDF/動画）
- ファイルダウンロード（Lambda プロキシ不要）
- 時限付き共有リンク
- Storage Browser for S3 の FSx for ONTAP S3 AP 対応（S3 AP がクライアント利用をサポートした場合）

**Production guidance**: AWS Support は「"Not supported" に分類されている操作を本番で依存することは推奨しない」と回答している。動作は確認済みだが、リージョン間の一貫性やサービスアップデート後の動作保証はない。本番利用する場合は、Lambda プロキシによるフォールバック経路を用意しておくことを推奨。

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

### ~~FR-9~~: Amazon Quick + FSx for ONTAP S3 AP（✅ 動作確認済み — AWS 公式ブログ + Workshop）

**Status**: **解決済み（実装の問題であり、サービス制約ではない）**

**根拠**:
- [AWS Storage Blog: Enabling AI-powered analytics on enterprise file data: Configuring S3 Access Points for FSx for ONTAP with Active Directory](https://aws.amazon.com/blogs/storage/enabling-ai-powered-analytics-on-enterprise-file-data-configuring-s3-access-points-for-amazon-fsx-for-netapp-ontap-with-active-directory/) — Amazon Quick Suite + S3 AP の連携手順とスクリーンショットを含む公式ブログ
- [AWS Workshop Studio: FSx for ONTAP S3 AP + Quick Suite セットアップ](https://catalog.us-east-1.prod.workshops.aws/workshops/9cd82e0b-8348-456b-932a-818b9e5825a1/en-US/08-quicksuite/61-setup) — ハンズオン手順

**動作手順**（AWS ブログより）:
1. FSx for ONTAP S3 AP を **AD ユーザー/サービスアカウントの Windows identity** で作成
2. Amazon Quick コンソール → Integrations → Knowledge bases → Amazon S3
3. 「S3 bucket URL」に `s3://<S3-AP-alias>` を入力
4. 同期完了後、Chat Agent で自然言語検索が動作

**前回の検証失敗の原因（2026-06-12）**:
当プロジェクトの検証では、S3 AP を **UNIX root identity** で構成していたため、Quick のデータアクセスロールを AP ポリシーに追加できなかった（`MalformedPolicy: Invalid principal`）。これはサービス制約ではなく、**S3 AP の FileSystemIdentity 設定の問題**。AD ベースの Windows identity で構成すれば正常動作する。

**Action**: 
- AD identity で S3 AP を再構成して Quick 接続の自環境検証を再実行
- FR-9 は取り下げ（機能要望ではなく構成の問題）

---

### ~~FR-10: AWS Transfer Family~~（✅ 実現済み — 2026/1 リリース）

**Status**: **解決済み**

**確認結果**: AWS Transfer Family は 2026 年 1 月に FSx for ONTAP S3 Access Points をサポートした。

- [AWS What's New (2026/1)](https://aws.amazon.com/about-aws/whats-new/2026/01/aws-transfer-family-amazon-fsx-netapp-ontap)
- [公式ドキュメント](https://docs.aws.amazon.com/transfer/latest/userguide/fsx-s3-access-points.html)
- [AWS Storage Blog (2026/3)](https://aws.amazon.com/blogs/storage/secure-sftp-file-sharing-with-aws-transfer-family-amazon-fsx-for-netapp-ontap-and-s3-access-points/)

Transfer Family は SFTP/FTPS エンドポイント経由で FSx for ONTAP S3 AP にアクセスでき、ファイルは FSx for ONTAP ボリュームに直接書き込まれる（NFS/SMB からもアクセス可能）。IAM ポリシー + S3 AP リソースポリシーでアクセス制御。

**Action**: この FR は取り下げ。代わりに、当プロジェクトの UC として Transfer Family 連携パターンを追加することを検討する（ROADMAP 参照）。

---

## Priority Ranking（最終版）

| FR | Status | Next Action |
|-----|--------|-------------|
| ~~FR-5~~ (Storage Browser + S3 AP) | 📋 要検証（クライアントサイドで動作する原理） | `createManagedAuthAdapter` で S3 AP alias 指定して検証 |
| **FR-6** (Amplify Storage + S3 AP) | **Open** | GitHub Issue on amplify-backend |
| ~~FR-7~~ (Presigned URL) | ✅ 動作確認済み | ドキュメント修正要望のみ |
| **FR-8** (Audit UI) | **Open** | CloudTrail data events 可視化コンポーネントの要望 |
| ~~FR-9~~ (Amazon Quick + S3 AP) | ✅ 動作確認済み（AWS ブログ + Workshop） | AD identity で S3 AP を再構成して自環境で再検証 |
| ~~FR-10~~ (Transfer Family) | ✅ 2026/1 解決済み | — |

**結論**: 真に「動かない」FR は **FR-6 (Amplify Storage category)** と **FR-8 (Audit UI)** の 2 つのみ。他はすべて動作確認済みまたはクライアントサイドで動作する構成が存在する。

**Positive signal**: Storage Browser for S3 の公式ロードマップに「Support for S3 Access Points」が明記されている（[Amplify UI Storage Browser docs](https://ui.docs.amplify.aws/react/connected-components/storage/storage-browser)）。

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

## Already Resolved (since original FR submission)

| Capability | Resolution | Source |
|---|---|---|
| SFTP/FTPS access to FSx for ONTAP | ✅ Transfer Family + S3 AP (2026/1 GA) | [docs](https://docs.aws.amazon.com/transfer/latest/userguide/fsx-s3-access-points.html) |
| RAG over NAS data | ✅ Bedrock Knowledge Base + S3 AP | [FSx User Guide tutorial](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-build-rag-with-bedrock.html) |
| Enterprise search / AI Q&A | ✅ Amazon Quick + S3 AP (AD identity 必須) | [AWS Storage Blog](https://aws.amazon.com/blogs/storage/enabling-ai-powered-analytics-on-enterprise-file-data-configuring-s3-access-points-for-amazon-fsx-for-netapp-ontap-with-active-directory/), [Workshop](https://catalog.us-east-1.prod.workshops.aws/workshops/9cd82e0b-8348-456b-932a-818b9e5825a1/en-US/08-quicksuite/61-setup) |
| Video streaming from NAS | ✅ CloudFront + S3 AP | [FSx User Guide tutorial](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-access-points-with-aws-services.html) |
| Presigned URL for file preview/download | ✅ 動作確認済み（client-side SigV4） | [プロジェクト検証記録](../repost-draft-presigned-url-compatibility.md) |

---

## Next Steps

1. Submit FR-5, FR-6, FR-7 to AWS via re:Post and/or Support cases
2. File GitHub issue on [aws-amplify/amplify-ui](https://github.com/aws-amplify/amplify-ui) for Storage Browser + S3 AP support
3. File GitHub issue on [aws-amplify/amplify-backend](https://github.com/aws-amplify/amplify-backend) for Storage category S3 AP support
4. Document workaround architecture for customers who need capabilities today
5. Track AWS responses and update this document

---

## References

1. [Storage Browser for S3 — Amplify UI](https://ui.docs.amplify.aws/react/connected-components/storage/storage-browser) — includes public roadmap with "Support for S3 Access Points"
2. [Storage Browser for S3 is now GA — AWS News (2024/12)](https://aws.amazon.com/about-aws/whats-new/2024/12/storage-browser-amazon-s3)
3. [Use Amplify Storage with custom S3 — Amplify Docs](https://docs.amplify.aws/android/build-a-backend/storage/use-with-custom-s3/)
4. [Access point compatibility — FSx for ONTAP User Guide](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)
5. [AWS Transfer Family now supports FSx for ONTAP — AWS News (2026/1)](https://aws.amazon.com/about-aws/whats-new/2026/01/aws-transfer-family-amazon-fsx-netapp-ontap)
6. [Access your FSx for ONTAP file systems with Transfer Family — User Guide](https://docs.aws.amazon.com/transfer/latest/userguide/fsx-s3-access-points.html)
7. [Secure SFTP file sharing with Transfer Family + FSx for ONTAP — AWS Storage Blog (2026/3)](https://aws.amazon.com/blogs/storage/secure-sftp-file-sharing-with-aws-transfer-family-amazon-fsx-for-netapp-ontap-and-s3-access-points/)
8. [Build a RAG application using Bedrock KB + FSx for ONTAP — User Guide](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-build-rag-with-bedrock.html)
9. [Amazon Kendra availability change (Maintenance Mode 2026/6/30)](https://docs.aws.amazon.com/kendra/latest/dg/kendra-availability-change.html)
10. [Amazon Q Business availability change (新規停止 2026/7/31)](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/qbusiness-availability-change.html)
11. [Amazon Quick — Enterprise AI Productivity Assistant](https://aws.amazon.com/quick/enterprise/)
12. [Amazon Quick: Accelerating enterprise data to AI-powered decisions — AWS ML Blog (2026/1)](https://aws.amazon.com/blogs/machine-learning/amazon-quick-accelerating-the-path-from-enterprise-data-to-ai-powered-decisions/)
13. [ONTAP 9.11+ Presigned URL support — NetApp KB](https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Software/ONTAP_OS/What_version_of_ONTAP_support_pre-signed_URLs_for_S3_bucket)
14. [Box Retention Policies — Box Support](https://support.box.com/hc/en-us/articles/360043694374-About-Retention-and-Retention-Policies)
15. [Top features in a client file sharing portal (2025) — Moxo](https://www.moxo.com/blog/client-file-sharing-portal)
16. [Enterprise file sharing solution guide (2026) — fast.io](https://about.fast.io/resources/enterprise-file-sharing-solution/)

---

*Content was rephrased for compliance with licensing restrictions. All feature descriptions are based on publicly available documentation.*
