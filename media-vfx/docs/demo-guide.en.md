# VFX Rendering Quality Check — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | English | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> Note: This translation is produced by Amazon Bedrock Claude. Contributions to improve translation quality are welcome.

## Executive Summary

This demo demonstrates a quality check pipeline for VFX rendering output. Automatic validation of rendering frames enables early detection of artifacts and error frames.

**Core Demo Message**: Automatically validate large volumes of rendering frames and instantly detect quality issues. Accelerate re-rendering decisions.

**Estimated Duration**: 3–5 minutes

---

## Target Audience & Persona

| Item | Details |
|------|------|
| **Role** | VFX Supervisor / Rendering TD |
| **Daily Work** | Rendering job management, quality verification, shot approval |
| **Challenge** | Visual inspection of thousands of frames takes enormous time |
| **Expected Outcome** | Automatic detection of problem frames and accelerated re-rendering decisions |

### Persona: Nakamura-san (VFX Supervisor)

- 50+ shots per project, each shot 100–500 frames
- Quality verification after rendering completion is a bottleneck
- "Want to automatically detect black frames, excessive noise, missing textures"

---

## Demo Scenario: Rendering Batch Quality Verification

### Overall Workflow

```
Rendering Output     Frame Analysis      Quality Assessment      QC Report
(EXR/PNG)       →   Metadata        →   Anomaly Detection  →    Per-Shot
                    Extraction          (Statistical Analysis)   Summary
```

---

## Storyboard (5 Sections / 3–5 minutes)

### Section 1: Problem Statement (0:00–0:45)

**Narration Summary**:
> Thousands of frames output from the rendering farm. Visual inspection of issues like black frames, noise, missing textures is impractical.

**Key Visual**: Rendering output folder (large volume of EXR files)

### Section 2: Pipeline Trigger (0:45–1:30)

**Narration Summary**:
> After rendering job completion, quality check pipeline automatically starts. Parallel processing per shot.

**Key Visual**: Workflow launch, shot list

### Section 3: Frame Analysis (1:30–2:30)

**Narration Summary**:
> Calculate pixel statistics (average luminance, variance, histogram) for each frame. Check inter-frame consistency as well.

**Key Visual**: Frame analysis in progress, pixel statistics graph

### Section 4: Quality Assessment (2:30–3:45)

**Narration Summary**:
> Detect statistical outliers and identify problem frames. Classify black frames (zero luminance), excessive noise (abnormal variance), etc.

**Key Visual**: Problem frame list, classification by category

### Section 5: QC Report (3:45–5:00)

**Narration Summary**:
> Generate per-shot QC report. Present frame ranges requiring re-rendering and estimated causes.

**Key Visual**: AI-generated QC report (per-shot summary + recommended actions)

---

## Screen Capture Plan

| # | Screen | Section |
|---|------|-----------|
| 1 | Rendering output folder | Section 1 |
| 2 | Pipeline launch screen | Section 2 |
| 3 | Frame analysis progress | Section 3 |
| 4 | Problem frame detection results | Section 4 |
| 5 | QC report | Section 5 |

---

## Narration Outline

| Section | Time | Key Message |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "Visual inspection of thousands of frames is impractical" |
| Trigger | 0:45–1:30 | "QC automatically starts upon rendering completion" |
| Analysis | 1:30–2:30 | "Quantitatively evaluate frame quality with pixel statistics" |
| Assessment | 2:30–3:45 | "Automatically classify and identify problem frames" |
| Report | 3:45–5:00 | "Immediately support re-rendering decisions" |

---

## Sample Data Requirements

| # | Data | Purpose |
|---|--------|------|
| 1 | Normal frames (100 images) | Baseline |
| 2 | Black frames (3 images) | Anomaly detection demo |
| 3 | Excessive noise frames (5 images) | Quality assessment demo |
| 4 | Missing texture frames (2 images) | Classification demo |

---

## Timeline

### Achievable Within 1 Week

| Task | Time Required |
|--------|---------|
| Sample frame data preparation | 3 hours |
| Pipeline execution verification | 2 hours |
| Screen capture acquisition | 2 hours |
| Narration script creation | 2 hours |
| Video editing | 4 hours |

