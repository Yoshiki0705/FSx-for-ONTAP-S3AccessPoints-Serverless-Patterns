# Delivery Slip OCR and Inventory Analysis — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | English | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> Note: This translation is produced by Amazon Bedrock Claude. Contributions to improve translation quality are welcome.

## Executive Summary

This demo demonstrates an OCR processing and inventory analysis pipeline for delivery waybills. It digitizes paper waybills and automatically aggregates and analyzes inbound/outbound data.

**Core Demo Message**: Automatically digitize delivery waybills to support real-time inventory visibility and demand forecasting.

**Expected Duration**: 3–5 minutes

---

## Target Audience & Persona

| Item | Details |
|------|---------|
| **Role** | Logistics Manager / Warehouse Manager |
| **Daily Tasks** | Inbound/outbound management, inventory verification, delivery coordination |
| **Challenges** | Delays and errors from manual entry of paper waybills |
| **Expected Outcomes** | Automation of waybill processing and inventory visualization |

### Persona: Mr. Saito (Logistics Manager)

- Processes 500+ delivery waybills per day
- Inventory information is always delayed due to manual entry time lag
- "I want to reflect inventory just by scanning waybills"

---

## Demo Scenario: Delivery Waybill Batch Processing

### Overall Workflow

```
Delivery Waybill    OCR Processing    Data Structuring    Inventory Analysis
(Scanned Image)  →  Text Extraction →  Field Mapping   →  Aggregation Report
                                                           Demand Forecasting
```

---

## Storyboard (5 Sections / 3–5 minutes)

### Section 1: Problem Statement (0:00–0:45)

**Narration Summary**:
> Over 500 delivery waybills per day. Manual entry delays inventory information updates, increasing the risk of stockouts and excess inventory.

**Key Visual**: Large volume of scanned waybill images, manual entry delay imagery

### Section 2: Scan & Upload (0:45–1:30)

**Narration Summary**:
> Simply place scanned waybill images in a folder, and the OCR pipeline automatically starts.

**Key Visual**: Waybill image upload → Workflow activation

### Section 3: OCR Processing (1:30–2:30)

**Narration Summary**:
> OCR extracts text from waybills, and AI automatically maps fields such as product name, quantity, destination, and date.

**Key Visual**: OCR processing in progress, field extraction results

### Section 4: Inventory Analysis (2:30–3:45)

**Narration Summary**:
> Cross-reference extracted data with the inventory database. Automatically aggregate inbound/outbound transactions and update inventory status.

**Key Visual**: Inventory aggregation results, inbound/outbound trends by item

### Section 5: Demand Report (3:45–5:00)

**Narration Summary**:
> AI generates an inventory analysis report. Presents inventory turnover rate, items at risk of stockout, and order recommendations.

**Key Visual**: AI-generated inventory report (inventory summary + order recommendations)

---

## Screen Capture Plan

| # | Screen | Section |
|---|--------|---------|
| 1 | Scanned waybill image list | Section 1 |
| 2 | Upload / Pipeline activation | Section 2 |
| 3 | OCR extraction results | Section 3 |
| 4 | Inventory aggregation dashboard | Section 4 |
| 5 | AI inventory analysis report | Section 5 |

---

## Narration Outline

| Section | Time | Key Message |
|---------|------|-------------|
| Problem | 0:00–0:45 | "Inventory information is always outdated due to manual entry delays" |
| Upload | 0:45–1:30 | "Automatic processing starts just by placing scans" |
| OCR | 1:30–2:30 | "AI automatically recognizes and structures waybill fields" |
| Analysis | 2:30–3:45 | "Automatically aggregate inbound/outbound and update inventory immediately" |
| Report | 3:45–5:00 | "AI presents stockout risks and order recommendations" |

---

## Sample Data Requirements

| # | Data | Purpose |
|---|------|---------|
| 1 | Inbound waybill images (10 sheets) | OCR processing demo |
| 2 | Outbound waybill images (10 sheets) | Inventory deduction demo |
| 3 | Handwritten waybills (3 sheets) | OCR accuracy demo |
| 4 | Inventory master data | Cross-reference demo |

---

## Timeline

### Achievable Within 1 Week

| Task | Time Required |
|------|---------------|
| Prepare sample waybill images | 2 hours |
| Verify pipeline execution | 2 hours |
| Capture screenshots | 2 hours |
| Create narration script | 2 hours |
| Video editing | 4 hours |

### Future Enhancements

- Real-time waybill processing (camera integration)
- WMS system integration
- Demand forecasting model integration

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Workflow orchestration |
| Lambda (OCR Processor) | Waybill text extraction via Textract |
| Lambda (Field Mapper) | Field mapping via Bedrock |
| Lambda (Inventory Updater) | Inventory data update and aggregation |
| Lambda (Report Generator) | Inventory analysis report generation |

