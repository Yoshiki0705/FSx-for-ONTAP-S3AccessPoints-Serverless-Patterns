---
title: "28 Industry Patterns: Full AWS Vertical Coverage with FSx for ONTAP S3 Access Points — Phase 15"
published: false
series: "FSx for ONTAP S3 Access Points"
tags: aws, serverless, amazonfsxfornetappontap, s3accesspoints
---

# 28 Industry Patterns: Full AWS Vertical Coverage with FSx for ONTAP S3 Access Points — Phase 15

## TL;DR

Phase 15 expands the pattern library from 17 to **28 industry-specific use cases**, covering every AWS Industry vertical plus Japan-market focus areas. Each new pattern includes a CloudFormation template, Step Functions workflow, Python Lambda functions, 8-language documentation, and property-based tests. Combined with 6 FlexCache/FlexClone patterns and 1 SAP/ERP pattern, the repository now offers **35 production-ready serverless patterns** for enterprise file processing on FSx for ONTAP.

**Repository**: [github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns)

---

## Why 28 Use Cases?

AWS organizes customers into 22 industry verticals. When we mapped our existing 17 patterns against these verticals, several gaps stood out:

- **Telecommunications** — No CDR/network log processing pattern
- **Advertising & Marketing** — No creative asset management
- **Travel & Hospitality** — No document processing for reservations
- **Agriculture & Food** — No traceability or crop monitoring
- **Sustainability/ESG** — No ESG metrics extraction
- **Nonprofit** — No grant management automation
- **Utilities** — No drone/SCADA-based asset inspection
- **Real Estate** — No portfolio analysis
- **HR** — No resume screening (with PII protection)
- **Chemicals** — No SDS/lab notebook processing
- **Transportation** (railway) — No deterioration detection

Phase 15 fills all of these, achieving **100% coverage** of AWS Industry verticals where FSx for ONTAP file processing is relevant.

---

## The 11 New Patterns

### P0: Foundation Patterns

| UC | Industry | Key AWS Services | Differentiator |
|----|----------|-----------------|----------------|
| UC18 | Telecom | Athena, Bedrock | CDR/syslog anomaly detection with 7-day baseline |
| UC19 | AdTech | Rekognition, Textract, Bedrock | Brand compliance scoring + moderation |

### P1: Document Intelligence

| UC | Industry | Key AWS Services | Differentiator |
|----|----------|-----------------|----------------|
| UC20 | Travel | Textract, Comprehend, Rekognition | Multilingual reservation extraction + facility inspection |
| UC21 | Agriculture | Rekognition, Textract, Bedrock | GeoTIFF crop analysis + lot traceability |
| UC22 | Transportation | Rekognition, Textract, Bedrock | Safety-critical thresholds (60%) + deterioration trends |

### P2: Specialized Processing

| UC | Industry | Key AWS Services | Differentiator |
|----|----------|-----------------|----------------|
| UC23 | Sustainability | Textract, Bedrock | ESG metric extraction + GRI/TCFD/ISSB mapping |
| UC24 | Nonprofit | Textract, Comprehend, Bedrock | Grant application + outcome matching |
| UC25 | Utilities | Rekognition, Bedrock, Athena | Drone + SCADA + thermal tri-modal inspection |
| UC26 | Real Estate | Rekognition, Textract, Bedrock | Property analysis + lease extraction + PII flagging |
| UC27 | HR | Textract, Comprehend, Bedrock | Resume screening with protected characteristic exclusion |
| UC28 | Chemicals | Textract, Rekognition, Bedrock | SDS hazard extraction + GHS compliance + lab notebook |

---

## Architecture: One Pattern, Many Industries

Every pattern follows the same proven architecture:

```
EventBridge Scheduler
       │
       ▼
Step Functions State Machine
       │
       ├── Discovery Lambda (VPC-internal, ONTAP API)
       │        │
       │        ▼
       │   S3 Access Point (list + classify files)
       │
       ├── Processing Map (parallel, Retry + Catch)
       │        │
       │        ▼
       │   [Rekognition | Textract | Comprehend | Bedrock | Athena]
       │
       └── Report Lambda
                │
                ├── Output → S3 AP (FSx ONTAP volume)
                └── SNS Notification
```

What changes per industry:
- **File prefixes and extensions** (Discovery Lambda configuration)
- **AI/ML service selection** (Rekognition for images, Textract for documents, Bedrock for reasoning)
- **Domain-specific schemas** (ESG metrics, GHS sections, CDR fields)
- **Confidence thresholds** (60% for safety-critical, 80% standard, 90% for human review)
- **Compliance requirements** (PII filtering for HR, data classification labels, audit trails)

---

## Shared Modules: The Productivity Multiplier

The 11 new patterns reuse the same `shared/` modules that power the original 17:

| Module | Purpose | Used By |
|--------|---------|---------|
| `s3ap_helper.py` | S3 Access Point abstraction (alias + ARN) | All 28 UCs |
| `exceptions.py` | Domain exceptions + error handler decorator | All 28 UCs |
| `observability.py` | EMF metrics + structured logging | All 28 UCs |
| `human_review.py` | Confidence-based review decisions | UC22, UC25, UC27 |
| `data_classification.py` | Output data labeling (INTERNAL/CUI/etc.) | UC23, UC24, UC27, UC28 |
| `schemas/events.py` | TypedDict event/response schemas | All 28 UCs |

Adding a new industry pattern takes **2-3 hours** (not days) because the infrastructure is already solved.

---

## Key Design Decisions for New Patterns

### 1. Safety-Critical Thresholds (UC22)

Railway infrastructure inspection cannot accept false negatives. We use a **dual-threshold** approach:

```python
STANDARD_THRESHOLD = 80       # General defect detection
SAFETY_CRITICAL_THRESHOLD = 60  # Bridges, signaling, rail joints
HUMAN_REVIEW_THRESHOLD = 90    # Auto-approve above this
```

Any detection between 60-90% for safety-critical categories triggers mandatory human review.

### 2. PII-First Design (UC27)

HR document screening handles personal data. The pattern enforces:

- **No PII in logs** — structured logging strips personal identifiers
- **Protected characteristic exclusion** — Bedrock prompt explicitly excludes age, gender, ethnicity
- **Encrypted output** — all results written with data classification labels
- **Audit trail** — every scoring decision is logged with justification (not content)

### 3. Tri-Modal Inspection (UC25)

Utilities asset inspection combines three data modalities in a single workflow:

1. **Visual** (drone images) → Rekognition defect detection
2. **Temporal** (SCADA logs) → Athena time-series anomaly detection
3. **Thermal** (FLIR images) → Hot-spot classification (≥10°C differential)

The Step Functions workflow processes all three in parallel Map states, then merges results for a unified maintenance priority report.

### 4. ESG Framework Mapping (UC23)

Sustainability reporting requires mapping extracted metrics to multiple frameworks simultaneously:

- **GRI** (Global Reporting Initiative)
- **TCFD** (Task Force on Climate-related Financial Disclosures)
- **ISSB** (International Sustainability Standards Board)

Bedrock performs the mapping using structured prompts with framework-specific indicator definitions.

---

## Testing: 1,499+ Tests Across 28 Patterns

Each new pattern includes:
- **Unit tests** with moto for AWS service mocking
- **Property-based tests** (Hypothesis) for invariant verification
- **cfn-lint validation** for all CloudFormation templates
- **ruff linting** for Python code quality

Notable property tests:
- UC22: `severity_level ∈ {critical, major, minor, observation}` for all inputs
- UC25: SCADA thresholds within physical bounds (voltage ±5%, frequency ±0.5 Hz)
- UC27: No protected characteristics appear in any output field
- UC28: All GHS mandatory sections validated for completeness

---

## Deployment: 30 Minutes to First Result

Every pattern includes a `samconfig.toml.example` and step-by-step deployment:

```bash
# 1. Copy and configure
cp samconfig.toml.example samconfig.toml
# Edit: S3AccessPointAlias, VpcId, SubnetIds, etc.

# 2. Deploy
sam build && sam deploy --guided

# 3. Execute
aws stepfunctions start-execution \
  --state-machine-arn <ARN from outputs>

# 4. Verify
aws stepfunctions describe-execution --execution-arn <ARN>
# Status: SUCCEEDED
```

For patterns without FSx for ONTAP, **DemoMode=true** uses a regular S3 bucket — ideal for evaluation without infrastructure commitment.

---

## Benchmark Insight: Small Files Don't Need More Throughput

During Phase 15 deployment verification, we ran benchmarks at 128/256/512 MBps throughput capacity with a 202-byte JSON manifest:

| Throughput | P50 @ conc=1 | P50 @ conc=25 | P50 @ conc=50 |
|:---:|:---:|:---:|:---:|
| 256 MBps | 56.9 ms | 60.3 ms | 257.9 ms |
| 512 MBps | 59.8 ms | 59.9 ms | 246.1 ms |

**Conclusion**: For metadata-heavy workloads (JSON manifests, small config files, document headers), throughput capacity increase has zero effect on latency. The bottleneck is connection overhead (TLS + S3 AP routing), not bandwidth. Save costs by staying at 128 MBps for these workloads.

> Sizing reference from a specific test environment, not a service limit.

---

## Documentation: 8 Languages × 28 Patterns

Every pattern includes documentation in:
🇯🇵 Japanese (primary) · 🇺🇸 English · 🇰🇷 Korean · 🇨🇳 Chinese (Simplified) · 🇹🇼 Chinese (Traditional) · 🇫🇷 French · 🇩🇪 German · 🇪🇸 Spanish

