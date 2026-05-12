# Accident Photo Damage Assessment and Insurance Claim Report — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | English | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> Note: This translation is produced by Amazon Bedrock Claude. Contributions to improve translation quality are welcome.

## Executive Summary

This demo demonstrates an automated pipeline for damage assessment and insurance claims report generation from accident photos. It streamlines the assessment process through image analysis-based damage evaluation and AI report generation.

**Core Demo Message**: AI automatically analyzes accident photos, evaluates the extent of damage, and instantly generates insurance claims reports.

**Estimated Duration**: 3–5 minutes

---

## Target Audience & Persona

| Item | Details |
|------|------|
| **Role** | Damage Assessor / Claims Adjuster |
| **Daily Tasks** | Review accident photos, evaluate damage, calculate insurance payouts, create reports |
| **Challenges** | Need to process large volumes of claims quickly |
| **Expected Outcomes** | Accelerate assessment process and ensure consistency |

### Persona: Kobayashi-san (Damage Assessor)

- Processes 100+ insurance claims per month
- Judges extent of damage from photos and creates reports
- "I want to automate initial assessments and focus on complex cases"

---

## Demo Scenario: Auto Accident Damage Assessment

### Overall Workflow

```
Accident Photos    Image Analysis    Damage Evaluation    Claims Report
(Multiple)     →   Damage Detection  →  Severity Assessment  →  AI Generation
                   Part Identification   Cost Estimation
```

---

## Storyboard (5 Sections / 3–5 minutes)

### Section 1: Problem Statement (0:00–0:45)

**Narration Summary**:
> Over 100 insurance claims per month. For each case, review multiple accident photos, evaluate damage extent, and create reports. Manual processing cannot keep up.

**Key Visual**: Insurance claims case list, accident photo samples

### Section 2: Photo Upload (0:45–1:30)

**Narration Summary**:
> When accident photos are uploaded, the automated assessment pipeline is triggered. Processing is done per case.

**Key Visual**: Photo upload → Workflow automatic activation

### Section 3: Damage Detection (1:30–2:30)

**Narration Summary**:
> AI analyzes photos and detects damaged areas. Identifies damage types (dents, scratches, breakage) and parts (bumper, door, fender, etc.).

**Key Visual**: Damage detection results, part mapping

### Section 4: Assessment (2:30–3:45)

**Narration Summary**:
> Evaluates damage severity, determines repair/replacement decisions, and calculates estimated costs. Also compares with similar past cases.

**Key Visual**: Damage evaluation results table, cost estimation

### Section 5: Claims Report (3:45–5:00)

**Narration Summary**:
> AI automatically generates insurance claims report. Includes damage summary, estimated costs, and recommended actions. Assessors only need to review and approve.

**Key Visual**: AI-generated claims report (damage summary + cost estimation)

---

## Screen Capture Plan

| # | Screen | Section |
|---|------|-----------|
| 1 | Claims case list | Section 1 |
| 2 | Photo upload / pipeline activation | Section 2 |
| 3 | Damage detection results | Section 3 |
| 4 | Damage evaluation / cost estimation | Section 4 |
| 5 | Insurance claims report | Section 5 |

---

## Narration Outline

| Section | Time | Key Message |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "Manually assessing 100 claims per month is unsustainable" |
| Upload | 0:45–1:30 | "Photo upload triggers automatic assessment" |
| Detection | 1:30–2:30 | "AI automatically detects damage locations and types" |
| Assessment | 2:30–3:45 | "Automatically estimates damage severity and repair costs" |
| Report | 3:45–5:00 | "Auto-generates claims report, only review and approval needed" |

---

## Sample Data Requirements

| # | Data | Purpose |
|---|--------|------|
| 1 | Minor damage photos (5 cases) | Basic assessment demo |
| 2 | Moderate damage photos (3 cases) | Evaluation accuracy demo |
| 3 | Severe damage photos (2 cases) | Total loss determination demo |

