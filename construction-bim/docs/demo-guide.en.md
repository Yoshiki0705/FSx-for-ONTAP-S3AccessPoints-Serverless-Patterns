# BIM Model Change Detection & Safety Compliance — Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | English | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

This demo showcases a BIM model change detection and safety compliance check pipeline. It automatically detects design changes and verifies conformance to building safety standards.

**Core Message**: Automatically track BIM model changes and instantly detect safety standard violations, shortening design review cycles.

**Target Duration**: 3–5 minutes

---

## Target Audience & Persona

| Item | Details |
|------|---------|
| **Role** | BIM Manager / Structural Design Engineer |
| **Daily Tasks** | BIM model management, design change review, compliance verification |
| **Challenge** | Difficult to track changes from multiple teams and verify standard conformance |
| **Expected Outcome** | Automated change detection and efficient safety standard checking |

### Persona: BIM Manager

- Large construction project with 20+ design teams working in parallel
- Must verify daily design changes don't impact safety standards
- "I want safety checks to run automatically whenever changes are made"

---

## Demo Scenario: Automated Design Change Detection & Safety Verification

### Workflow Overview

```
BIM Model Update    Change Detection    Compliance          Review Report
(IFC/RVT)      →   Diff Analysis    →  Rule Matching   →   AI Generated
                    Element Comparison   Safety Standard
                                         Check
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
> 20 teams updating BIM models in parallel on a large project. Manual verification that changes don't violate safety standards can't keep up.

**Key Visual**: BIM model file list, multiple team update history

### Section 2: Change Detection (0:45–1:30)

**Narration Summary**:
> Detect model file updates and automatically analyze differences from previous version. Identify changed elements (structural members, equipment placement, etc.).

**Key Visual**: Change detection trigger, diff analysis start

### Section 3: Compliance Check (1:30–2:30)

**Narration Summary**:
> Automatically match safety standard rules against changed elements. Verify conformance for seismic standards, fire compartments, evacuation routes, etc.

**Key Visual**: Rule matching in progress, check item list

### Section 4: Results Analysis (2:30–3:45)

**Narration Summary**:
> Review verification results. Display violations, impact scope, and severity in a list.

**Key Visual**: Violation detection results table, severity classification

### Section 5: Review Report (3:45–5:00)

**Narration Summary**:
> AI generates a design review report presenting violation details, remediation proposals, and affected design elements.

**Key Visual**: AI-generated review report

---

## Screen Capture Plan

| # | Screen | Section |
|---|--------|---------|
| 1 | BIM model file list | Section 1 |
| 2 | Change detection / diff display | Section 2 |
| 3 | Compliance check progress | Section 3 |
| 4 | Violation detection results | Section 4 |
| 5 | AI review report | Section 5 |

---

## Narration Outline

| Section | Time | Key Message |
|---------|------|-------------|
| Problem | 0:00–0:45 | "Can't keep up with change tracking and safety verification" |
| Detection | 0:45–1:30 | "Auto-detect model updates and analyze differences" |
| Compliance | 1:30–2:30 | "Automatically match safety standard rules" |
| Results | 2:30–3:45 | "Instantly grasp violations and impact scope" |
| Report | 3:45–5:00 | "AI presents remediation proposals and impact analysis" |

---

## Sample Data Requirements

| # | Data | Purpose |
|---|------|---------|
| 1 | Base BIM model (IFC format) | Comparison source |
| 2 | Modified model (with structural changes) | Diff detection demo |
| 3 | Safety standard violation models (3) | Compliance demo |

---

## Timeline

### Achievable Within 1 Week

| Task | Duration |
|------|----------|
| Prepare sample BIM data | 3 hours |
| Verify pipeline execution | 2 hours |
| Capture screenshots | 2 hours |
| Create narration script | 2 hours |
| Video editing | 4 hours |

### Future Enhancements

- 3D visualization integration
- Real-time change notifications
- Construction phase consistency checking

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Workflow orchestration |
| Lambda (Change Detector) | BIM model diff analysis |
| Lambda (Compliance Checker) | Safety standard rule matching |
| Lambda (Report Generator) | Review report generation via Bedrock |
| Amazon Athena | Change history / violation data aggregation |

### Fallback

| Scenario | Response |
|----------|----------|
| IFC parse failure | Use pre-analyzed data |
| Rule matching delay | Display pre-verified results |

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

![UC10 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc10-demo/step-functions-graph-succeeded.png)

![UC10 Step Functions Graph (zoomed — per-step detail)](../../docs/screenshots/masked/uc10-demo/step-functions-graph-zoomed.png)

### UI/UX Target Screens for Re-verification (Recommended Capture List)

- S3 output bucket (drawings-ocr/, bim-metadata/, safety-reports/)
- Textract drawing OCR results (Cross-Region)
- BIM version diff report
- Bedrock safety compliance check

### Capture Guide

1. **Preparation**: Run `bash scripts/verify_phase7_prerequisites.sh` to check prerequisites
2. **Sample Data**: Upload sample files via S3 AP Alias, then start Step Functions workflow
3. **Capture** (close CloudShell/terminal, mask username in browser top-right)
4. **Mask**: Run `python3 scripts/mask_uc_demos.py <uc-dir>` for automated OCR masking
5. **Cleanup**: Run `bash scripts/cleanup_generic_ucs.sh <UC>` to delete stack
