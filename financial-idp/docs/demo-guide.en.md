# Contract and Invoice Automatic Processing — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | English | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> Note: This translation is produced by Amazon Bedrock Claude. Contributions to improve translation quality are welcome.

## Executive Summary

This demo demonstrates an automated processing pipeline for contracts and invoices. By combining OCR-based text extraction with entity extraction, it automatically generates structured data from unstructured documents.

**Core Demo Message**: Automatically digitize paper-based contracts and invoices, and instantly extract and structure critical information such as amounts, dates, and business partners.

**Estimated Duration**: 3–5 minutes

---

## Target Audience & Persona

| Item | Details |
|------|------|
| **Role** | Accounting Department Manager / Contract Management Lead |
| **Daily Tasks** | Invoice processing, contract management, payment approval |
| **Challenges** | Manual entry of large volumes of paper documents is time-consuming |
| **Expected Outcomes** | Automation of document processing and reduction of input errors |

### Persona: Yamada-san (Accounting Department Leader)

- Processes 200+ invoices monthly
- Faces challenges with errors and delays from manual entry
- "I want to automatically extract amounts and payment due dates when invoices arrive"

---

## Demo Scenario: Invoice Batch Processing

### Overall Workflow

```
Document Scan       OCR Processing     Entity            Structured Data
(PDF/Image)    →   Text Extraction →  Extraction &  →   Output (JSON)
                                       Classification
                                       (AI Analysis)
```

---

## Storyboard (5 Sections / 3–5 minutes)

### Section 1: Problem Statement (0:00–0:45)

**Narration Summary**:
> Over 200 invoices arrive monthly. Manually entering amounts, dates, and business partners is time-consuming and error-prone.

**Key Visual**: List of numerous PDF invoice files

### Section 2: Document Upload (0:45–1:30)

**Narration Summary**:
> Simply place scanned documents on the file server, and the automated processing pipeline starts automatically.

**Key Visual**: File upload → Automatic workflow initiation

### Section 3: OCR & Extraction (1:30–2:30)

**Narration Summary**:
> Extract text with OCR, and AI determines document type. Automatically classify invoices, contracts, and receipts, and extract key fields from each document.

**Key Visual**: OCR processing progress, document classification results

### Section 4: Structured Output (2:30–3:45)

**Narration Summary**:
> Output extraction results as structured data. Amounts, payment due dates, business partner names, invoice numbers, etc. are available in JSON format.

**Key Visual**: Extraction results table (invoice number, amount, due date, business partner)

### Section 5: Validation & Report (3:45–5:00)

**Narration Summary**:
> AI evaluates the confidence of extraction results and flags low-confidence items. Understand overall processing status with a processing summary report.

**Key Visual**: Results with confidence scores, processing summary report

---

## Screen Capture Plan

| # | Screen | Section |
|---|------|-----------|
| 1 | Invoice PDF file list | Section 1 |
| 2 | Automatic workflow initiation | Section 2 |
| 3 | OCR processing & document classification results | Section 3 |
| 4 | Structured data output (JSON/table) | Section 4 |
| 5 | Processing summary report | Section 5 |

---

## Narration Outline

| Section | Time | Key Message |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "Manually processing 200 invoices per month is unsustainable" |
| Upload | 0:45–1:30 | "Automated processing starts just by placing files" |
| OCR | 1:30–2:30 | "Document classification and field extraction with OCR + AI" |
| Output | 2:30–3:45 | "Immediately available as structured data" |
| Report | 3:45–5:00 | "Confidence evaluation highlights areas requiring human review" |

---

## Sample Data Requirements

| # | Data | Purpose |
|---|--------|------|
| 1 | Invoice PDFs (10 files) | Main processing target |
| 2 | Contract PDFs (3 files) | Document classification demo |
| 3 | Receipt images (3 files) | Image OCR demo |
| 4 | Low-quality scans (2 files) | Confidence evaluation demo |

---

## Timeline

### Achievable within 1 week

| Task | Time Required |
|--------|---------|
| Sample document preparation | 3 hours |
| Pipeline execution verification | 2 hours |
| Screen capture acquisition | 2 hours |
| Narration script creation | 2 hours |
| Video editing | 4 hours |

### Future Enhancements

- Automatic integration with accounting systems
- Approval workflow integration
- Multi-language document support (English, Chinese)

---

## Technical Notes