### Fallback

| Scenario | Response |
|----------|----------|
| OCR accuracy degradation | Use pre-processed data |
| Bedrock delay | Display pre-generated report |

---

*This document is a production guide for demo videos for technical presentations.*

---

## About Output Destination: Selectable via OutputDestination (Pattern B)

UC12 logistics-ocr added support for the `OutputDestination` parameter in the 2026-05-10 update
(see `docs/output-destination-patterns.md`).

**Target Workload**: Delivery waybill OCR / Inventory analysis / Logistics reports

**Two Modes**:

### STANDARD_S3 (Default, traditional behavior)
Creates a new S3 bucket (`${AWS::StackName}-output-${AWS::AccountId}`) and
writes AI artifacts there.

```bash
aws cloudformation deploy \
  --template-file logistics-ocr/template-deploy.yaml \
  --stack-name fsxn-logistics-ocr-demo \
  --parameter-overrides \
    OutputDestination=STANDARD_S3 \
    ... (other required parameters)
```

### FSXN_S3AP ("no data movement" pattern)
Writes AI artifacts back to the **same FSx ONTAP volume** as the original data via FSxN S3 Access Point.
SMB/NFS users can directly view AI artifacts within the directory structure used in daily operations.
No standard S3 bucket is created.

```bash
aws cloudformation deploy \
  --template-file logistics-ocr/template-deploy.yaml \
  --stack-name fsxn-logistics-ocr-demo \
  --parameter-overrides \
    OutputDestination=FSXN_S3AP \
    OutputS3APPrefix=ai-outputs/ \
    S3AccessPointName=eda-demo-s3ap \
    ... (other required parameters)
```

**Notes**:

- Strongly recommend specifying `S3AccessPointName` (grant IAM permissions for both Alias and ARN formats)
- Objects over 5GB are not supported by FSxN S3AP (AWS specification), multipart upload required
- For AWS specification constraints, see
  [the "AWS Specification Constraints and Workarounds" section in the project README](../../README.md#aws-仕様上の制約と回避策)
  and [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)

---

## Verified UI/UX Screenshots

Following the same policy as Phase 7 UC15/16/17 and UC6/11/14 demos, targeting **UI/UX screens that end users actually see in daily operations**. Technical views (Step Functions graphs, CloudFormation stack events, etc.) are consolidated in `docs/verification-results-*.md`.

### Verification Status for This Use Case

- ✅ **E2E Execution**: Verified in Phase 1-6 (see root README)
- 📸 **UI/UX Re-capture**: ✅ Captured in 2026-05-10 redeployment verification (confirmed UC12 Step Functions graph, Lambda execution success)
- 🔄 **Reproduction Method**: See "Capture Guide" at the end of this document

### Captured in 2026-05-10 Redeployment Verification (UI/UX Focus)

#### UC12 Step Functions Graph view (SUCCEEDED)

![UC12 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc12-demo/uc12-stepfunctions-graph.png)

Step Functions Graph view is the most important end-user screen that visualizes the execution status of each Lambda / Parallel / Map state with colors.

### Existing Screenshots (Applicable from Phase 1-6)

![UC12 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc12-demo/step-functions-graph-succeeded.png)

![UC12 Step Functions Graph (Zoomed view — each step detail)](../../docs/screenshots/masked/uc12-demo/step-functions-graph-zoomed.png)

### UI/UX Target Screens for Re-verification (Recommended Capture List)

- S3 output bucket (waybills-ocr/, inventory/, reports/)
- Textract waybill OCR results (Cross-Region)
- Rekognition warehouse image labels
- Delivery aggregation report

### Capture Guide

1. **Preparation**:
   - Verify prerequisites with `bash scripts/verify_phase7_prerequisites.sh` (check for shared VPC/S3 AP)
   - Package Lambda with `UC=logistics-ocr bash scripts/package_generic_uc.sh`
   - Deploy with `bash scripts/deploy_generic_ucs.sh UC12`

2. **Place Sample Data**:
   - Upload sample files to `waybills/` prefix via S3 AP Alias
   - Start Step Functions `fsxn-logistics-ocr-demo-workflow` (input `{}`)

3. **Capture** (close CloudShell/terminal, mask username in browser top-right):
   - Overview of S3 output bucket `fsxn-logistics-ocr-demo-output-<account>`
   - AI/ML output JSON preview (refer to `build/preview_*.html` format)
   - SNS email notification (if applicable)

4. **Masking**:
   - Auto-mask with `python3 scripts/mask_uc_demos.py logistics-ocr-demo`
   - Apply additional masking as needed following `docs/screenshots/MASK_GUIDE.md`

5. **Cleanup**:
   - Delete with `bash scripts/cleanup_generic_ucs.sh UC12`
   - VPC Lambda ENI release takes 15-30 minutes (AWS specification)
