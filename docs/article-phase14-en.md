---
title: "Evidence Expansion, Presigned URL Discovery, and Operational Surprises — FSx for ONTAP S3 Access Points, Phase 14"
published: false
series: "FSx for ONTAP S3 Access Points"
tags: aws, serverless, amazonfsxfornetappontap, s3accesspoints
---

# Evidence Expansion, Presigned URL Discovery, and Operational Surprises — FSx for ONTAP S3 Access Points, Phase 14

## TL;DR

Phase 14 shifts from building patterns to **hardening the evidence base**. After publishing Phase 13's field-ready reference architecture, we focused on post-publication refinement: Partner/SI delivery assets, benchmark methodology standardization, S3 AP compatibility clarification (Presigned URLs work despite documentation), and an unexpected operational discovery — S3 Access Points become unavailable during FSx throughput capacity changes.

**Repository**: [github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns)

---

## Why Phase 14?

Phase 13 delivered the field-ready baseline. Phase 14 answers the question: **"Now that the patterns exist, how do we make them easier to evaluate, adopt, and operate?"**

The work falls into four categories:

1. **Partner/SI delivery acceleration** — one-pager, improved PoC templates, FC1-FC6 conversation starters
2. **Benchmark methodology** — standardized run IDs, hypothesis-driven testing, Range GET plans
3. **Compatibility clarification** — Presigned URL behavior confirmed with AWS Support
4. **Operational discovery** — S3 AP unavailability during throughput capacity changes

---

## 1. Partner/SI One-Pager: What / When / How / Where

Partners and SIs told us the existing 7-step delivery checklist was comprehensive but too long for a first conversation. Phase 14 adds a **single-page overview** that answers four questions:

| Section | Content |
|---------|---------|
| **What** | 17 UCs + 6 FC patterns, CloudFormation templates, 4-level maturity model |
| **When** | Customer has FSx ONTAP + needs serverless file processing + permission-aware access |
| **How** | Identify UC → Deploy template → Measure baseline → Evaluate Go/No-Go |
| **Where** | Links to Success Metrics, Governance, Production Readiness, Benchmarks |

Available in both [Japanese](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/blob/main/docs/partner-si-one-pager.md) and [English](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/blob/main/docs/partner-si-one-pager.en.md).

### FC1-FC6 Recommended First Questions

Each FlexCache/FlexClone pattern now has a **recommended first conversation question** — the question a Partner/SI should ask to determine if the pattern is relevant:

| Pattern | First Question |
|---------|---------------|
| FC1 (Anycast/DR) | "What is your current read latency from remote sites, and what target would justify a caching layer?" |
| FC2 (Render) | "How many concurrent render jobs share the same source data, and what is the job lifecycle?" |
| FC3 (RAG) | "Which file shares contain the knowledge base, and do access permissions need to be preserved in RAG results?" |
| FC4 (CAE) | "What is the typical solver output size and how quickly must results be available for post-processing?" |
| FC5 (Life Sciences) | "How do you currently share research datasets between teams while maintaining data governance?" |
| FC6 (Gaming) | "What is your current build pipeline duration and which asset validation steps are bottlenecks?" |

---

## 2. Presigned URLs: "Not Supported" but Working

> ⚠️ **Production Warning**: AWS Support explicitly states that operations marked "Not supported" should NOT be relied upon for production workloads, even when they return success today. The behavior may change without deprecation notice, return inconsistent results across regions, or stop working after service updates. **Design alternatives for any workflow that requires presigned URL access to FSx ONTAP S3 Access Points.**

### The Discovery

The [FSx for ONTAP S3 AP compatibility table](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html) lists `Presign — Not supported`. However, testing showed presigned URLs for GetObject work successfully.

### AWS Support Clarification

After raising this with AWS Support, the explanation was clear:

1. **Presigning is client-side only** — `aws s3 presign` computes a SigV4 signature locally. No network request is made.
2. **The presigned URL executes a standard GetObject** — signature is in query parameters instead of the Authorization header.
3. **Since GetObject is Supported, presigned URLs cannot be blocked** without breaking GetObject itself.
4. **The documentation likely intended** to indicate that presigned URL workflows are not officially tested.

### Production Guidance