| Component | Role |
|--------------|------|
| Step Functions | Workflow orchestration |
| Lambda (OCR Processor) | Document text extraction with Textract |
| Lambda (Entity Extractor) | Entity extraction with Bedrock |
| Lambda (Classifier) | Document type classification |
| Amazon Athena | Aggregation and analysis of extracted data |

### Fallback

| Scenario | Response |
|---------|------|
| OCR accuracy degradation | Use pre-processed text |
| Bedrock latency | Display pre-generated results |

---

*This document is a production guide for technical presentation demo videos.*

---

## About Output Destination: FSxN S3 Access Point (Pattern A)

UC2 financial-idp is classified as **Pattern A: Native S3AP Output**
(see `docs/output-destination-patterns.md`).

**Design**: Invoice OCR results, structured metadata, and BedRock summaries are all written back via FSxN S3 Access Point to the **same FSx ONTAP volume** as the original invoice PDFs. No standard S3 bucket is created ("no data movement" pattern).

**CloudFormation Parameters**:
- `S3AccessPointAlias`: S3 AP Alias for reading input data
- `S3AccessPointOutputAlias`: S3 AP Alias for writing output (can be the same as input)

**Deployment Example**:
```bash
aws cloudformation deploy \
  --template-file financial-idp/template-deploy.yaml \
  --stack-name fsxn-financial-idp-demo \
  --parameter-overrides \
    S3AccessPointAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    S3AccessPointOutputAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    ... (other required parameters)
```

**View from SMB/NFS Users**:
```
/vol/invoices/
  ├── 2026/05/invoice_001.pdf          # Original invoice
  └── summaries/2026/05/                # AI-generated summary (within same volume)
      └── invoice_001.json
```

For AWS specification constraints, refer to
[the "AWS Specification Constraints and Workarounds" section in the project README](../../README.md#aws-仕様上の制約と回避策)
and [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md).

---

## Verified UI/UX Screenshots

Following the same approach as Phase 7 UC15/16/17 and UC6/11/14 demos, we target **UI/UX screens that end users actually see in their daily work**. Technical views (Step Functions graphs, CloudFormation stack events, etc.) are consolidated in `docs/verification-results-*.md`.

### Verification Status for This Use Case

- ⚠️ **E2E Verification**: Partial functionality only (additional verification recommended in production)
- 📸 **UI/UX Capture**: ✅ SFN Graph completed (Phase 8 Theme D, commit 081cc66)

### Captured in 2026-05-10 Redeployment Verification (UI/UX Focus)

#### UC2 Step Functions Graph view (SUCCEEDED)

![UC2 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc2-demo/uc2-stepfunctions-graph.png)

Step Functions Graph view is the most critical end-user screen that visualizes the execution status of each Lambda / Parallel / Map state with colors.

### Existing Screenshots (Applicable from Phase 1-6)

![UC2 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc2-demo/step-functions-graph-succeeded.png)

### UI/UX Target Screens for Re-verification (Recommended Capture List)

- S3 output bucket (textract-results/, comprehend-entities/, reports/)
- Textract OCR result JSON (fields extracted from contracts and invoices)
- Comprehend entity detection results (organization names, dates, amounts)
- Bedrock-generated summary reports

### Capture Guide

1. **Preparation**:
   - Verify prerequisites with `bash scripts/verify_phase7_prerequisites.sh` (check for shared VPC/S3 AP)
   - Package Lambda with `UC=financial-idp bash scripts/package_generic_uc.sh`
   - Deploy with `bash scripts/deploy_generic_ucs.sh UC2`

2. **Sample Data Placement**:
   - Upload sample files to `invoices/` prefix via S3 AP Alias
   - Start Step Functions `fsxn-financial-idp-demo-workflow` (input `{}`)

3. **Capture** (close CloudShell/terminal, mask username in browser top-right):
   - Overview of S3 output bucket `fsxn-financial-idp-demo-output-<account>`
   - Preview of AI/ML output JSON (refer to `build/preview_*.html` format)
   - SNS email notification (if applicable)

4. **Masking**:
   - Auto-mask with `python3 scripts/mask_uc_demos.py financial-idp-demo`
   - Apply additional masking as needed following `docs/screenshots/MASK_GUIDE.md`

5. **Cleanup**:
   - Delete with `bash scripts/cleanup_generic_ucs.sh UC2`
   - VPC Lambda ENI release takes 15-30 minutes (AWS specification)
