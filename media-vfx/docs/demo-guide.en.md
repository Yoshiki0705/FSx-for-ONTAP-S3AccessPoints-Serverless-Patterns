# VFX Rendering Quality Check — Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | English | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

This demo showcases a VFX rendering output quality check pipeline. Automated frame verification enables early detection of artifacts and error frames.

**Core Message**: Automatically verify large volumes of rendered frames, instantly detecting quality issues and accelerating re-render decisions.

**Target Duration**: 3–5 minutes

---

## Target Audience & Persona

| Item | Details |
|------|---------|
| **Role** | VFX Supervisor / Rendering TD |
| **Daily Tasks** | Render job management, quality verification, shot approval |
| **Challenge** | Visual inspection of thousands of frames takes enormous time |
| **Expected Outcome** | Automated problem frame detection and faster re-render decisions |

### Persona: VFX Supervisor

- 50+ shots per project, each shot 100–500 frames
- Quality verification after render completion is the bottleneck
- "I want to automatically detect black frames, excessive noise, and missing textures"

---

## Demo Scenario: Rendering Batch Quality Verification

### Workflow Overview

```
Render Output     Frame Analysis    Quality Assessment    QC Report
(EXR/PNG)     →   Metadata       →  Anomaly Detection → Per-Shot
                   Extraction        (Statistical)       Summary
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
> Thousands of frames output from the render farm. Visually checking for black frames, noise, and missing textures is impractical.

**Key Visual**: Render output folder (large number of EXR files)

### Section 2: Pipeline Trigger (0:45–1:30)

**Narration Summary**:
> After render job completion, the quality check pipeline auto-triggers. Parallel processing per shot.

**Key Visual**: Workflow trigger, shot list

### Section 3: Frame Analysis (1:30–2:30)

**Narration Summary**:
> Calculate pixel statistics (mean luminance, variance, histogram) for each frame. Also check inter-frame consistency.

**Key Visual**: Frame analysis in progress, pixel statistics graphs

### Section 4: Quality Assessment (2:30–3:45)

**Narration Summary**:
> Detect statistical outliers and identify problem frames. Classify black frames (zero luminance), excessive noise (abnormal variance), etc.

**Key Visual**: Problem frame list, category classification

### Section 5: QC Report (3:45–5:00)

**Narration Summary**:
> Generate per-shot QC reports. Present frame ranges requiring re-render and estimated causes.

**Key Visual**: AI-generated QC report (per-shot summary + recommended actions)

---

## Screen Capture Plan

| # | Screen | Section |
|---|--------|---------|
| 1 | Render output folder | Section 1 |
| 2 | Pipeline trigger screen | Section 2 |
| 3 | Frame analysis progress | Section 3 |
| 4 | Problem frame detection results | Section 4 |
| 5 | QC report | Section 5 |

---

## Narration Outline

| Section | Time | Key Message |
|---------|------|-------------|
| Problem | 0:00–0:45 | "Visual inspection of thousands of frames is impractical" |
| Trigger | 0:45–1:30 | "Render completion automatically starts QC" |
| Analysis | 1:30–2:30 | "Pixel statistics quantitatively evaluate frame quality" |
| Assessment | 2:30–3:45 | "Automatically classify and identify problem frames" |
| Report | 3:45–5:00 | "Instantly support re-render decisions" |

---

## Sample Data Requirements

| # | Data | Purpose |
|---|------|---------|
| 1 | Normal frames (100) | Baseline |
| 2 | Black frames (3) | Anomaly detection demo |
| 3 | Excessive noise frames (5) | Quality assessment demo |
| 4 | Missing texture frames (2) | Classification demo |

---

## Timeline

### Achievable Within 1 Week

| Task | Duration |
|------|----------|
| Prepare sample frame data | 3 hours |
| Verify pipeline execution | 2 hours |
| Capture screenshots | 2 hours |
| Create narration script | 2 hours |
| Video editing | 4 hours |

### Future Enhancements

- Deep learning-based artifact detection
- Render farm integration (automatic re-rendering)
- Shot tracking system integration

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Workflow orchestration |
| Lambda (Frame Analyzer) | Frame metadata/pixel statistics extraction |
| Lambda (Quality Checker) | Statistical quality assessment |
| Lambda (Report Generator) | QC report generation via Bedrock |
| Amazon Athena | Frame statistics aggregation/analysis |

### Fallback

| Scenario | Response |
|----------|----------|
| Large frame processing delay | Switch to thumbnail analysis |
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
- 📸 **UI/UX**: Not yet captured

### Existing Screenshots (from Phase 1-6)

*(None applicable. Please capture during re-verification.)*

### UI/UX Target Screens for Re-verification (Recommended Capture List)

- (To be defined during re-verification)

### Capture Guide

1. **Preparation**: Run `bash scripts/verify_phase7_prerequisites.sh` to check prerequisites
2. **Sample Data**: Upload sample files via S3 AP Alias, then start Step Functions workflow
3. **Capture** (close CloudShell/terminal, mask username in browser top-right)
4. **Mask**: Run `python3 scripts/mask_uc_demos.py <uc-dir>` for automated OCR masking
5. **Cleanup**: Run `bash scripts/cleanup_generic_ucs.sh <UC>` to delete stack
