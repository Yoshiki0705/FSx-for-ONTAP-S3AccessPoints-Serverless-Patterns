# BIM Model Change Detection and Safety Compliance — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | English | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> Note: This translation is produced by Amazon Bedrock Claude. Contributions to improve translation quality are welcome.

## Executive Summary

This demo demonstrates a BIM model change detection and safety compliance check pipeline. It automatically detects design changes and verifies compliance with building codes.

**Core Demo Message**: Automatically track BIM model changes and instantly detect safety standard violations. Shorten design review cycles.

**Estimated Duration**: 3–5 minutes

---

## Target Audience & Persona

| Item | Details |
|------|------|
| **Role** | BIM Manager / Structural Design Engineer |
| **Daily Work** | BIM model management, design change review, compliance verification |
| **Challenge** | Difficult to track design changes from multiple teams and verify standard compliance |
| **Expected Outcome** | Streamline automatic change detection and safety standard checks |

### Persona: Kimura-san (BIM Manager)

- 20+ design teams working in parallel on large-scale construction projects
- Need to verify that daily design changes do not impact safety standards
- "I want to automatically run safety checks when changes occur"

---

## Demo Scenario: Automatic Detection and Safety Verification of Design Changes

### Overall Workflow

```
BIM Model Update     Change Detection     Compliance          Review Report
(IFC/RVT)       →   Diff Analysis    →   Rule Matching   →   AI Generation
                    Element Comparison   Safety Standard Check
```

---

## Storyboard (5 Sections / 3–5 minutes)

### Section 1: Problem Statement (0:00–0:45)

**Narration Summary**:
> In large-scale projects, 20 teams update BIM models in parallel. Manual verification cannot keep up with checking whether changes violate safety standards.

**Key Visual**: BIM model file list, update history from multiple teams

### Section 2: Change Detection (0:45–1:30)

**Narration Summary**:
> Detect model file updates and automatically analyze differences from the previous version. Identify changed elements (structural members, equipment placement, etc.).

**Key Visual**: Change detection trigger, diff analysis start

### Section 3: Compliance Check (1:30–2:30)

**Narration Summary**:
> Automatically match safety standard rules against changed elements. Verify compliance with seismic standards, fire compartments, evacuation routes, etc.

**Key Visual**: Rule matching in progress, checklist items

### Section 4: Results Analysis (2:30–3:45)

**Narration Summary**:
> Review verification results. Display violation items, impact scope, and severity in a list.

**Key Visual**: Violation detection results table, classification by severity

### Section 5: Review Report (3:45–5:00)

**Narration Summary**:
> AI generates a design review report. Presents violation details, corrective measures, and other affected design elements.

**Key Visual**: AI-generated review report

---

## Screen Capture Plan

| # | Screen | Section |
|---|------|-----------|
| 1 | BIM model file list | Section 1 |
| 2 | Change detection / diff display | Section 2 |
| 3 | Compliance check progress | Section 3 |
| 4 | Violation detection results | Section 4 |
| 5 | AI review report | Section 5 |

---

## Narration Outline

| Section | Time | Key Message |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "Cannot keep up with tracking changes and safety verification in parallel work" |
| Detection | 0:45–1:30 | "Automatically detect model updates and analyze differences" |
| Compliance | 1:30–2:30 | "Automatically match safety standard rules" |
| Results | 2:30–3:45 | "Instantly understand violation items and impact scope" |
| Report | 3:45–5:00 | "AI presents corrective measures and impact analysis" |

---

## Sample Data Requirements

| # | Data | Purpose |
|---|--------|------|
| 1 | Base BIM model (IFC format) | Comparison source |
| 2 | Modified model (with structural changes) | Diff detection demo |
| 3 | Safety standard violation model (3 cases) | Compliance demo |

---

## Timeline

### Achievable Within 1 Week

| Task | Time Required |
|--------|---------|
| Prepare sample BIM data | 3 hours |
| Verify pipeline execution | 2 hours |
| Capture screenshots | 2 hours |
| Create narration script | 2 hours |
| Video editing | 4 hours |

### Future Enhancements

- 3D visualization integration
- Real-time change notifications
- Consistency check with construction phase

---

## Technical Notes

