# Accident Photo Damage Assessment & Claims Report — Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | English | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

This demo showcases an automated damage assessment and claims report generation pipeline from accident photos. Image analysis-based damage evaluation and AI report generation streamline the assessment process.

**Core Message**: AI automatically analyzes accident photos, evaluating damage severity and instantly generating insurance claims reports.

**Target Duration**: 3–5 minutes

---

## Target Audience & Persona

| Item | Details |
|------|---------|
| **Role** | Claims Adjuster / Damage Assessor |
| **Daily Tasks** | Accident photo review, damage evaluation, claims calculation, report creation |
| **Challenge** | Need to rapidly process large volumes of claims |
| **Expected Outcome** | Faster assessment process with consistent evaluations |

### Persona: Claims Adjuster

- Processes 100+ insurance claims monthly
- Reviews photos to assess damage severity and create reports
- "I want to automate initial assessments so I can focus on complex cases"

---

## Demo Scenario: Vehicle Accident Damage Assessment

### Workflow Overview

```
Accident Photos    Image Analysis    Damage Assessment    Claims Report
(Multiple)     →   Damage         →  Severity          → AI Generated
                   Detection         Estimation
                   Part ID           Cost Estimate
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
> Over 100 insurance claims monthly. Each case requires reviewing multiple accident photos, evaluating damage severity, and creating reports. Manual processing can't keep up.

**Key Visual**: Claims case list, sample accident photos

### Section 2: Photo Upload (0:45–1:30)

**Narration Summary**:
> When accident photos are uploaded, the automated assessment pipeline triggers. Processed per case.

**Key Visual**: Photo upload → workflow auto-trigger

### Section 3: Damage Detection (1:30–2:30)

**Narration Summary**:
> AI analyzes photos and detects damage areas. Identifies damage type (dents, scratches, breakage) and location (bumper, door, fender, etc.).

**Key Visual**: Damage detection results, part mapping

### Section 4: Assessment (2:30–3:45)

**Narration Summary**:
> Evaluate damage severity, determine repair/replacement decisions, and calculate estimated costs. Compare with similar past cases.

**Key Visual**: Damage assessment results table, cost estimation

### Section 5: Claims Report (3:45–5:00)

**Narration Summary**:
> AI automatically generates an insurance claims report including damage summary, estimated costs, and recommended actions. Adjusters only need to review and approve.

**Key Visual**: AI-generated claims report (damage summary + cost estimate)

---

## Screen Capture Plan

| # | Screen | Section |
|---|--------|---------|
| 1 | Claims case list | Section 1 |
| 2 | Photo upload / pipeline trigger | Section 2 |
| 3 | Damage detection results | Section 3 |
| 4 | Damage assessment / cost estimation | Section 4 |
| 5 | Insurance claims report | Section 5 |

---

## Narration Outline

| Section | Time | Key Message |
|---------|------|-------------|
| Problem | 0:00–0:45 | "Manual assessment of 100 monthly claims is unsustainable" |
| Upload | 0:45–1:30 | "Photo upload starts automated assessment" |
| Detection | 1:30–2:30 | "AI auto-detects damage areas and types" |
| Assessment | 2:30–3:45 | "Auto-estimate damage severity and repair costs" |
| Report | 3:45–5:00 | "Auto-generate claims report, just review and approve" |

---

## Sample Data Requirements

| # | Data | Purpose |
|---|------|---------|
| 1 | Minor damage photos (5) | Basic assessment demo |
| 2 | Moderate damage photos (3) | Assessment accuracy demo |
| 3 | Severe damage photos (2) | Total loss determination demo |

---

## Timeline

### Achievable Within 1 Week

| Task | Duration |
|------|----------|
| Prepare sample photo data | 2 hours |
| Verify pipeline execution | 2 hours |
| Capture screenshots | 2 hours |
| Create narration script | 2 hours |
| Video editing | 4 hours |

### Future Enhancements

- Video-based damage detection
- Automatic cross-reference with repair shop estimates
- Fraud detection

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Workflow orchestration |
| Lambda (Image Analyzer) | Damage detection via Bedrock/Rekognition |
| Lambda (Damage Assessor) | Damage severity evaluation / cost estimation |
| Lambda (Report Generator) | Claims report generation via Bedrock |
| Amazon Athena | Historical case data reference/comparison |

### Fallback

| Scenario | Response |
|----------|----------|
| Image analysis accuracy issues | Use pre-analyzed results |
| Bedrock delay | Display pre-generated report |

---

*This document serves as a production guide for technical presentation demo videos.*