### Future Enhancements

- Artifact detection using deep learning
- Rendering farm integration (automatic re-rendering)
- Shot tracking system integration

---

## Technical Notes

| Component | Role |
|--------------|------|
| Step Functions | Workflow orchestration |
| Lambda (Frame Analyzer) | Frame metadata and pixel statistics extraction |
| Lambda (Quality Checker) | Statistical quality assessment |
| Lambda (Report Generator) | QC report generation via Bedrock |
| Amazon Athena | Aggregation and analysis of frame statistics |

### Fallback

| Scenario | Response |
|---------|------|
| Large frame processing delay | Switch to thumbnail analysis |
| Bedrock delay | Display pre-generated report |

---

*This document is a production guide for technical presentation demo videos.*

---

## About Output Destination: FSxN S3 Access Point (Pattern A)

UC4 media-vfx is classified as **Pattern A: Native S3AP Output**
(see `docs/output-destination-patterns.md`).

**Design**: Rendering metadata and frame quality assessments are all written back via FSxN S3 Access Point to
the **same FSx ONTAP volume** as the original rendering assets. No standard S3 bucket is
created ("no data movement" pattern).

**CloudFormation Parameters**:
- `S3AccessPointAlias`: S3 AP Alias for input data reading
- `S3AccessPointOutputAlias`: S3 AP Alias for output writing (can be same as input)

**Deployment Example**:
```bash
aws cloudformation deploy \
  --template-file media-vfx/template-deploy.yaml \
  --stack-name fsxn-media-vfx-demo \
  --parameter-overrides \
    S3AccessPointAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    S3AccessPointOutputAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    ... (other required parameters)
```

**View from SMB/NFS Users**:
```
/vol/renders/
  ├── shot_001/frame_0001.exr         # Original render frame
  └── qc/shot_001/                     # Frame quality assessment (within same volume)
      └── frame_0001_qc.json
```

For AWS specification constraints, see
[the "AWS Specification Constraints and Workarounds" section in the project README](../../README.md#aws-仕様上の制約と回避策)
and [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md).

---

## Verified UI/UX Screenshots

Following the same policy as Phase 7 UC15/16/17 and UC6/11/14 demos, targeting **UI/UX screens that end users
actually see in daily work**. Technical views (Step Functions graph, CloudFormation
stack events, etc.) are consolidated in `docs/verification-results-*.md`.

### Verification Status for This Use Case

- ⚠️ **E2E Verification**: Partial functionality only (additional verification recommended in production)
- 📸 **UI/UX Capture**: ✅ SFN Graph completed (Phase 8 Theme D, commit 3c90042)

### Existing Screenshots (Applicable from Phase 1-6)

![UC4 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc4-demo/step-functions-graph-succeeded.png)

![UC4 Step Functions Graph (Zoomed view — each step detail)](../../docs/screenshots/masked/uc4-demo/step-functions-graph-zoomed.png)

### UI/UX Target Screens for Re-verification (Recommended Capture List)

- (To be defined during re-verification)

### Capture Guide

1. **Preparation**:
   - Verify prerequisites with `bash scripts/verify_phase7_prerequisites.sh` (check for shared VPC/S3 AP)
   - Package Lambda with `UC=media-vfx bash scripts/package_generic_uc.sh`
   - Deploy with `bash scripts/deploy_generic_ucs.sh UC4`

2. **Sample Data Placement**:
   - Upload sample files to `renders/` prefix via S3 AP Alias
   - Start Step Functions `fsxn-media-vfx-demo-workflow` (input `{}`)

3. **Capture** (close CloudShell/terminal, mask username in browser top-right):
   - Overview of S3 output bucket `fsxn-media-vfx-demo-output-<account>`
   - AI/ML output JSON preview (refer to `build/preview_*.html` format)
   - SNS email notification (if applicable)

4. **Masking**:
   - Auto-mask with `python3 scripts/mask_uc_demos.py media-vfx-demo`
   - Apply additional masking as needed following `docs/screenshots/MASK_GUIDE.md`

5. **Cleanup**:
   - Delete with `bash scripts/cleanup_generic_ucs.sh UC4`
   - VPC Lambda ENI release takes 15-30 minutes (AWS specification)