| Feature | Status | Guidance |
|---------|--------|----------|
| GetObject, PutObject, ListObjectsV2 | **Supported** | Build on freely |
| Conditional writes (If-None-Match) | **Blocked** | Returns NotImplemented |
| Presigned URLs | **Not supported (doc)** | Works but do not rely on for production |

AWS Support has escalated documentation clarification to the FSx for ONTAP service team. The distinction between "Not supported + hard-blocked" (returns error) and "Not supported + may incidentally work" (no guarantees) is being reviewed.

---

## 3. Benchmark Methodology: Hypothesis-Driven Testing

### Why 1769 MB Lambda Memory?

Lambda memory directly controls CPU and network bandwidth allocation. At 1769 MB, Lambda receives exactly 1 vCPU equivalent, providing consistent and reproducible network throughput for benchmark measurements. Lower memory settings would introduce variable network bandwidth as a confounding factor.

### Benchmark Run ID Convention

Every benchmark run now follows a standardized format:

```
s3ap-bench-{YYYY-MM-DD}-{seq}
```

With mandatory fixed conditions:

```
Region: ap-northeast-1
Lambda memory: 1769 MB (1 vCPU)
Lambda architecture: arm64
FSx Throughput Capacity: [128 / 256 / 512] MBps
Iterations per data point: 50
Statistics: p50, p90, p95, p99, min, max
Concurrent NFS/SMB workload: [None / Light / Production-level]
```

### Hypothesis: Throughput Capacity vs Practical Concurrency Point

Based on 128 MBps observations where we observed concurrency=10 as the practical upper limit **in this specific test environment** (1 MB objects, single Lambda invocation pattern, no concurrent NFS/SMB workload), we hypothesize:

> **Practical concurrency point may shift with FSx throughput capacity increase.**

| FSx Capacity | Predicted Practical Concurrency | Rationale |
|-------------|-------------------------------|-----------|
| 128 MBps | 10 (observed) | Baseline — P99 exceeded 420 ms |
| 256 MBps | ~15-25 | Sub-linear scaling is plausible due to ONTAP WAFL overhead and TCP connection management |
| 512 MBps | ~25-45 | Step-function behavior possible if a different bottleneck emerges |

> **Note**: Linear scaling (2x capacity = 2x concurrency) is one possible outcome, but sub-linear or step-function behavior is equally plausible. The actual relationship depends on ONTAP data plane queuing, TCP connection overhead, and whether the bottleneck shifts from throughput to IOPS or latency at higher capacities.

Verification is blocked by the S3 AP issue described below. Results will be published when available, regardless of whether they confirm or reject the hypothesis.

---

## 4. Operational Discovery: S3 AP Unavailability During Throughput Changes

### What Happened

While preparing to run 256 MBps benchmarks, we changed the FSx throughput capacity from 128 to 256 MBps. After the change completed successfully:

- **All S3 Access Points** on the file system returned `ServiceUnavailable`
- **All SVMs** were affected (not just one)
- **Reverting to 128 MBps** did not immediately restore S3 AP access
- The file system itself remained `AVAILABLE` throughout

### Timeline

| Time | Event |
|------|-------|
| T+0 | `update-file-system` ThroughputCapacity 128 → 256 |
| T+25 min | Change completed (256 MBps confirmed) |
| T+25+ min | All S3 APs return ServiceUnavailable |
| T+40 min | Revert initiated (256 → 128) |
| T+65 min | Revert completed, S3 APs still unavailable |

### Impact and Recommendation

This is now tracked as an AWS Support case. Key takeaways:

> **Plan throughput capacity changes during maintenance windows. S3 AP workloads may be disrupted for an extended period.**

**Important context**: AWS documentation states that NFS/SMB access typically remains available during throughput capacity changes. The S3 AP disruption we observed appears to be specific to the S3 Access Point data plane — not the file system's NFS/SMB data LIFs. This distinction matters for environments that use both protocols.

**For regulated environments** (FISC, healthcare, government): Throughput capacity changes must be included in change management procedures. If S3 AP-based workloads have SLA requirements, the change should be approved through the organization's change advisory board with documented rollback procedures.

This finding has been added to the [Production Readiness](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/blob/main/docs/production-readiness.md) document as a Level 3+ operational consideration.

---

## 5. DEV.to Series Cleanup

Phase 14 also cleaned up the article series:

- **Update Notes** added to Phase 1, 9, 10, 12 articles linking to Phase 13
- **Permission-Aware RAG** articles moved to a separate series (was incorrectly mixed into FSx S3AP series)
- **Series now has 14 articles** in "FSx for ONTAP S3 Access Points" (down from 16 after RAG separation)

---

## 6. Community Engagement: AWS re:Post

To build toward Rising Star status (required for Article publishing on re:Post), we contributed answers to FSx for ONTAP questions:

- NFS mount troubleshooting (systematic 5-step guide)
- SVM deletion stuck in "Deleting" state
- Peer relationship blocking deletion
- NTFS volumes slow right-click (5 root causes)
- iSCSI LUN thin provisioning and space reporting
- IAM permissions for cross-account mounting
- iSCSI snapshot individual file restore (Japanese)
- Bedrock Agent KB parse failure workarounds
- S3 AP real-time sync options (S3 AP as alternative to DataSync)

---

## What's Blocked

| Item | Blocker | Resolution |
|------|---------|-----------|
| ~~256/512 MBps benchmark~~ | ~~S3 AP ServiceUnavailable~~ | ✅ **Resolved 2026-05-25** — Results below |
| FC1 Recovery Metrics | FlexCache × S3 AP integration | Pending AWS feature availability |
| ~~Hypothesis verification~~ | ~~Depends on benchmark~~ | ✅ **Partially confirmed** — see results |

---

## 7. Benchmark Results: 128 / 256 / 512 MBps Concurrency Comparison

S3 AP ServiceUnavailable was resolved on 2026-05-25. We immediately executed the planned benchmark across all three throughput tiers.

### Test Environment

| Parameter | Value |
|-----------|-------|
| Region | ap-northeast-1 (Tokyo) |
| FSx ONTAP | Single-AZ, First-generation |
| S3 AP | NetworkOrigin=Internet |
| Client | macOS, boto3, Python 3.9 (Internet) |
| Object sizes | 1 KB, 100 KB, 1 MB |
| Concurrency | 1, 5, 10, 20, 50 |
| Iterations | 10 per concurrency level |

### Key Results: 1 MB GetObject P99

| Concurrency | 128 MBps | 256 MBps | 512 MBps |
|:-----------:|:--------:|:--------:|:--------:|
| 1 | 76 ms | 93 ms | 96 ms |
| 5 | 160 ms | 175 ms | 308 ms |
| 10 | 239 ms | 236 ms | 229 ms |
| **20** | **981 ms** | **481 ms** | **738 ms** |
| 50 | — | 850 ms | 4,495 ms |

### Analysis

1. **P50 (median) is largely independent of throughput capacity** — Internet baseline latency (connection + TLS) dominates
2. **P99 (tail latency) shows the difference** — 128→256 MBps improved P99 by 51% at concurrency=20
3. **512 MBps shows no improvement over 256 MBps via Internet** — client-side bandwidth (~100 Mbps) becomes the bottleneck
4. **Hypothesis partially confirmed**: Practical concurrency point does shift with throughput capacity, but the relationship is non-linear and bounded by client bandwidth in Internet-origin tests

### Sizing Guidance

| Workload | 128 MBps | 256 MBps | 512 MBps |
|----------|:---:|:---:|:---:|
| Small files (< 10 KB) | MaxConcurrency=20 | 50 | 50 |
| Medium files (100 KB) | 10 | 20 | 50 |
| Large files (1 MB+) | 5 | 10 | 20 |

> These are sizing references from a specific test environment, not service limits. VPC-internal Lambda access will show significantly better throughput. Always validate with your own workload profile.

### What This Means for Production

- **For PoC (128 MBps)**: Keep Step Functions Map state MaxConcurrency ≤ 5 for 1 MB+ files
- **For Production (256+ MBps)**: MaxConcurrency=10-20 is safe for most workloads
- **For VPC-internal Lambda**: Expect 2-5x better throughput (Internet latency eliminated)
- **Throughput capacity changes**: Plan during maintenance windows (S3 AP disruption risk confirmed)

---

## What's Next (Phase 15 candidates)

