# DICOM Anonymization Workflow — Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | English | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

This demo showcases a DICOM medical image anonymization workflow. It demonstrates the process of automatically removing patient personal information for research data sharing and verifying anonymization quality.

**Core Message**: Automatically remove patient identifying information from DICOM files, safely generating anonymized datasets ready for research use.

**Target Duration**: 3–5 minutes

---

## Target Audience & Persona

| Item | Details |
|------|---------|
| **Role** | Health Information Manager / Clinical Research Data Manager |
| **Daily Tasks** | Medical image management, research data provision, privacy protection |
| **Challenge** | Manual anonymization of large DICOM volumes is time-consuming and error-prone |
| **Expected Outcome** | Safe, reliable anonymization with automated audit trails |

### Persona: Clinical Research Data Manager

- Multi-site collaborative research requiring anonymization of 10,000+ DICOM files
- Reliable removal of patient name, ID, date of birth, etc. is mandatory
- "I want to guarantee zero anonymization leaks while maintaining image quality"

---

## Demo Scenario: DICOM Anonymization for Research Data Sharing

### Workflow Overview

```
DICOM Files         Tag Analysis     De-identification    Quality Verification
(With Patient   →   Metadata      →  PII Removal      →  Anonymization
 Info)              Extraction       Hashing              Confirmation &
                                                          Report Generation
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
> 10,000 DICOM files need anonymization for multi-site collaborative research. Manual processing risks errors, and personal information leakage is unacceptable.

**Key Visual**: DICOM file list, highlighted patient information tags

### Section 2: Workflow Trigger (0:45–1:30)

**Narration Summary**:
> Specify the target dataset and launch the anonymization workflow. Configure anonymization rules (removal, hashing, generalization).

**Key Visual**: Workflow launch, anonymization rule configuration screen

### Section 3: De-identification (1:30–2:30)

**Narration Summary**:
> Automatically process personal information tags in each DICOM file. Patient name → hash, date of birth → age range, institution name → anonymous code. Image pixel data is preserved.

**Key Visual**: Anonymization processing progress, tag transformation before/after

### Section 4: Quality Verification (2:30–3:45)

**Narration Summary**:
> Automatically verify anonymized files. Scan all tags for remaining personal information. Also confirm image integrity.

**Key Visual**: Verification results — anonymization success rate, remaining risk tags list

### Section 5: Audit Report (3:45–5:00)

**Narration Summary**:
> Automatically generate an anonymization audit report. Records processing counts, removed tags, and verification results. Usable as submission material for ethics review boards.

**Key Visual**: Audit report (processing summary + compliance evidence)

---

## Screen Capture Plan

| # | Screen | Section |
|---|--------|---------|
| 1 | DICOM file list (pre-anonymization) | Section 1 |
| 2 | Workflow launch / rule configuration | Section 2 |
| 3 | Anonymization processing progress | Section 3 |
| 4 | Quality verification results | Section 4 |
| 5 | Audit report | Section 5 |

---

## Narration Outline

| Section | Time | Key Message |
|---------|------|-------------|
| Problem | 0:00–0:45 | "Anonymization leaks in bulk DICOM processing are unacceptable" |
| Trigger | 0:45–1:30 | "Configure anonymization rules and launch workflow" |
| Processing | 1:30–2:30 | "Auto-remove PII tags while preserving image quality" |
| Verification | 2:30–3:45 | "Full tag scan confirms zero anonymization leaks" |
| Report | 3:45–5:00 | "Auto-generate audit trail for ethics board submission" |

---

## Sample Data Requirements

| # | Data | Purpose |
|---|------|---------|
| 1 | Test DICOM files (20) | Main processing target |
| 2 | Complex tag structure DICOM (5) | Edge cases |
| 3 | DICOM with private tags (3) | High-risk verification |

---

## Timeline

### Achievable Within 1 Week

| Task | Duration |
|------|----------|
| Prepare test DICOM data | 3 hours |
| Verify pipeline execution | 2 hours |
| Capture screenshots | 2 hours |
| Create narration script | 2 hours |
| Video editing | 4 hours |

### Future Enhancements

- Automatic detection/removal of burned-in text in images
- FHIR integration for anonymization mapping management
- Differential anonymization (incremental processing of additional data)

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Workflow orchestration |
| Lambda (Tag Parser) | DICOM tag analysis / PII detection |
| Lambda (De-identifier) | Tag anonymization processing |
| Lambda (Verifier) | Anonymization quality verification |
| Lambda (Report Generator) | Audit report generation |

### Fallback

| Scenario | Response |
|----------|----------|
| DICOM parse failure | Use pre-processed data |
| Verification error | Switch to manual verification flow |

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
- 📸 **UI/UX**: Not yet captured

### Existing Screenshots (from Phase 1-6)

*(None applicable. Please capture during re-verification.)*

### UI/UX Target Screens for Re-verification (Recommended Capture List)

- S3 output bucket (dicom-metadata/, deid-reports/, diagnoses/)
- Comprehend Medical entity detection results (Cross-Region)
- De-identified DICOM metadata JSON

### Capture Guide

1. **Preparation**: Run `bash scripts/verify_phase7_prerequisites.sh` to check prerequisites
2. **Sample Data**: Upload sample files via S3 AP Alias, then start Step Functions workflow
3. **Capture** (close CloudShell/terminal, mask username in browser top-right)
4. **Mask**: Run `python3 scripts/mask_uc_demos.py <uc-dir>` for automated OCR masking
5. **Cleanup**: Run `bash scripts/cleanup_generic_ucs.sh <UC>` to delete stack
