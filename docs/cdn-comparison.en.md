# CDN / Edge Delivery Integration Comparison — Delivering from FSx ONTAP S3 Access Points

🌐 **Language / 言語**: [日本語](cdn-comparison.md) | [English](cdn-comparison.en.md) | [한국어](cdn-comparison.ko.md) | [简体中文](cdn-comparison.zh-CN.md) | [繁體中文](cdn-comparison.zh-TW.md) | [Français](cdn-comparison.fr.md) | [Deutsch](cdn-comparison.de.md) | [Español](cdn-comparison.es.md)

## 0. Scope

A technical-feasibility reference for delivering data on FSx for ONTAP S3 Access Points (S3 AP)
through a CDN / edge network. This document does **not** rank vendors, compare price/performance, or
make marketing claims. It only addresses **what is technically achievable, what is not, and what
requires verification** against the constraints of FSx ONTAP S3 AP. Vendor selection depends on
customer contracts, SLAs, operations, and regional requirements outside this document's scope.

## 1. S3 AP constraints that drive delivery design

| Constraint | Detail | Impact on delivery |
|------------|--------|--------------------|
| Block Public Access enforced (cannot disable) | Default-on, immutable | No unauthenticated public origin; origin auth required |
| Origin auth is SigV4 (IAM) | Requests evaluated by IAM / AP policy | CDN must sign origin requests with AWS SigV4 |
| Dual-layer authz (AWS + ONTAP) | IAM then ONTAP file identity (UNIX UID / Windows AD) | Delivery limited to what the ONTAP identity can read |
| Presigned URLs unsupported | Officially not supported | Viewer token auth cannot use S3 presigned URLs; use CDN-native tokens |
| NetworkOrigin (Internet/VPC, immutable) | CDN accesses from managed/external network | CDN integration needs **Internet origin** |
| PutObject max 5 GB | Single PUT limit | Large write-backs need multipart |

## 2. Integration mechanisms (vendor-neutral)

- **M1 — Native SigV4 origin-pull**: CDN pulls the S3 AP directly, signing origin requests with SigV4.
  Achievable where the CDN ships SigV4 origin signing. **To verify**: the S3 AP `accesspoint alias`
  host differs from a standard bucket; SigV4 behavior must be validated on hardware.
- **M2 — Edge-compute SigV4 signing**: implement SigV4 in the CDN's edge runtime (Workers/Compute/EdgeWorkers).
  Achievable where native origin signing is absent; you own signing/key management.
- **M3 — Push to a CDN-native S3-compatible store**: keep FSx as master, replicate only approved
  renditions to the CDN's object store. Avoids the origin-auth question; CDN-agnostic; lowest-risk first step.
- **M4 — Self-managed SigV4 signing proxy**: place a signing intermediary (Lambda Function URL / ALB) as the
  origin. Works with almost any CDN; the proxy becomes an availability/scaling concern.

> Universal constraint: viewer token auth cannot use S3 presigned URLs — use CDN-native tokens.
> Public delivery bypasses NFS/SMB ACLs, so deliver only approved renditions (see section 4).

## 3. Mechanism support per delivery network (fact-based)

○ = documented native feature / △ = conditional or self-implemented / − = no such feature / TBV = S3 AP-specific verification needed.

| Network | M1 native SigV4 pull | M2 edge signing | M3 own S3-compatible store | Viewer token | S3 AP-specific TBV |
|---------|:---:|:---:|:---:|---|---|
| Amazon CloudFront | ○ OAC (SigV4) | △ Lambda@Edge / Functions | (to standard S3) | CloudFront signed URL/Cookie | **Proven** (AWS official tutorial shows S3 AP + OAC) |
| Akamai | ○ Cloud Access Manager (AWS signing) | △ EdgeWorkers | ○ NetStorage / Object Storage | Akamai Token Auth | Signing on AP alias host TBV |
| Fastly | ○ SigV4 to S3-compatible private origin | △ Compute | ○ Fastly Object Storage | Fastly signed URL | SigV4 on AP alias TBV |
| Cloudflare | − (no native SigV4 at proxy) | ○ Workers SigV4 signing | ○ R2 (S3-compatible) | Cloudflare signed URL | Workers signing + AP alias TBV |
| Bunny.net | △ S3 origin pull (AWS S3 origin type) | − | ○ Bunny Storage (S3-compatible API, beta) | Pull Zone token auth | Signing on AP alias TBV |
| Google Cloud CDN / Media CDN | ○ private S3-compatible origin SigV4 auth | △ Media CDN routing | (GCS / any S3-compatible) | Media CDN signed URL/Cookie | Cross-cloud egress + AP alias TBV |

### Noted but not table-ranked
- **Azure Front Door / Azure CDN**: same mechanism (M1/M4) may apply; out of primary scope; TBV.
- **Gcore**: S3-compatible storage + storage-as-origin (M3); out of primary scope.
- **Edgio (formerly Limelight / Edgecast)**: **CDN service ceased on 2025-01-15**; most assets acquired by
  Akamai. **Not a live option** — excluded.

> Sources are public vendor docs (CloudFront OAC, Akamai Cloud Access Manager, Fastly S3-compatible private
> origins, Cloudflare Workers/R2, Bunny Storage, Google Media CDN). All describe **standard S3-compatible
> buckets**; behavior on the FSx ONTAP S3 AP accesspoint alias is TBV.

## 4. Fixed security requirements (mechanism-agnostic)

1. Public delivery bypasses NFS/SMB ACLs — deliver **only approved renditions**; never route ACL-controlled
   master data straight to the delivery layer.
2. Separate master (ACL-controlled, sensitive) from delivery artifacts (public/semi-public). M3 makes this natural.
3. Viewer auth via CDN-native token mechanisms (no S3 presigned URLs).
4. Least-privilege origin credentials; avoid long-lived keys at the edge; prefer short-lived credentials.
5. Delivery logs: address viewer PII when writing logs back to FSx.
6. **Approval provenance**: record which object was approved for public delivery, by whom, and when.
   Objects with no recorded approver are **surfaced** (recorded as `unrecorded`), not silently blocked.
7. **Data residency / geo-restriction**: CDNs deliver globally. Exclude data that may not leave a region,
   or enforce geo-blocking; include residency checks in the approval process.

### 4.1 Evidence classification
- **Public evidence**: section 3 vendor capabilities — based on public docs, **time-sensitive**, re-verify before adoption.
- **To be verified (this project)**: SigV4 origin signing behavior against the FSx ONTAP S3 AP accesspoint alias.

## 5. Feasibility summary

| Question | Answer |
|----------|--------|
| Expose S3 AP as an unauthenticated CDN origin? | **No** (BPA enforced) |
| Deliver directly from S3 AP via CDN? | **Yes, conditionally** — M1/M2 with SigV4; AP-alias signing is TBV |
| Deliver via a CDN without SigV4? | **Yes** — M3 (push) or M4 (signing proxy) |
| Use S3 presigned URLs for viewers? | **No** — use CDN-native tokens |
| Enforce ONTAP ACLs at delivery time? | **No** — enforce via "approved renditions only" + provenance |
| Lowest-verification-risk first step? | **M3 (push)** — avoids origin-auth, CDN-agnostic, DemoMode-friendly |

> **Governance Caveat**: This is technical reference information. Vendor features change; re-verify against
> the latest official docs before adoption. SigV4 origin signing against the S3 AP accesspoint alias is a
> project verification item (TBV). See the [ORIGIN_PULL SigV4 verification checklist](cdn-origin-verification-checklist.en.md)
> for the hardware procedure. Vendor selection is the customer's decision.