1. **VPC-internal Lambda benchmark** — eliminate Internet latency to measure true FSx throughput impact
2. **FC1 Recovery Metrics** — route decision latency, cache health detection, failover timing
3. **FlexCache × S3 AP integration** — pending AWS feature availability
4. **Multi-Account OAM validation** — cross-account observability with 2nd AWS account
5. **Replay Storm real-data testing** — 1000/10000 FPolicy events with Persistent Store

---

## Stats

- **Files changed**: 200+ (documentation, translations, shared modules, templates)
- **New documents**: Partner/SI one-pager (JP/EN/KO/ZH-CN), cost calculator, customization guide, incident response playbook, demo mode guide, comparison alternatives, PoC Go/No-Go template
- **New shared modules**: `data_classification.py`, `human_review.py`, `schemas/events.py`
- **Benchmark runs**: 3 (128/256/512 MBps × concurrency 1-50)
- **Templates fixed**: 5 (cfn-lint errors: RecursiveDeleteOption, SNSPublishMessagePolicy, Handler path)
- **Translations added**: 20 files (FC1-FC6 ko/zh-CN + FC1/FC3 full 8-lang)
- **samconfig.toml.example**: 24 patterns
- **Output JSON samples**: 24 patterns
- **DEV.to articles updated**: 6 (4 Update Notes + 2 Series changes)
- **re:Post contributions**: 10 (1 question + 9 answers)
- **AWS Support cases**: 1 resolved (S3 AP ServiceUnavailable — throughput change related)
- **Operational discoveries**: 1 (throughput change → S3 AP disruption, now resolved)
- **Cost savings**: ~$187/month (v4-test-demo deletion + resource cleanup)

---

## Who Should Care About Phase 14?

- **Partners and SIs** get a one-pager for first conversations and recommended questions for each FC pattern
- **Operations teams** learn that throughput capacity changes can disrupt S3 AP access
- **Architects** get standardized benchmark methodology with hypothesis-driven testing
- **Developers** get Presigned URL clarification — works but don't depend on it
- **Community members** get detailed answers to common FSx ONTAP questions on re:Post

---

## What You Can Do Today

Even with benchmarks blocked, Phase 14 delivers immediately usable assets:

1. **Use the [Partner/SI one-pager](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/blob/main/docs/partner-si-one-pager.en.md)** for your next customer conversation about FSx ONTAP + serverless
2. **Check the [S3AP Compatibility Notes](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/blob/main/docs/s3ap-compatibility-notes.md)** for the latest Presigned URL and troubleshooting guidance
3. **Plan throughput changes carefully** — add S3 AP health checks to your maintenance runbook
4. **Ask questions on [re:Post](https://repost.aws/tags/TAibLc_0diRMaBeYxIBdlP2g/amazon-fsx-for-netapp-ontap)** — the FSx for ONTAP community is growing

---

**Repository**: [github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns)

**Full series**: [FSx for ONTAP S3 Access Points on DEV.to](https://dev.to/yoshikifujiwara/series/39652)

**Previous phases**: [Phase 1](https://dev.to/aws-builders/industry-specific-serverless-automation-patterns-with-fsx-for-ontap-s3-access-points-3e0a) · [Phase 7](https://dev.to/aws-builders/public-sector-use-cases-unified-output-destination-and-a-localization-batch-fsx-for-ontap-s3-2hmo) · [Phase 8](https://dev.to/aws-builders/operational-hardening-ci-grade-validation-and-pattern-c-b-hybrid-fsx-for-ontap-s3-access-587h) · [Phase 9](https://dev.to/aws-builders/production-rollout-vpc-endpoint-auto-detection-and-the-cdk-no-go-fsx-for-ontap-s3-access-3lni) · [Phase 10](https://dev.to/aws-builders/fpolicy-event-driven-pipeline-multi-account-stacksets-and-cost-optimization-fsx-for-ontap-s3-5bd6) · [Phase 11](https://dev.to/aws-builders/production-ready-fpolicy-event-pipeline-across-17-ucs-fsx-for-ontap-s3-access-points-phase-11-57p8) · [Phase 12](https://dev.to/aws-builders/operational-hardening-guardrails-secrets-rotation-slo-fsx-ontap-s3ap-phase-12-1k4o) · [Phase 13](https://dev.to/aws-builders/from-serverless-patterns-to-field-ready-reference-architecture-fsx-for-ontap-s3-access-points-dhj)
