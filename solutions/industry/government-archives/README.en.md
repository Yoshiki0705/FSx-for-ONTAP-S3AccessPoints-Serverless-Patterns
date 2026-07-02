# UC16: Government Agencies — Public Records Digital Archive & FOIA Response

🌐 **Language / 言語**: [日本語](README.md) | English | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)
📚 **Documentation**: [Architecture](docs/architecture.md) | [Demo Script](docs/demo-guide.md) | [Troubleshooting](../docs/phase7-troubleshooting.md)

## Overview

An automated pipeline for government public records digital archiving and
Freedom of Information Act (FOIA) response, built on
FSx for ONTAP S3 Access Points.

## Use Case

Automatically digitize, classify, and redact the large volume of public
records (PDF, scanned images, email) held by government agencies, and
respond quickly to Freedom of Information Act requests.

### Processing Flow

```
FSx for ONTAP (Public records storage — per-department NTFS ACL)
  → S3 Access Point
    → Step Functions workflow
      → Discovery: Detect new documents (PDF, TIFF, EML, MSG)
      → OCR: Document digitization with Textract (cross-region because ap-northeast-1 is not supported)
      → Classification: Document classification with Comprehend (sensitivity level determination)
      → EntityExtraction: PII detection (name, address, SSN, phone number)
      → Redaction: Automatic redaction of sensitive information
      → IndexGeneration: Full-text search index generation (OpenSearch, can be disabled)
      → ComplianceCheck: Retention period / disposition schedule check (NARA GRS)
```

### Target Data

| Data format | Description | Typical size |
|-----------|------|-----------|
| PDF | Public records, reports, contracts | 100 KB – 50 MB |
| TIFF | Scanned documents | 1 – 100 MB |
| EML / MSG | Email archives | 10 KB – 10 MB |
| DOCX / XLSX | Office documents | 50 KB – 20 MB |

### AWS Services

| Service | Purpose |
|---------|------|
| FSx for ONTAP | Persistent storage for public records (per-department NTFS ACL) |
| S3 Access Points | Document access from serverless |
| Step Functions | Workflow orchestration |
| Lambda | Document classification, PII detection, redaction |
| Amazon Textract ⚠️ | Document OCR (cross-region via us-east-1) |
| Amazon Comprehend | Entity extraction, document classification, PII detection |
| Amazon Bedrock | Document summarization, FOIA response draft generation |
| Amazon Macie | Automatic sensitive-data detection |
| DynamoDB | Document metadata, processing-state management |
| OpenSearch Serverless | Full-text search index (optional, disabled by default) |
| SNS | FOIA deadline alerts |

### Public Sector Suitability

- **NARA (National Archives and Records Administration) compliance**: Meets electronic records management requirements
- **FOIA response**: Automatically tracks the 20 business-day response deadline
- **FedRAMP High**: Compliant on AWS GovCloud
- **Section 508**: Accessibility support (OCR + alternative text generation)
- **Records Management**: Automatic management of retention periods and disposition schedules

### FOIA Response Flow

```
FOIA request received
  → Search target documents (OpenSearch)
  → Sensitivity level determination for matching documents
  → Automatic redaction (PII, national security information)
  → Notification to reviewers
  → Response deadline tracking (20 business days)
  → Public document package generation
```

## Verified Screens (Screenshots)

### 1. Storing public records (via S3 Access Point)

After a FOIA request is received, the target documents are stored under the `archives/YYYY/MM/` prefix.

<!-- SCREENSHOT: phase7-uc16-s3-archives-uploaded.png
     Content: List of PDF documents under the archives/ prefix on the S3 AP
     Mask: account ID, S3 AP ARN, document names -->
![UC16: Confirming stored public records](../docs/screenshots/masked/phase7/phase7-uc16-s3-archives-uploaded.png)

### 2. Viewing redacted documents

Text stored under the `redacted/` prefix after processing, where PII has been
replaced with the `[REDACTED]` marker. **The screen that general staff review before publication.**

<!-- SCREENSHOT: phase7-uc16-redacted-text-preview.png
     Content: Redacted text preview in the S3 console, [REDACTED] markers visible
     Mask: account ID, redacted document names (sample names only) -->
![UC16: Redacted document preview](../docs/screenshots/masked/phase7/phase7-uc16-redacted-text-preview.png)

### 3. Redaction metadata (sidecar JSON)

Sidecar data for auditing. Original PII is not stored — only SHA-256 hashes.
Offsets, entity types (NAME / EMAIL / SSN, etc.), and confidence are recorded.