---

## Timeline

### Achievable Within 1 Week

| Task | Time Required |
|--------|---------|
| Prepare sample photo data | 2 hours |
| Verify pipeline execution | 2 hours |
| Capture screenshots | 2 hours |
| Create narration script | 2 hours |
| Video editing | 4 hours |

### Future Enhancements

- Damage detection from video
- Automatic cross-checking with repair shop estimates
- Fraudulent claims detection

---

## Technical Notes

| Component | Role |
|--------------|------|
| Step Functions | Workflow orchestration |
| Lambda (Image Analyzer) | Damage detection via Bedrock/Rekognition |
| Lambda (Damage Assessor) | Damage severity evaluation / cost estimation |
| Lambda (Report Generator) | Claims report generation via Bedrock |
| Amazon Athena | Reference / comparison of past case data |

### Fallback

| Scenario | Response |
|---------|------|
| Insufficient image analysis accuracy | Use pre-analyzed results |
| Bedrock latency | Display pre-generated reports |

---

*This document is a production guide for technical presentation demo videos.*

---

## Verified UI/UX Screenshots (2026-05-10 AWS Verification)

Following the same approach as Phase 7, capturing **UI/UX screens that insurance assessors actually use in daily operations**.
Technical screens (Step Functions graphs, etc.) are excluded.

### Output Destination Selection: Standard S3 vs FSxN S3AP

UC14 supports the `OutputDestination` parameter as of the 2026-05-10 update.
**Writing AI artifacts back to the same FSx volume** allows claims processing staff to
view damage evaluation JSON, OCR results, and claims reports within the claims case directory structure
("no data movement" pattern, also advantageous from a PII protection perspective).

```bash
# STANDARD_S3 mode (default, traditional behavior)
--parameter-overrides OutputDestination=STANDARD_S3 ...

# FSXN_S3AP mode (write AI artifacts back to FSx ONTAP volume)
--parameter-overrides \
  OutputDestination=FSXN_S3AP \
  OutputS3APPrefix=ai-outputs/ \
  ...
```

For AWS specification constraints and workarounds, refer to the ["AWS Specification Constraints and Workarounds"
section in the project README](../../README.md#aws-仕様上の制約と回避策).

### 1. Insurance Claims Report — Assessor Summary

Report integrating accident photo Rekognition analysis + estimate Textract OCR + assessment recommendation judgment.
With judgment `MANUAL_REVIEW` + 75% confidence, assessor reviews items that cannot be automated.

<!-- SCREENSHOT: uc14-claims-report.png
     Content: Insurance claims report (claim ID, damage summary, estimate correlation, recommended judgment)
            + Rekognition detected label list + Textract OCR results
     Masked: Account ID, bucket name -->
![UC14: Insurance Claims Report](../../docs/screenshots/masked/uc14-demo/uc14-claims-report.png)

### 2. S3 Output Bucket — Assessment Artifacts Overview

Screen where assessors review artifacts per claims case.
`assessments/` (Rekognition analysis) + `estimates/` (Textract OCR) + `reports/` (integrated report).

<!-- SCREENSHOT: uc14-s3-output-bucket.png
     Content: S3 console showing assessments/, estimates/, reports/ prefixes
     Masked: Account ID -->
![UC14: S3 Output Bucket](../../docs/screenshots/masked/uc14-demo/uc14-s3-output-bucket.png)

### Actual Measurements (2026-05-10 AWS Deployment Verification)

- **Step Functions Execution**: SUCCEEDED
- **Rekognition**: Detected `Maroon` 90.79%, `Business Card` 84.51%, etc. in accident photos
- **Textract**: OCR'd `Total: 1270.00 USD` etc. from estimate PDF via cross-region us-east-1
- **Generated Artifacts**: assessments/*.json, estimates/*.json, reports/*.txt
- **Actual Stack**: `fsxn-insurance-claims-demo` (ap-northeast-1, verified 2026-05-10)
