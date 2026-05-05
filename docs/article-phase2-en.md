---
title: "9 More Industry Serverless Patterns with FSx for ONTAP S3 Access Points — Semiconductor, Genomics, Energy, and Beyond"
published: true
description: "Phase 2: 9 new serverless automation patterns for semiconductor EDA, genomics, energy exploration, autonomous driving, construction BIM, retail, logistics, education, and insurance — with cross-region AI/ML support and E2E verification."
tags: aws, serverless, netapp, python
canonical_url: https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns
cover_image: https://raw.githubusercontent.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/main/docs/screenshots/masked/step-functions-phase2-all-workflows.png
series: "FSx for ONTAP S3 Access Points"
---

## TL;DR

This is **Phase 2** of the FSx for ONTAP S3 Access Points serverless patterns collection. Building on the [5 patterns from Phase 1](https://dev.to/yoshikifujiwara/industry-specific-serverless-automation-patterns-with-fsx-for-ontap-s3-access-points-4a5g), we add **9 new industry-specific patterns** covering semiconductor, genomics, energy, autonomous driving, construction, retail, logistics, education, and insurance.

Key additions:
- **Cross-region AI/ML**: Textract and Comprehend Medical routed from ap-northeast-1 to us-east-1
- **Large-scale data support**: Streaming download, multipart upload, 10K+ object pagination
- **All services E2E verified**: Rekognition (15 labels), Textract (text extraction), Comprehend Medical (entity detection), Bedrock (report generation), Athena (SQL queries)
- **9 CloudFormation stacks deployed**: 205 resources, all Step Functions SUCCEEDED

**Repository**: [github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns)

---

## What's New in Phase 2

### Cross-Region Client

Textract and Comprehend Medical are unavailable in ap-northeast-1 (Tokyo). Phase 2 introduces a `CrossRegionClient` that transparently routes API calls to us-east-1:

```python
from shared.cross_region_client import CrossRegionClient, CrossRegionConfig

config = CrossRegionConfig(
    target_region="us-east-1",
    services=["textract", "comprehendmedical"]
)
client = CrossRegionClient(config)

# Textract in us-east-1
result = client.analyze_document(document_bytes=pdf_bytes)

# Comprehend Medical in us-east-1
entities = client.detect_entities_v2(text=medical_text)
```

The client includes an allow-list to prevent accidental cross-region calls to unintended services, and raises `CrossRegionClientError` with region and service context for debugging.

### Streaming Download & Multipart Upload

Phase 2 use cases handle TB/PB-scale data. The `S3ApHelper` now supports:

```python
# Streaming download — never loads entire file into memory
for chunk in s3ap.streaming_download(key="large-file.segy", chunk_size=256*1024):
    process(chunk)

# Range download — read only SEG-Y header (first 3600 bytes)
header = s3ap.streaming_download_range(key="survey.segy", start=0, end=3599)

# Multipart upload — automatic abort on failure
s3ap.multipart_upload(key="output.parquet", data_chunks=chunks, part_size=5*1024*1024)
```

### Discovery Lambda Pagination

For volumes with 10,000+ objects, Discovery Lambda automatically paginates manifests into chunks for Step Functions Distributed Map processing.

---

## The 9 New Use Cases

### UC6: Semiconductor / EDA — Design File Validation

Detects GDS/OASIS design files, extracts metadata (library name, cell count, bounding box, creation date), aggregates DRC statistics with Athena SQL, and generates design review reports with Bedrock.

```
Discovery → Map(MetadataExtraction) → DrcAggregation(Athena) → ReportGeneration(Bedrock + SNS)
```

**Services**: Athena, Glue Data Catalog, Bedrock (Nova Lite)
**Verification**: ✅ GDS metadata extracted, Athena 4 queries succeeded, Bedrock report generated

### UC7: Genomics / Bioinformatics — Quality Check & Variant Aggregation

Processes FASTQ files for quality metrics (total reads, average quality score, GC content), aggregates VCF variant statistics (SNP count, indel count, Ti/Tv ratio), and generates research summaries with biomedical entity extraction.

```
Discovery → Parallel[QcMap(FASTQ), VariantMap(VCF)] → AthenaAnalysis → Summary(Bedrock + Comprehend Medical)
```

**Services**: Athena, Bedrock, Comprehend Medical (cross-region us-east-1)
**Verification**: ✅ QC metrics extracted, variants aggregated, Comprehend Medical entities detected (genes: ["GC"])

### UC8: Energy / Oil & Gas — Seismic Data Processing

Reads SEG-Y binary headers (first 3600 bytes via range download) for survey metadata, detects anomalies in well log sensor readings using statistical thresholds, and generates compliance reports.

```
Discovery → Parallel[SeismicMetadata(Range DL), AnomalyDetection(Well Logs)] → AthenaAnalysis → ComplianceReport(Bedrock)
```

**Services**: Athena, Bedrock, Rekognition
**Verification**: ✅ SEG-Y header parsed, anomaly detection executed

### UC9: Autonomous Driving / ADAS — Labeling Preprocessing

Extracts keyframes from dashcam video, performs Rekognition object detection (vehicles, pedestrians, traffic signs), validates LiDAR point cloud data integrity, and generates COCO-compatible annotation suggestions with Bedrock.

```
Discovery → Parallel[FrameExtraction(Rekognition), PointCloudQC] → AnnotationManager(Bedrock)
```

**Services**: Rekognition, Bedrock, SageMaker (optional)
**Verification**: ✅ Step Functions SUCCEEDED

### UC10: Construction / AEC — BIM Model Management

Parses IFC files for building metadata, performs version diff detection, OCRs blueprint PDFs with Textract (cross-region), and checks safety compliance rules with Bedrock + Rekognition.

```
Discovery → Parallel[BimParse(IFC), OcrMap(Textract)] → SafetyCheck(Bedrock + Rekognition)
```

**Services**: Textract (cross-region), Bedrock, Rekognition
**Verification**: ✅ Textract text extraction confirmed

### UC11: Retail / E-Commerce — Product Image Tagging

Detects product images, performs Rekognition label detection with confidence scoring, generates structured catalog metadata with Bedrock, and flags low-quality images for manual review.

```
Discovery → ImageTagging(Rekognition) → CatalogMetadata(Bedrock) → QualityCheck
```

**Services**: Rekognition, Bedrock
**Verification**: ✅ **15 labels detected** (Lighting 98.5%, Light 96.0%, Purple 92.0%)

### UC12: Logistics / Supply Chain — Delivery Slip OCR

OCRs delivery slips with Textract (cross-region), normalizes extracted fields with Bedrock, analyzes warehouse inventory images with Rekognition, and generates route optimization reports.

```
Discovery → Parallel[OcrMap(Textract), InventoryMap(Rekognition)] → DataStructuring(Bedrock) → Report(Bedrock + SNS)
```

**Services**: Textract (cross-region), Rekognition, Bedrock
**Verification**: ✅ **"Hello World" extracted from PDF**, inventory analysis completed

### UC13: Education / Research — Paper Classification

OCRs research PDFs with Textract (cross-region), classifies topics with Comprehend, builds citation networks from reference sections, and generates structured metadata.

```
Discovery → OcrMap(Textract) → Classification(Comprehend + Bedrock) → CitationAnalysis → Metadata
```

**Services**: Textract (cross-region), Comprehend, Bedrock
**Verification**: ✅ Step Functions SUCCEEDED

### UC14: Insurance / Claims — Damage Assessment

Detects accident photos and estimate documents, performs Rekognition damage assessment with severity scoring, OCRs estimates with Textract (cross-region), and generates comprehensive claims reports correlating photo evidence with estimate data.

```
Discovery → Parallel[DamageAssessment(Rekognition), EstimateOcr(Textract)] → ClaimsReport(Bedrock + SNS)
```

**Services**: Rekognition, Textract (cross-region), Bedrock
**Verification**: ✅ **Rekognition labels detected + Textract "Delivery Slip - Tracking: TRK-2026-001234" extracted**

---

## AI/ML Service Verification Results

All services were verified via **Lambda E2E execution** (not just direct API calls):

| Service | UC | Result |
|---------|-----|--------|
| Rekognition DetectLabels | UC11 | ✅ 15 labels (Lighting 98.5%) |
| Rekognition DetectLabels | UC14 | ✅ damage_assessment with labels |
| Textract DetectDocumentText | UC12 | ✅ "Hello World" from PDF |
| Textract DetectDocumentText | UC14 | ✅ "Delivery Slip - Tracking: TRK-2026-001234" |
| Comprehend Medical DetectEntitiesV2 | UC7 | ✅ genes: ["GC"] |
| Bedrock InvokeModel (Nova Lite) | UC6 | ✅ Design review report generated |
| Athena StartQueryExecution | UC6 | ✅ 4 queries (cell_count, bbox, naming, invalid) |

---

## Design Decisions

### File-Type Classification in Discovery Lambda

Each UC's Discovery Lambda classifies detected files by type and returns UC-specific keys matching the Step Functions Map `ItemsPath`:

```python
# UC7 Genomics Discovery returns:
return {
    "objects": all_objects,          # All detected files
    "fastq_objects": fastq_files,   # → QcMap ItemsPath
    "vcf_objects": vcf_files,       # → VariantMap ItemsPath
    "metadata": ontap_metadata,
}
```

This allows Step Functions to route different file types to different processing branches without additional Lambda invocations.

### IAM Policy for S3 Access Points

FSx ONTAP S3 Access Points require **two ARN formats** in IAM policies:

```yaml
# Both formats are needed
Resource:
  - !Sub "arn:aws:s3:::${S3AccessPointAlias}"        # Alias format (S3 API)
  - !Sub "arn:aws:s3:::${S3AccessPointAlias}/*"
  - !Sub "arn:aws:s3:${AWS::Region}:${AWS::AccountId}:accesspoint/${S3AccessPointName}"  # ARN format (IAM evaluation)
  - !Sub "arn:aws:s3:${AWS::Region}:${AWS::AccountId}:accesspoint/${S3AccessPointName}/*"
```

### VPC Endpoints for Discovery Lambda

Discovery Lambda runs inside the VPC (for ONTAP REST API access) and needs these endpoints:

| Endpoint | Type | Cost |
|----------|------|------|
| Secrets Manager | Interface | ~$7.20/mo |
| FSx | Interface | ~$7.20/mo |
| CloudWatch Monitoring | Interface | ~$7.20/mo |
| CloudWatch Logs | Interface | ~$7.20/mo |
| S3 | Gateway | **Free** |

**Key lesson**: The `monitoring` endpoint is for CloudWatch Metrics, not Logs. You need a separate `logs` endpoint for Lambda to write CloudWatch Logs from inside a VPC.

### boto3 Service Name Gotcha

The correct boto3 service name for Comprehend Medical is `comprehendmedical` (no hyphen), not `comprehend-medical`. This caused silent failures in early testing where the service was skipped with a WARNING rather than crashing the workflow.

---

## Issues Discovered During Phase 2 Verification

| # | Issue | Root Cause | Fix |
|---|-------|-----------|-----|
| 1 | Discovery Lambda timeout (300s) | Public subnet + no VPC Endpoints | Private subnet + VPC Endpoints |
| 2 | S3 AP AccessDenied | IAM policy missing ARN format | Both Alias + ARN formats |
| 3 | Athena RLIKE syntax error | Athena (Trino) doesn't support RLIKE | Use `REGEXP_LIKE()` |
| 4 | Missing CloudWatch Logs endpoint | `monitoring` ≠ `logs` | Added separate Logs endpoint |
| 5 | Step Functions ItemsPath mismatch | Discovery returns `objects` but SFN expects `fastq_objects` | Added file-type classification |
| 6 | Comprehend Medical service name | `comprehend-medical` is invalid | Use `comprehendmedical` |
| 7 | Rekognition InvalidImageFormat | 284-byte invalid JPEG | Valid 200x200 PNG (56KB) |
| 8 | Processing Lambda S3 AP AccessDenied | Only Discovery role had S3 AP permissions | Added to all Processing roles |

---

## Deployment

### Quick Start (Batch Deploy)

```bash
git clone https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns.git
cd FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns

# Generate deployment templates
./scripts/regenerate_deploy_templates.sh

# Package all Lambda functions
./scripts/deploy_phase2_batch.sh package

# Deploy all 9 stacks
./scripts/deploy_phase2_batch.sh deploy

# Check status
./scripts/deploy_phase2_batch.sh status
```

### Test Data

```bash
# Generate and upload test data (GDS, FASTQ, VCF, SEG-Y, IFC, PNG, PDF)
export S3_AP_ALIAS="<your-s3-ap-alias>"
python3 scripts/generate_test_data.py all --upload
```

### Verify shared/ modules

```bash
python3 docs/verification-scripts/verify_phase2_shared.py \
  --s3-ap-alias "<your-s3-ap-alias>" \
  --output-bucket "<your-output-bucket>"
# Result: 8/8 PASSED
```

---

## Cost

Phase 2 uses the same cost-optimized architecture as Phase 1:

| Environment | Fixed/mo | Variable/mo | Total/mo |
|-------------|----------|-------------|----------|
| Demo/PoC | ~$0 | ~$1–$3 | **~$1–$3** |
| Production (1 UC) | ~$36 | ~$1–$3 | **~$37–$39** |
| Production (all 14 UCs) | ~$36 | ~$14–$42 | **~$50–$78** |

VPC Endpoints are shared across all UCs in the same VPC — deploy the first UC with `EnableVpcEndpoints=true`, subsequent UCs with `false`.

---

## What's Next

- SageMaker Batch Transform integration for UC9 (autonomous driving point cloud segmentation)
- Real-time streaming with Kinesis for high-frequency sensor data
- Multi-account deployment patterns with AWS Organizations
- Cost optimization with Lambda Provisioned Concurrency for latency-sensitive UCs

---

**Repository**: [github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns)

**Phase 1 Article**: [Industry-Specific Serverless Automation Patterns with FSx for ONTAP S3 Access Points](https://dev.to/yoshikifujiwara/industry-specific-serverless-automation-patterns-with-fsx-for-ontap-s3-access-points-4a5g)

**License**: MIT
