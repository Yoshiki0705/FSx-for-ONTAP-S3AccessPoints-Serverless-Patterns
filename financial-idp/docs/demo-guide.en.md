# Contract & Invoice Automated Processing — Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | English | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

This demo showcases an automated processing pipeline for contracts and invoices. It combines OCR text extraction with entity extraction to automatically generate structured data from unstructured documents.

**Core Message**: Automatically digitize paper-based contracts and invoices, instantly extracting and structuring key information such as amounts, dates, and vendor names.

**Target Duration**: 3–5 minutes

---

## Target Audience & Persona

| Item | Details |
|------|---------|
| **Role** | Accounting Manager / Contract Administrator |
| **Daily Tasks** | Invoice processing, contract management, payment approvals |
| **Challenge** | Manual data entry from large volumes of paper documents is time-consuming |
| **Expected Outcome** | Automated document processing and reduced input errors |

### Persona: Accounting Team Leader

- Processes 200+ invoices monthly
- Manual entry errors and delays are ongoing issues
- "I want amounts and due dates extracted automatically when invoices arrive"

---

## Demo Scenario: Invoice Batch Processing

### Workflow Overview

```
Document Scan     OCR Processing    Entity              Structured Data
(PDF/Image)   →   Text Extraction → Extraction &    →   Output (JSON)
                                    Classification
                                    (AI Analysis)
```

---

## Output Destination: FSxN S3 Access Point (Pattern A)

This UC falls under **Pattern A: Native S3AP Output**
(see `docs/output-destination-patterns.md`).

**Design**: All AI/ML artifacts are written back to the **same FSx ONTAP
volume** as the source data via the FSxN S3 Access Point — no separate
standard S3 bucket is created ("no data movement" pattern).

**CloudFormation parameters**:
- `S3AccessPointAlias`: Input S3 AP Alias
- `S3AccessPointOutputAlias`: Output S3 AP Alias (can be same as input)

See [README.en.md — AWS Specification Constraints](../../README.en.md#aws-specification-constraints-and-workarounds)
for AWS-side limitations and workarounds.

---
## Storyboard (5 Sections / 3–5 min)

### Section 1: Problem Statement (0:00–0:45)

**Narration Summary**:
> Over 200 invoices arrive monthly. Manually entering amounts, dates, and vendor names is time-consuming and error-prone.

**Key Visual**: Large collection of PDF invoice files

### Section 2: Document Upload (0:45–1:30)

**Narration Summary**:
> Simply placing scanned documents on the file server automatically triggers the processing pipeline.

**Key Visual**: File upload → workflow auto-trigger

### Section 3: OCR & Extraction (1:30–2:30)

**Narration Summary**:
> OCR extracts text, then AI determines document type. Automatically classifies invoices, contracts, and receipts, extracting key fields from each.

**Key Visual**: OCR processing progress, document classification results

### Section 4: Structured Output (2:30–3:45)

**Narration Summary**:
> Extraction results output as structured data. Amounts, due dates, vendor names, and invoice numbers available in JSON format.

**Key Visual**: Extraction results table (invoice number, amount, due date, vendor)

### Section 5: Validation & Report (3:45–5:00)

**Narration Summary**:
> AI evaluates confidence scores for extraction results, flagging low-confidence items. Processing summary report provides overall status overview.

**Key Visual**: Results with confidence scores, processing summary report

---

## Screen Capture Plan

| # | Screen | Section |
|---|--------|---------|
| 1 | Invoice PDF file list | Section 1 |
| 2 | Workflow auto-trigger | Section 2 |
| 3 | OCR processing / document classification | Section 3 |
| 4 | Structured data output (JSON/table) | Section 4 |
| 5 | Processing summary report | Section 5 |

---

## Narration Outline

| Section | Time | Key Message |
|---------|------|-------------|
| Problem | 0:00–0:45 | "Processing 200 invoices manually per month is unsustainable" |
| Upload | 0:45–1:30 | "Just place files to start automated processing" |
| OCR | 1:30–2:30 | "OCR + AI for document classification and field extraction" |
| Output | 2:30–3:45 | "Immediately available as structured data" |
| Report | 3:45–5:00 | "Confidence scoring highlights items needing human review" |

---

## Sample Data Requirements

| # | Data | Purpose |
|---|------|---------|
| 1 | Invoice PDFs (10) | Main processing target |
| 2 | Contract PDFs (3) | Document classification demo |
| 3 | Receipt images (3) | Image OCR demo |
| 4 | Low-quality scans (2) | Confidence scoring demo |

---

## Timeline

### Achievable Within 1 Week

| Task | Duration |
|------|----------|
| Prepare sample documents | 3 hours |
| Verify pipeline execution | 2 hours |
| Capture screenshots | 2 hours |
| Create narration script | 2 hours |
| Video editing | 4 hours |

### Future Enhancements

- Automatic integration with accounting systems
- Approval workflow integration
- Multi-language document support (English, Chinese)

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Workflow orchestration |
| Lambda (OCR Processor) | Document text extraction via Textract |
| Lambda (Entity Extractor) | Entity extraction via Bedrock |
| Lambda (Classifier) | Document type classification |
| Amazon Athena | Aggregation analysis of extracted data |

### Fallback

| Scenario | Response |
|----------|----------|
| OCR accuracy degradation | Use pre-processed text |
| Bedrock delay | Display pre-generated results |

---

*This document serves as a production guide for technical presentation demo videos.*
