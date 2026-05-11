# Shipping Slip OCR & Inventory Analysis — Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | English | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

This demo showcases a shipping slip OCR processing and inventory analysis pipeline. It digitizes paper slips and automatically aggregates and analyzes inbound/outbound data.

**Core Message**: Automatically digitize shipping slips, enabling real-time inventory visibility and demand forecasting support.

**Target Duration**: 3–5 minutes

---

## Target Audience & Persona

| Item | Details |
|------|---------|
| **Role** | Logistics Manager / Warehouse Manager |
| **Daily Tasks** | Inbound/outbound management, inventory verification, shipping coordination |
| **Challenge** | Manual entry from paper slips causes delays and errors |
| **Expected Outcome** | Automated slip processing and inventory visualization |

### Persona: Logistics Manager

- Processes 500+ shipping slips daily
- Manual entry time lag means inventory information is always outdated
- "I want inventory updated just by scanning slips"

---

## Demo Scenario: Shipping Slip Batch Processing

### Workflow Overview

```
Shipping Slips     OCR Processing    Data Structuring    Inventory Analysis
(Scanned Images) → Text Extraction → Field            → Aggregation Report
                                     Mapping             Demand Forecast
```

---

## Output Destination: Selectable via OutputDestination (Pattern B)

This UC supports the `OutputDestination` parameter (2026-05-10 update,
see `docs/output-destination-patterns.md`).

**Two modes**:

- **STANDARD_S3** (default): AI artifacts go to a new S3 bucket
- **FSXN_S3AP** ("no data movement"): AI artifacts go back to the same
  FSx ONTAP volume via S3 Access Point — visible to SMB/NFS users in
  the existing directory structure

```bash
# FSXN_S3AP mode
--parameter-overrides OutputDestination=FSXN_S3AP OutputS3APPrefix=ai-outputs/
```

See [README.en.md — AWS Specification Constraints](../../README.en.md#aws-specification-constraints-and-workarounds)
for AWS-side limitations and workarounds.

---
## Storyboard (5 Sections / 3–5 min)

### Section 1: Problem Statement (0:00–0:45)

**Narration Summary**:
> Over 500 shipping slips daily. Manual entry delays inventory updates, increasing stockout and overstock risks.

**Key Visual**: Large volume of scanned slip images, manual entry delay illustration

### Section 2: Scan & Upload (0:45–1:30)

**Narration Summary**:
> Simply place scanned slip images in a folder to auto-trigger the OCR pipeline.

**Key Visual**: Slip image upload → workflow trigger

### Section 3: OCR Processing (1:30–2:30)

**Narration Summary**:
> OCR extracts text from slips, then AI automatically maps fields: product name, quantity, destination, date, etc.

**Key Visual**: OCR processing, field extraction results

### Section 4: Inventory Analysis (2:30–3:45)

**Narration Summary**:
> Cross-reference extracted data with inventory database. Auto-aggregate inbound/outbound and update inventory status.

**Key Visual**: Inventory aggregation results, item-level inbound/outbound trends

### Section 5: Demand Report (3:45–5:00)

**Narration Summary**:
> AI generates an inventory analysis report presenting inventory turnover, stockout risk items, and reorder recommendations.

**Key Visual**: AI-generated inventory report (inventory summary + reorder recommendations)

---

## Screen Capture Plan

| # | Screen | Section |
|---|--------|---------|
| 1 | Scanned slip image list | Section 1 |
| 2 | Upload / pipeline trigger | Section 2 |
| 3 | OCR extraction results | Section 3 |
| 4 | Inventory aggregation dashboard | Section 4 |
| 5 | AI inventory analysis report | Section 5 |

---

## Narration Outline

| Section | Time | Key Message |
|---------|------|-------------|
| Problem | 0:00–0:45 | "Manual entry delays keep inventory info always outdated" |
| Upload | 0:45–1:30 | "Just scan and place to start automated processing" |
| OCR | 1:30–2:30 | "AI auto-recognizes and structures slip fields" |
| Analysis | 2:30–3:45 | "Auto-aggregate inbound/outbound, instantly update inventory" |
| Report | 3:45–5:00 | "AI presents stockout risks and reorder recommendations" |

---

## Sample Data Requirements

| # | Data | Purpose |
|---|------|---------|
| 1 | Inbound slip images (10) | OCR processing demo |
| 2 | Outbound slip images (10) | Inventory deduction demo |
| 3 | Handwritten slips (3) | OCR accuracy demo |
| 4 | Inventory master data | Cross-reference demo |

---

## Timeline

### Achievable Within 1 Week

| Task | Duration |
|------|----------|
| Prepare sample slip images | 2 hours |
| Verify pipeline execution | 2 hours |
| Capture screenshots | 2 hours |
| Create narration script | 2 hours |
| Video editing | 4 hours |

### Future Enhancements

- Real-time slip processing (camera integration)
- WMS system integration
- Demand forecasting model integration

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Workflow orchestration |
| Lambda (OCR Processor) | Slip text extraction via Textract |
| Lambda (Field Mapper) | Field mapping via Bedrock |
| Lambda (Inventory Updater) | Inventory data update/aggregation |
| Lambda (Report Generator) | Inventory analysis report generation |

### Fallback

| Scenario | Response |
|----------|----------|
| OCR accuracy degradation | Use pre-processed data |
| Bedrock delay | Display pre-generated report |

---

*This document serves as a production guide for technical presentation demo videos.*

---

## Verified UI/UX Screenshots

Following the same approach as Phase 7 UC15/16/17 and UC6/11/14 demos, targeting
**UI/UX screens that end users actually see in daily operations**.
Technical views (Step Functions graph, CloudFormation stack events, etc.)
are consolidated in `docs/verification-results-*.md`.

### Verification Status for This Use Case

- ⚠️ **E2E**: Partial (additional verification recommended)
- 📸 **UI/UX Capture**: ✅ SFN Graph complete (Phase 8 Theme D, commit 3c90042)

### Existing Screenshots (from Phase 1-6)

![UC12 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc12-demo/step-functions-graph-succeeded.png)

![UC12 Step Functions Graph (zoomed — per-step detail)](../../docs/screenshots/masked/uc12-demo/step-functions-graph-zoomed.png)

### UI/UX Target Screens for Re-verification (Recommended Capture List)

- S3 output bucket (waybills-ocr/, inventory/, reports/)
- Textract waybill OCR results (Cross-Region)
- Rekognition warehouse image labels
- Delivery aggregation report

### Capture Guide

1. **Preparation**: Run `bash scripts/verify_phase7_prerequisites.sh` to check prerequisites
2. **Sample Data**: Upload sample files via S3 AP Alias, then start Step Functions workflow
3. **Capture** (close CloudShell/terminal, mask username in browser top-right)
4. **Mask**: Run `python3 scripts/mask_uc_demos.py <uc-dir>` for automated OCR masking
5. **Cleanup**: Run `bash scripts/cleanup_generic_ucs.sh <UC>` to delete stack