<!-- SCREENSHOT: phase7-uc16-redaction-metadata-json.png
     Content: Formatted view of redaction-metadata/*.json
     Mask: account ID, original document names -->
![UC16: Redaction metadata JSON](../docs/screenshots/masked/phase7/phase7-uc16-redaction-metadata-json.png)

### 4. FOIA deadline reminder (SNS email notification)

Reminder email that FOIA officers receive 3 business days before the deadline.
When overdue, an OVERDUE notification with severity=HIGH.

<!-- SCREENSHOT: phase7-uc16-foia-reminder-email.png
     Content: FOIA_DEADLINE_APPROACHING email shown in an email client
     Mask: recipient/sender emails, request_id (sample ID only) -->
![UC16: FOIA deadline reminder email](../docs/screenshots/masked/phase7/phase7-uc16-foia-reminder-email.png)

### 5. NARA GRS retention schedule (DynamoDB Explorer)

The `fsxn-uc16-demo-retention` table. For each document, the NARA GRS code
(GRS 2.1 / 2.2 / 1.1), retention years (3 / 7 / 30 years), and scheduled disposition date are recorded.

<!-- SCREENSHOT: phase7-uc16-dynamodb-retention.png
     Content: List of items in the retention table in DynamoDB Explorer
     Mask: account ID, document_key (sample names only) -->
![UC16: Retention schedule table](../docs/screenshots/masked/phase7/phase7-uc16-dynamodb-retention.png)


## Success Metrics

### Outcome
Speed up Freedom of Information Act response by automating public records archiving and FOIA handling (OCR, classification, redaction, retention-deadline management).

### Metrics
| Metric | Target (example) |
|-----------|------------|
| Documents processed / run | > 500 documents |
| OCR text extraction success rate | > 95% |
| PII detection accuracy | > 95% |
| Redaction time / document | < 30 seconds |
| Reduction in FOIA response time | > 50% |
| Human Review mandatory rate | 100% (all redaction results require human confirmation) |

> **Why 100% Human Review**: Because a missed redaction directly affects information disclosure and personal-data protection, human confirmation of every item is mandatory.

### Measurement Method
Step Functions execution history, Comprehend PII detection results, before/after redaction diff, DynamoDB retention history, CloudWatch Metrics. Review results are recorded in DynamoDB so that, during audits, "who confirmed/approved what and when" can be traced.

### Sample Run Results (measured example)

**Environment**: FSx for ONTAP Single-AZ, 128 MBps, ap-northeast-1, S3AP Internet Origin

| Indicator | Before (manual) | After (S3AP automation) |
|------|-------------|-------------------|
| FOIA response time | Days to weeks | 389 ms (10 docs, sequential) |
| Document discovery | Manual search | 32 ms (10 documents) |
| File read | Individual access | avg 36 ms / document |
| Redaction quality | Depends on staff, inconsistent | Comprehend PII detection + automatic redaction |
| Human Review | None or irregular | 100% (all items require human confirmation) |
| Audit trail | Personal records | DynamoDB (who/when/what) + S3 Object Lock |
| Retention management | Manual | Automatic tracking + alerts |

> **Note**: The UC16 sample run is a validation using synthetic or non-sensitive sample documents and does not represent actual government records or production data. This sample run validates only the processing path. Redaction quality, completeness of Human Review, and audit-trail evaluation should be conducted separately in a customer-specific PoC.

## Deployment

### Pre-validation

```bash
bash scripts/verify_phase7_prerequisites.sh
```

### One-shot deploy

```bash
bash scripts/deploy_phase7.sh government-archives
```

### Manual deploy

```bash
# Prerequisite: AWS SAM CLI is required. sam build automatically packages the code and shared layer.
sam build

sam deploy \
  --stack-name fsxn-gov-archives \
  --parameter-overrides \
    S3AccessPointAlias=<alias> \
    S3AccessPointName=<name> \
    OpenSearchMode=none \
    CrossRegion=us-east-1 \
    UseCrossRegion=true \
    OntapSecretName=<secret> \
    OntapManagementIp=<ip> \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3
```

### OpenSearch modes

| Mode | Purpose | Monthly cost (estimate) |
|--------|------|-------------------|
| `none` | Validation / low-cost operation (default) | $0 |
| `serverless` | Variable workloads, pay-as-you-go | $350 – $700 |
| `managed` | Fixed workloads, low cost | $35 – $100 |

## Directory Layout

```
government-archives/
├── template.yaml
├── template-deploy.yaml
├── functions/
│   ├── discovery/handler.py
│   ├── ocr/handler.py                # Cross-region Textract
│   ├── classification/handler.py
│   ├── entity_extraction/handler.py
│   ├── redaction/handler.py
│   ├── index_generation/handler.py
│   ├── compliance_check/handler.py   # NARA GRS retention period
│   └── foia_deadline_reminder/handler.py  # 20 business-day tracking
├── tests/                            # 52 pytest (incl. Hypothesis)
└── README.md
```


---

## AWS Documentation Links

| Service | Documentation |
|---------|------------|
| FSx for ONTAP | [User Guide](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/what-is-fsx-ontap.html) |
| S3 Access Points | [S3 AP for FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html) |
| Step Functions | [Developer Guide](https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html) |
| Amazon Textract | [Developer Guide](https://docs.aws.amazon.com/textract/latest/dg/what-is.html) |
| Amazon Comprehend | [Developer Guide](https://docs.aws.amazon.com/comprehend/latest/dg/what-is.html) |
| Amazon Macie | [User Guide](https://docs.aws.amazon.com/macie/latest/user/what-is-macie.html) |
| Amazon OpenSearch | [Developer Guide](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/what-is.html) |

### Well-Architected Framework Alignment

| Pillar | Alignment |
|----|------|
| Operational Excellence | X-Ray, EMF, FOIA deadline tracking, 52+ tests |
| Security | PII redaction, SHA-256 audit sidecar, Macie, 100% Human Review |
| Reliability | Step Functions Retry/Catch, cross-region OCR, resilience tests |
| Performance Efficiency | Parallel PII detection, OpenSearch index, batch processing |
| Cost Optimization | Serverless, OpenSearch Serverless, conditional indexing |
| Sustainability | NARA GRS compliance, retention management, automatic disposition schedule |





---

## Cost Estimate (Monthly Approximate)

> **Note**: The following are approximate figures for the ap-northeast-1 region; actual costs vary by usage. Check the latest pricing at [AWS Pricing Calculator](https://calculator.aws/).

### Serverless components (pay-as-you-go)

| Service | Unit price | Assumed usage | Monthly approx. |
|---------|------|-----------|---------|
| Lambda | $0.0000166667/GB-sec | 8 functions × 100 docs/day | ~$1-5 |
| S3 API (GetObject/ListObjects) | $0.0047/10K requests | ~10K requests/day | ~$1.5 |
| Step Functions | $0.025/1K state transitions | ~1K transitions/day | ~$0.75 |
| Bedrock (Nova Lite) | $0.00006/1K input tokens | ~80K tokens/run | ~$3-10 |
| Athena | $5/TB scanned | ~50 MB/query | ~$0.5-2 |
| SNS | $0.50/100K notifications | ~100 notifications/day | ~$0.15 |
| CloudWatch Logs | $0.76/GB ingested | ~1 GB/month | ~$0.76 |
| OpenSearch Serverless | $0.24/OCU-hour |


### Fixed cost (FSx for ONTAP — assumes existing environment)

| Component | Monthly |
|--------------|------|
| FSx for ONTAP (128 MBps, 1 TB) | ~$230 (shares existing environment) |
| S3 Access Point | No additional charge (S3 API charges only) |

### Total estimate

| Configuration | Monthly approx. |
|------|---------|
| Minimal (once daily) | ~$5-15 |
| Standard (hourly) | ~$15-50 |
| Large-scale (high frequency + alarms) | ~$50-150 |

> **Governance Caveat**: Cost estimates are approximate and not guaranteed. Actual billing varies by usage pattern, data volume, and region.

---

## Local Testing

### Prerequisites check

```bash
# Check prerequisites
aws --version          # AWS CLI v2
sam --version          # SAM CLI
python3 --version      # Python 3.9+
docker --version       # Docker (for sam local)
aws sts get-caller-identity  # AWS credentials
```

### sam local invoke

```bash
# Build
# Prerequisite: AWS SAM CLI is required. sam build automatically packages the code and shared layer.
sam build

# Run Discovery Lambda locally
sam local invoke DiscoveryFunction --event events/discovery-event.json

# With environment variable overrides
sam local invoke DiscoveryFunction \
  --event events/discovery-event.json \
  --env-vars env.json
```

### Unit tests

```bash
python3 -m pytest tests/ -v
```

For details, see [Local Testing Quick Start](../docs/local-testing-quick-start.md).

---

## Output Sample

Example output of public records archiving / FOIA processing:

```json
{
  "discovery": {
    "status": "completed",
    "object_count": 25,
    "prefix": "archives/incoming/"
  },
  "classification": [
    {
      "key": "archives/incoming/memo-2026-001.pdf",
      "record_type": "memorandum",
      "retention_schedule": "GRS 5.2 - 7 years",
      "sensitivity": "CUI",
      "pii_detected": true
    }
  ],
  "redaction": {
    "total_redacted": 25,
    "pii_fields_removed": 89,
    "redaction_types": {"name": 34, "ssn": 12, "address": 28, "phone": 15},
    "audit_hash": "sha256:d4e5f6..."
  },
  "foia_tracking": {
    "request_id": "FOIA-2026-0042",
    "deadline_date": "2026-06-12",
    "business_days_remaining": 15,
    "status": "IN_PROCESSING"
  },
  "search_index": {
    "documents_indexed": 25,
    "opensearch_collection": "gov-archives-collection"
  }
}
```

> **Note**: The above is sample output; actual values vary by environment and input data. Benchmark figures are a sizing reference, not a service limit.

---

## Governance Note

> This pattern provides technical architecture guidance. It is not legal, compliance, or regulatory advice. Organizations should consult qualified professionals.

---

## S3AP Compatibility

For compatibility constraints, troubleshooting, and trigger patterns for S3 Access Points for FSx for ONTAP, see [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).