Each language includes:
- `README.md` — Overview, deployment, success metrics
- `docs/architecture.md` — Mermaid data flow diagram
- `docs/demo-guide.md` — Step-by-step demo with verification checklist

---

## What Changed Since Phase 14

| Metric | Phase 14 | Phase 15 | Delta |
|--------|:---:|:---:|:---:|
| Use cases | 17 | 28 | +11 |
| Total patterns | 24 | 35 | +11 |
| Test count | ~800 | 1,499+ | +699 |
| Industries covered | 14/22 | 20/22 | +6 |
| Languages | 8 | 8 | — |
| Shared modules | 8 | 11 | +3 |
| Documentation files | ~400 | ~700 | +300 |

---

## Who Should Use Each New Pattern?

| If you are... | Start with... | Why |
|---------------|---------------|-----|
| Telecom operator with CDR data | UC18 | Anomaly detection across network logs |
| Ad agency managing creative assets | UC19 | Automated brand compliance scoring |
| Hotel chain with inspection photos | UC20 | Facility condition monitoring at scale |
| Agricultural cooperative | UC21 | Crop health + traceability in one workflow |
| Railway/transit operator | UC22 | Safety-critical deterioration detection |
| ESG reporting team | UC23 | Multi-framework metric extraction |
| Grant-making foundation | UC24 | Application processing + outcome matching |
| Power utility with drone programs | UC25 | Tri-modal inspection (visual + SCADA + thermal) |
| Real estate portfolio manager | UC26 | Property analysis + lease extraction |
| Recruiting team (APAC/EMEA) | UC27 | PII-compliant resume screening |
| Chemical manufacturer | UC28 | SDS compliance + lab notebook digitization |

---

## What's Next

1. **VPC-internal Lambda benchmark** — True VPC path performance (eliminates Internet latency)
2. **FPolicy TCP-level Replay Storm** — Real ONTAP event replay (requires ECS rebuild)
3. **Cross-repository integration** — Link patterns to [fsxn-lakehouse-integrations](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations) for analytics pipelines
4. **Community contributions** — Pattern template for community-submitted industry use cases

---

## Stats

- **New patterns**: 11 (UC18-UC28)
- **New Lambda functions**: 44 (4 per pattern average)
- **New tests**: 699
- **New documentation files**: ~300 (across 8 languages)
- **New shared modules**: `data_classification.py`, `human_review.py`, `schemas/events.py`
- **Deployment verified**: All 28 UCs SUCCEEDED in ap-northeast-1
- **Benchmark runs**: 2 additional (256/512 MBps small-file comparison)
- **Cost**: ~$10 total for deployment verification (Lambda + Step Functions + Bedrock Nova Lite)

---

## Try It Today

```bash
git clone https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns.git
cd FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns

# Quick test (no AWS account needed)
make test-quick

# Deploy any pattern with DemoMode (no FSx ONTAP needed)
cd telecom-network-analytics
cp samconfig.toml.example samconfig.toml
sam build && sam deploy --guided
```

---

**Repository**: [github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns)

**Full series**: [FSx for ONTAP S3 Access Points on DEV.to](https://dev.to/yoshikifujiwara/series/39652)

**Previous phases**: [Phase 1](https://dev.to/aws-builders/industry-specific-serverless-automation-patterns-with-fsx-for-ontap-s3-access-points-3e0a) · [Phase 7](https://dev.to/aws-builders/public-sector-use-cases-unified-output-destination-and-a-localization-batch-fsx-for-ontap-s3-2hmo) · [Phase 8](https://dev.to/aws-builders/operational-hardening-ci-grade-validation-and-pattern-c-b-hybrid-fsx-for-ontap-s3-access-587h) · [Phase 9](https://dev.to/aws-builders/production-rollout-vpc-endpoint-auto-detection-and-the-cdk-no-go-fsx-for-ontap-s3-access-3lni) · [Phase 10](https://dev.to/aws-builders/fpolicy-event-driven-pipeline-multi-account-stacksets-and-cost-optimization-fsx-for-ontap-s3-5bd6) · [Phase 11](https://dev.to/aws-builders/production-ready-fpolicy-event-pipeline-across-17-ucs-fsx-for-ontap-s3-access-points-phase-11-57p8) · [Phase 12](https://dev.to/aws-builders/operational-hardening-guardrails-secrets-rotation-slo-fsx-ontap-s3ap-phase-12-1k4o) · [Phase 13](https://dev.to/aws-builders/from-serverless-patterns-to-field-ready-reference-architecture-fsx-for-ontap-s3-access-points-dhj) · [Phase 14](https://dev.to/yoshikifujiwara/evidence-expansion-presigned-url-discovery-and-operational-surprises-fsx-for-ontap-s3-access-points-phase-14-temp-slug-5765194)
