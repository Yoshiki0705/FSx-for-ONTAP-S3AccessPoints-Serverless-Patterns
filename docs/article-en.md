---
title: "14 Industry-Specific Serverless Automation Patterns with FSx for ONTAP S3 Access Points"
published: true
description: "14 serverless patterns using FSx for ONTAP S3 Access Points with Lambda, Step Functions, and AI/ML services (Rekognition, Textract, Comprehend Medical, Bedrock, Athena) — all E2E verified in AWS ap-northeast-1 with cross-region support."
tags: aws, serverless, netapp, python
canonical_url: https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns
cover_image: https://raw.githubusercontent.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/main/docs/screenshots/masked/step-functions-all-succeeded.png
series: "FSx for ONTAP S3 Access Points"
---

## TL;DR

FSx for ONTAP S3 Access Points let you build **industry-specific serverless data pipelines** against NAS data — without moving files — using EventBridge Scheduler, Step Functions, and AWS AI/ML services. This article introduces **14 use-case patterns** (Phase 1: 5 UCs + Phase 2: 9 UCs) and 3 extension patterns, all backed by a [reference implementation repository](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns) with CloudFormation templates, shared Python modules, and property-based tests.

**Phase 2 highlights**:
- 9 new industry patterns (semiconductor, genomics, energy, autonomous driving, construction, retail, logistics, education, insurance)
- Cross-region support for Textract and Comprehend Medical (ap-northeast-1 → us-east-1)
- Streaming download and multipart upload for TB/PB-scale data
- All AI/ML services verified via Lambda E2E execution (Rekognition, Textract, Comprehend Medical, Bedrock, Athena)