| Component | Role |
|--------------|------|
| Step Functions | Workflow orchestration |
| Lambda (Change Detector) | BIM model diff analysis |
| Lambda (Compliance Checker) | Safety standard rule matching |
| Lambda (Report Generator) | Review report generation via Bedrock |
| Amazon Athena | Aggregation of change history and violation data |

### Fallback

| Scenario | Response |
|---------|------|
| IFC parse failure | Use pre-analyzed data |
| Rule matching delay | Display pre-verified results |

---

*This document is a production guide for demo videos for technical presentations.*

---

## About Output Destination: Selectable via OutputDestination (Pattern B)

UC10 construction-bim supports the `OutputDestination` parameter as of the 2026-05-10 update
(see `docs/output-destination-patterns.md`).

**Target Workload**: Construction BIM / Drawing OCR / Safety Compliance Check

**Two Modes**:

### STANDARD_S3 (Default, traditional behavior)
Creates a new S3 bucket (`${AWS::StackName}-output-${AWS::AccountId}`) and
writes AI artifacts there.

```bash
aws cloudformation deploy \
  --template-file construction-bim/template-deploy.yaml \
  --stack-name fsxn-construction-bim-demo \
  --parameter-overrides \
    OutputDestination=STANDARD_S3 \
    ... (other required parameters)
```

### FSXN_S3AP ("no data movement" pattern)
Writes AI artifacts back to the **same FSx ONTAP volume** as the original data via FSxN S3 Access Point.
SMB/NFS users can directly view AI artifacts within the directory structure used in daily work.
No standard S3 bucket is created.

```bash
aws cloudformation deploy \
  --template-file construction-bim/template-deploy.yaml \
  --stack-name fsxn-construction-bim-demo \
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

Following the same policy as Phase 7 UC15/16/17 and UC6/11/14 demos, targeting **UI/UX screens that end users actually see in daily work**. Technical views (Step Functions graphs, CloudFormation stack events, etc.) are consolidated in `docs/verification-results-*.md`.

### Verification Status for This Use Case

- ✅ **E2E Execution**: Verified in Phase 1-6 (see root README)
- 📸 **UI/UX Re-capture**: ✅ Captured in 2026-05-10 redeployment verification (confirmed UC10 Step Functions graph, Lambda execution success)
- 🔄 **Reproduction Method**: See "Capture Guide" at the end of this document

### Captured in 2026-05-10 Redeployment Verification (UI/UX Focus)

#### UC10 Step Functions Graph view (SUCCEEDED)

![UC10 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc10-demo/uc10-stepfunctions-graph.png)

Step Functions Graph view is the most important end-user screen that visualizes the execution status of each Lambda / Parallel / Map state with colors.

### Existing Screenshots (Applicable from Phase 1-6)

![UC10 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc10-demo/step-functions-graph-succeeded.png)

![UC10 Step Functions Graph (Zoomed view — each step detail)](../../docs/screenshots/masked/uc10-demo/step-functions-graph-zoomed.png)

### UI/UX Target Screens for Re-verification (Recommended Capture List)

- S3 output bucket (drawings-ocr/, bim-metadata/, safety-reports/)
- Textract drawing OCR results (Cross-Region)
- BIM version diff report
- Bedrock safety compliance check

### Capture Guide

1. **Preparation**:
   - Verify prerequisites with `bash scripts/verify_phase7_prerequisites.sh` (check for shared VPC/S3 AP)
   - Package Lambda with `UC=construction-bim bash scripts/package_generic_uc.sh`
   - Deploy with `bash scripts/deploy_generic_ucs.sh UC10`

2. **Place Sample Data**:
   - Upload sample files to `drawings/` prefix via S3 AP Alias
   - Start Step Functions `fsxn-construction-bim-demo-workflow` (input `{}`)

3. **Capture** (close CloudShell/terminal, mask username in browser top-right):
   - Overview of S3 output bucket `fsxn-construction-bim-demo-output-<account>`
   - Preview of AI/ML output JSON (refer to `build/preview_*.html` format)
   - SNS email notification (if applicable)

4. **Masking**:
   - Auto-mask with `python3 scripts/mask_uc_demos.py construction-bim-demo`
   - Apply additional masking as needed following `docs/screenshots/MASK_GUIDE.md`

5. **Cleanup**:
   - Delete with `bash scripts/cleanup_generic_ucs.sh UC10`
   - VPC Lambda ENI release takes 15-30 minutes (AWS specification)
