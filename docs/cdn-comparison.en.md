# CDN / Edge Delivery Integration Comparison — Delivering from FSx for ONTAP S3 Access Points

🌐 **Language / 言語**: [日本語](cdn-comparison.md) | English | [한국어](cdn-comparison.ko.md) | [简体中文](cdn-comparison.zh-CN.md) | [繁體中文](cdn-comparison.zh-TW.md) | [Français](cdn-comparison.fr.md) | [Deutsch](cdn-comparison.de.md) | [Español](cdn-comparison.es.md)

## 0. Scope

A technical-feasibility reference for delivering data on FSx for ONTAP S3 Access Points (S3 AP)
through a CDN / edge network. This document does **not** rank vendors, compare price/performance, or
make marketing claims. It only addresses **what is technically achievable, what is not, and what
requires verification** against the constraints of FSx for ONTAP S3 AP. Vendor selection depends on
customer contracts, SLAs, operations, and regional requirements outside this document's scope.

## 1. S3 AP constraints that drive delivery design

| Constraint | Detail | Impact on delivery |
|------------|--------|--------------------|
| Block Public Access enforced (cannot disable) | Default-on, immutable | No unauthenticated public origin; origin auth required |
| Origin auth is SigV4 (IAM) | Requests evaluated by IAM / AP policy | CDN must sign origin requests with AWS SigV4 |
| Dual-layer authz (AWS + ONTAP) | IAM then ONTAP file identity (UNIX UID / Windows AD) | Delivery limited to what the ONTAP identity can read |
| Presigned URLs unsupported | Officially not supported | Viewer token auth cannot use S3 presigned URLs; use CDN-native tokens |
| NetworkOrigin (Internet/VPC, immutable) | CDN accesses from managed/external network | CDN integration needs **Internet origin** |
| 50 GB object size limit | Single PUT limited to 5 GB | Write-backs above 5 GB need multipart |

## 2. Integration mechanisms (vendor-neutral)

Ways to connect an S3 AP to a delivery network fall into four technical categories.

### M1: Native SigV4 origin-pull (the CDN fetches the S3 AP directly)

```
Viewer → CDN Edge ──(SigV4 signed)──> S3 AP (Internet origin) → FSx for ONTAP
```

- Applies when the CDN **ships built-in support** for signing origin requests with AWS SigV4 on a cache miss.
- **What is achievable**: deliver artifacts on FSx for ONTAP directly, without moving data.
- **Not achievable / to verify**: an S3 AP uses **different addressing (the `accesspoint alias` hostname)** than
  a standard S3 bucket. Whether each CDN's SigV4 implementation signs correctly for the combination of
  AP alias host + Region + the `s3` service name **requires hands-on verification** (a track record with
  standard buckets does not automatically carry over to an AP).

### M2: SigV4 signing via edge compute

```
Viewer → CDN Edge (SigV4 signed in Worker/Compute) → S3 AP → FSx for ONTAP
```

- Implement SigV4 yourself in the edge runtime when the CDN has no built-in origin signing.
- **What is achievable**: the equivalent of M1 even on CDNs without native origin signing, with full control
  over the signing logic.
- **Not achievable / to verify**: you must maintain the signing implementation, key management, and cache-key
  design yourself. How AWS credentials reach the edge (avoiding long-lived keys, using short-lived credentials)
  is a design problem.

### M3: Publish to a CDN-native S3-compatible store (push)

```
FSx for ONTAP ─(S3 AP read)→ processing ─push→ CDN-side S3-compatible store → CDN Edge → Viewer
```

- Keep FSx for ONTAP as the master and write out **only the approved, transcoded renditions** to the CDN's
  object store.
- **What is achievable**: **avoids** the S3 AP origin-authentication question. CDN-agnostic. The master and the
  delivery tier can be physically separated.
- **Not achievable / to verify**: the delivery store is a copy of FSx for ONTAP, so replication lag,
  consistency, and dual-custody all need design. Not suited to delivery with real-time requirements.

### M4: Self-managed SigV4 signing proxy as a generic HTTP origin

```
Viewer → CDN Edge → signing proxy (adds SigV4) → S3 AP → FSx for ONTAP
```

- Even a CDN with neither SigV4 origin signing nor edge compute can integrate if you place a signing
  intermediary (Lambda + Function URL / ALB, etc.) as the origin.
- **What is achievable**: the equivalent of M1 on nearly any CDN.
- **Not achievable / to verify**: the intermediary becomes a single point of failure and a scaling target.
  The proxy needs its own availability design.

> **Universal hard constraint**: with any of these mechanisms, S3 presigned URLs cannot be used for
> viewer-facing token authentication. Implement viewer auth with each CDN's native token / signed-URL
> mechanism.
> Also, because public delivery does not pass through ONTAP NFS/SMB ACLs, **restrict what you deliver to
> approved renditions** (see section 4).

---

## 2.5 Performance / throughput considerations (Storage design)

CDN integration affects the shared throughput design of FSx for ONTAP. You need to understand the read-load
characteristics of each delivery mechanism.

| Aspect | ORIGIN_PULL (M1/M2/M4) | PUBLISH_PUSH (M3) |
|--------|------------------------|-------------------|
| FSx for ONTAP read load | Occurs on every cache miss (ongoing) | Initial replication only (zero at steady state) |
| Cache stampede | Simultaneous origin fetches can concentrate on FSx for ONTAP | Absorbed by the delivery store (independent of FSx for ONTAP) |
| Bandwidth contention with production NFS/SMB | Yes (S3 AP/NFS/SMB share throughput) | Only during initial replication |
| Partial fetch of large media | Range GET is effective (depends on CDN→S3 AP Range support) | Depends on Range delivery in the store |

### What is achievable / design considerations (fact-based)

- Provisioned throughput on FSx for ONTAP is shared across NFS/SMB/S3 AP. ORIGIN_PULL origin fetches share
  bandwidth with production workloads, so you need to **estimate the cache-miss rate and concurrent connections**.
- CDN-side **Origin Shield / high TTL / tiered caching** can reduce the number of origin fetches (a per-CDN
  feature).
- One option is to use **FlexCache** to separate a delivery-read cache volume from production volumes
  (ONTAP native; see the FlexCache pattern set for details). This is a design decision based on requirements
  and cost.
- PUBLISH_PUSH generates no FSx for ONTAP reads during steady-state delivery after the initial replication, so
  the impact on production workloads is small.

> All quantitative values depend on the FSx for ONTAP configuration (throughput capacity), file size, and cache
> hit rate, so **production estimates must be based on measurement** (do not present general guidance as
> figures for a specific environment).

## 2.6 Cost considerations (qualitative)

| Mechanism | Primary cost components |
|-----------|------------------------|
| ORIGIN_PULL | FSx reads (cache-miss share) + AWS data-transfer out (S3 AP → CDN) + CDN delivery |
| PUBLISH_PUSH | Delivery-store storage (approved renditions only) + initial replication transfer + CDN delivery |

> These are **qualitative cost factors**, not dollar amounts. Actual costs depend on traffic volume, object
> sizes, cache-hit ratios, and each vendor's current pricing. Calculate with real traffic projections against
> latest pricing — do not extrapolate sample-run costs to production.

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
> buckets**; behavior on the FSx for ONTAP S3 AP accesspoint alias is TBV.

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

## 4.1 Evidence classification
- **Public evidence**: section 3 vendor capabilities — based on public docs, **time-sensitive**, re-verify before adoption.
- **To be verified (this project)**: SigV4 origin signing behavior against the FSx for ONTAP S3 AP accesspoint alias.

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