This is a continuation of [FSx for ONTAP S3 Access Points as a Serverless Automation Boundary](https://dev.to/yoshikifujiwara/fsx-for-ontap-s3-access-points-as-a-serverless-automation-boundary-ai-data-pipelines-ili). While the previous article covered the operational automation layer, this one focuses on **concrete, reusable industry patterns** with full deployment instructions.

## Why Polling-Based? The S3 AP Constraint

S3 Access Points (hereafter **S3 AP**) expose ONTAP volume data through S3 APIs — `ListObjectsV2`, `GetObject`, `PutObject`, and others. However, `GetBucketNotificationConfiguration` is not supported, which means S3 event notifications (EventBridge / Lambda triggers) cannot be used.

This is why all patterns in this collection use **EventBridge Scheduler + Step Functions** for periodic polling:

```
EventBridge Scheduler (cron/rate)
  └─→ Step Functions State Machine
       ├─→ Discovery Lambda: List objects via S3 AP → Generate Manifest
       ├─→ Map State: Process each object with AI/ML services
       └─→ Report Lambda: Generate results → SNS notification
```

## Architecture: VPC Placement Optimization

A key design decision from verification: **only Lambda functions that need ONTAP REST API access are placed inside the VPC**. Lambda functions that only use S3 AP (with `internet` network origin) run outside the VPC.

```
┌─────────────────────────────────────────────────────┐
│ Inside VPC                                           │
│  - Discovery Lambda (ONTAP REST API + S3 AP)        │
│  - ACL Collection Lambda (ONTAP REST API)           │
│  → Requires VPC Endpoints for Secrets Manager / FSx │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ Outside VPC                                          │
│  - Processing Lambda (S3 AP + AI/ML services)       │
│  - Report Lambda (S3 + SNS + Bedrock)               │
│  → Direct access to S3 AP (internet origin)         │
│  → No VPC Endpoints needed — cost savings           │
└─────────────────────────────────────────────────────┘
```

**Benefits**: Interface VPC Endpoints (~$28.80/month) become unnecessary for most Lambda functions, cold start times improve (no ENI creation), and AI/ML services are accessed directly without NAT Gateway.

### Lambda Placement Guide

| Purpose | Recommended | Reason |
|---------|-------------|--------|
| Demo / PoC | Outside VPC | No VPC Endpoints needed, low cost |
| Production / private network | Inside VPC | Secrets Manager / FSx / SNS via PrivateLink |
| Athena / Glue use cases | S3 AP network origin: `internet` | AWS managed services need access |

### Network Origin Constraints

| Network Origin | Lambda (outside VPC) | Lambda (inside VPC) | Athena / Glue |
|---------------|---------------------|--------------------:|--------------|
| **internet** | ✅ | ✅ (via S3 Gateway EP) | ✅ |
| **VPC** | ❌ | ✅ (S3 Gateway EP required) | ❌ |

Athena and Glue access from AWS managed infrastructure, so they cannot reach VPC-origin S3 APs. Use cases requiring Athena (UC1, UC3) must use `internet` network origin.

## Security and Authorization Model

The solution uses four authorization layers:

| Layer | Role |
|-------|------|
| **IAM** | Controls access to AWS services and S3 Access Points |
| **S3 Access Point** | Defines access boundaries through the associated file system user |
| **ONTAP File System** | Enforces file-level permissions (UNIX / NTFS ACL) |
| **ONTAP REST API** | Exposes only metadata and control-plane operations |

Key points:
- S3 APIs do not expose file-level ACLs. File permissions are retrieved **exclusively via the ONTAP REST API** (UC1's ACL Collection uses this pattern)
- S3 AP access is authorized on the ONTAP side as the associated UNIX / Windows file system user, after IAM / S3 AP policy checks pass

## The 5 Use Cases

### UC1: Legal & Compliance — File Server Audit

Collects NTFS ACL information via ONTAP REST API, detects excessive permissions with Athena SQL, and generates natural-language compliance reports with Bedrock.

**Services**: Athena, Glue Data Catalog, Bedrock | **Verification**: ✅ E2E success (67/67 Lambda executions)

### UC2: Financial Services — Contract & Invoice Processing (IDP)

OCR processing of PDF/TIFF/JPEG documents with Textract, entity extraction with Comprehend, and structured summary generation with Bedrock.

**Services**: Textract, Comprehend, Bedrock | **Verification**: ✅ E2E success (Textract via cross-region invocation)

### UC3: Manufacturing — IoT Sensor Log & Quality Inspection

CSV sensor logs converted to Parquet for Athena anomaly detection. Inspection images analyzed with Rekognition for defect detection with confidence-based manual review flagging.

**Services**: Athena, Glue Data Catalog, Rekognition | **Verification**: ✅ E2E success

### UC4: Media — VFX Rendering Pipeline

Detects rendering assets, submits jobs to AWS Deadline Cloud, performs Rekognition quality checks, and writes approved output back to FSx ONTAP via S3 AP PutObject.

**Services**: Deadline Cloud, Rekognition | **Verification**: ✅ E2E success

### UC5: Healthcare — DICOM Image Classification & Anonymization

Parses DICOM metadata for classification, detects burned-in PII with Rekognition DetectText, and removes PHI with Comprehend Medical.

**Services**: Rekognition, Comprehend Medical | **Verification**: ✅ E2E success (Comprehend Medical via cross-region)

## Extension Patterns (Verified)

### Bedrock Knowledge Bases — RAG

S3 AP as a data source for Bedrock Knowledge Bases. Verified with OpenSearch Serverless + Titan Embed Text v2 (81 documents indexed, Retrieve and RetrieveAndGenerate APIs confirmed).

### Transfer Family SFTP — Partner File Exchange

SFTP server connected to S3 AP for external partner file exchange. Verified with SSH public key auth, upload/download operations.

### EMR Serverless Spark — Large-Scale Processing

PySpark jobs reading/writing via S3 AP. Verified CSV → Parquet transformation with script and data I/O entirely through S3 AP.

## Design Decisions

### Shared Modules

All use cases share `OntapClient` (Secrets Manager auth, urllib3, TLS, retry), `FsxHelper` (AWS FSx API + CloudWatch metrics), `S3ApHelper` (pagination, suffix filter), and `lambda_error_handler` decorator.

### Cost Optimization

High-cost always-on resources are opt-in via CloudFormation parameters:

| Resource | Monthly Cost | Default |
|----------|-------------|---------|
| Interface VPC Endpoints (4) | ~$28.80 | **Disabled** |
| CloudWatch Alarms | ~$0.10/alarm | **Disabled** |
| S3 Gateway VPC Endpoint | Free | **Enabled** |

Demo/PoC cost: **~$1–$3/month**. Actual verification cost for all 8 patterns: **under $2**.

### Three-Layer Error Handling

1. **Shared modules**: Custom exceptions + urllib3/boto3 retry
2. **Step Functions**: Retry/Catch blocks with exponential backoff
3. **Workflow**: Map State individual failures don't affect other items

### Cross-Region Invocation

Textract and Comprehend Medical are unavailable in some regions (e.g., ap-northeast-1). UC2 and UC5 use `TextractRegion` and `ComprehendMedicalRegion` CloudFormation parameters for cross-region API calls.

> **Note**: Cross-region invocation transfers data to another region. Verify data residency and compliance requirements.

## Issues Discovered During Verification

| # | Issue | Fix |
|---|-------|-----|
| 1 | `datetime` JSON serialization | Added `default=str` |
| 2 | Bedrock Messages API format | Updated to Messages API |
| 3 | Athena SQL quoting | Added backtick quoting |
| 4 | Lambda package name collision | Added UC prefix to ZIP names |
| 5 | S3 Gateway Endpoint duplication | Added `EnableS3GatewayEndpoint` parameter |
| 6 | VPC Lambda S3 AP timeout | Added `PrivateRouteTableIds` parameter |
| 7 | Textract region unavailability | Added `TextractRegion` cross-region parameter |
| 8 | ONTAP self-signed certificate | Added `VERIFY_SSL` environment variable |
| 9 | Single route table limitation | Changed to `CommaDelimitedList` type |
| 10 | Unnecessary VpcConfig | Removed VpcConfig from S3 AP-only Lambda |
| 11 | Comprehend Medical region | Added `ComprehendMedicalRegion` parameter |
| 12 | UC4 QualityCheck KeyError | Safe key access pattern |
| 13 | pyarrow Lambda layer size | Replaced with stdlib `csv` module |

## When to Use / When Not to Use

### Use this when:
- You want to serverlessly process existing NAS data on FSx for ONTAP without moving it
- You need file listing and preprocessing from Lambda without NFS/SMB mounts
- You want to learn the separation of responsibilities between S3 AP and ONTAP REST API
- You want to quickly validate industry-specific AI/ML patterns as a PoC

### Don't use this when:
- Real-time file change event processing is required (S3 Event Notification not supported)
- Full S3 bucket compatibility (Presigned URLs, etc.) is needed
- You already have EC2/ECS batch infrastructure with NFS mount operations
- File data already exists in standard S3 buckets

## Production Readiness Considerations

This repository includes production-oriented design decisions, but actual production environments should additionally consider:

- Organizational IAM / SCP / Permission Boundary alignment
- S3 AP policy and ONTAP-side user permission review
- Audit and execution logs (CloudTrail / CloudWatch Logs)
- CloudWatch Alarms / SNS / Incident Management integration
- Industry-specific compliance (data classification, PII, PHI)
- Data residency for cross-region invocations

## Getting Started

```bash
git clone https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns.git
cd FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns

pip install -r requirements.txt
pip install -r requirements-dev.txt
pytest shared/tests/ -v

# Package and deploy (example: UC1)
export AWS_DEFAULT_REGION=us-east-1
./scripts/deploy_uc.sh legal-compliance package
# Then deploy via CloudFormation — see README for full parameter list
```

The repository includes 8-language READMEs (ja, en, ko, zh-CN, zh-TW, fr, de, es), deployment guides, operations guides, troubleshooting guides, cost analysis, and region compatibility matrix.

---

**Repository**: [github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns)

**License**: MIT
