# Partner/SI One-Pager: FSx for ONTAP S3 Access Points Serverless Patterns

🌐 **Language / 言語**: [日本語](partner-si-one-pager.md) | [English](partner-si-one-pager.en.md)

---

## What — What This Repo Provides

| Item | Details |
|------|---------|
| Industry Use Cases | 17 UCs (Legal, Healthcare, Manufacturing, Public Sector, etc.) |
| FlexCache/FlexClone Patterns | 6 FCs (DR, Render, RAG, CAE, Life Sciences, Gaming) |
| Template Format | CloudFormation (SAM Transform) — independently deployable |
| Trigger Modes | POLLING (default) / EVENT_DRIVEN (FPolicy) / HYBRID |
| Maturity Model | 4 levels (Sandbox → Scheduled → Monitored → Production) |
| Testing | 1,499+ unit/property tests, cfn-lint, ruff validation |

## When — When to Use It

Propose to customers who match the following criteria:

- ✅ Have file data on FSx for ONTAP
- ✅ Need serverless automation over file data
- ✅ Need S3 API read/write access (GetObject, PutObject, ListObjectsV2, etc.)
- ✅ Require permission-aware processing (NTFS ACL / AD SIDs)
- ✅ Want to leverage AI/ML (Bedrock, Textract, Comprehend, Rekognition)
- ✅ Need event-driven or scheduled file processing automation

> **Note**: S3 Access Points are NOT read-only. PutObject (max 5 GB), DeleteObject, and MultipartUpload are supported. Constraints: FSX_ONTAP storage class only, SSE-FSX encryption only. See [S3AP Compatibility Notes](s3ap-compatibility-notes.md) for details.

## How — How to Run a PoC

```
Step 1: Identify closest UC → Check Success Metrics
Step 2: Deploy template → Verify S3AP access
Step 3: Measure Customer-Specific Baseline
Step 4: Evaluate against Go/No-Go criteria
```

**Estimated time**:
- Level 1 (Sandbox): 1-2 hours
- Level 2 (Scheduled): 1-2 days
- Level 3 (Monitored): 1-2 weeks

**Detailed steps**: [Partner/SI Delivery Checklist](partner-si-delivery-checklist.md)

## Where — Where to Find Key Resources

| Resource | Path |
|----------|------|
| Success Metrics | Each UC's README.md |
| Governance | [docs/governance-checklist.md](governance-checklist.md) |
| Production Readiness | [docs/production-readiness.md](production-readiness.md) |
| Benchmark Data | [docs/s3ap-benchmark-results.md](s3ap-benchmark-results.md) |
| Customer Discovery | [docs/customer-discovery-template.md](customer-discovery-template.md) |
| Trigger Selection | [docs/trigger-mode-decision-guide.md](trigger-mode-decision-guide.md) |
| Public Sector | [docs/public-sector-adoption-roadmap.md](public-sector-adoption-roadmap.md) |
| Workshop | [docs/workshop-guide.md](workshop-guide.md) |

---

> **Note**: This repository is a reference implementation for learning design decisions. Production adoption requires customer-specific security review, compliance assessment, and performance validation.
