# Well Logging Data Anomaly Detection and Compliance Report — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | English | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> Note: This translation is produced by Amazon Bedrock Claude. Contributions to improve translation quality are welcome.

## Executive Summary

This demo demonstrates a well log data anomaly detection and compliance report generation pipeline. It automatically detects quality issues in well log data and efficiently creates regulatory reports.

**Core Demo Message**: Automatically detect anomalies in well log data and instantly generate compliance reports that meet regulatory requirements.

**Estimated Time**: 3–5 minutes

---

## Target Audience & Persona

| Item | Details |
|------|------|
| **Role** | Geoscience Engineer / Data Analyst / Compliance Officer |
| **Daily Work** | Well log data analysis, well evaluation, regulatory report creation |
| **Challenge** | Manually detecting anomalies from large volumes of well log data is time-consuming |
| **Expected Outcome** | Automated data quality verification and streamlined regulatory reporting |

### Persona: Matsumoto-san (Geoscience Engineer)

- Manages well log data for 50+ wells
- Requires periodic reporting to regulatory authorities
- "I want to automatically detect data anomalies and streamline report creation"

---

## Demo Scenario: Well Log Data Batch Analysis

### Overall Workflow

```
Well Log Data        Data Validation       Anomaly Detection          Compliance
(LAS/DLIS)      →   Quality Check     →   Statistical Analysis  →    Report Generation
                     Format                Outlier Detection
```

---

## Storyboard (5 Sections / 3–5 minutes)

### Section 1: Problem Statement (0:00–0:45)

**Narration Summary**:
> We need to periodically verify the quality of well log data from 50 wells and report to regulatory authorities. Manual analysis carries a high risk of oversight.

**Key Visual**: List of well log data files (LAS/DLIS format)

### Section 2: Data Ingestion (0:45–1:30)

**Narration Summary**:
> Upload well log data files and initiate the quality verification pipeline. Start with format validation.

**Key Visual**: Workflow initiation, data format validation

### Section 3: Anomaly Detection (1:30–2:30)

**Narration Summary**:
> Execute statistical anomaly detection on each log curve (GR, SP, Resistivity, etc.). Detect outliers for each depth interval.

**Key Visual**: Anomaly detection in progress, log curve anomaly highlights

### Section 4: Results Review (2:30–3:45)

**Narration Summary**:
> Review detected anomalies by well and by curve. Classify anomaly types (spikes, missing data, range violations).

**Key Visual**: Anomaly detection results table, per-well summary

### Section 5: Compliance Report (3:45–5:00)

**Narration Summary**:
> AI automatically generates a compliance report that meets regulatory requirements. Includes data quality summary, anomaly response records, and recommended actions.

**Key Visual**: Compliance report (regulatory format compliant)

---

## Screen Capture Plan

| # | Screen | Section |
|---|------|-----------|
| 1 | Well log data file list | Section 1 |
| 2 | Pipeline initiation & format validation | Section 2 |
| 3 | Anomaly detection processing results | Section 3 |
| 4 | Per-well anomaly summary | Section 4 |
| 5 | Compliance report | Section 5 |

---

## Narration Outline

| Section | Time | Key Message |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "Manual quality verification of well log data from 50 wells has reached its limit" |
| Ingestion | 0:45–1:30 | "Validation starts automatically upon data upload" |
| Detection | 1:30–2:30 | "Detect anomalies in each curve using statistical methods" |
| Results | 2:30–3:45 | "Classify and review anomalies by well and by curve" |
| Report | 3:45–5:00 | "AI automatically generates regulatory-compliant reports" |

---

## Sample Data Requirements

| # | Data | Purpose |
|---|--------|------|
| 1 | Normal well log data (LAS format, 10 wells) | Baseline |
| 2 | Spike anomaly data (3 cases) | Anomaly detection demo |
| 3 | Missing interval data (2 cases) | Quality check demo |
| 4 | Range violation data (2 cases) | Classification demo |

---

## Timeline

### Achievable Within 1 Week

| Task | Time Required |
|--------|---------|
| Prepare sample well log data | 3 hours |
| Verify pipeline execution | 2 hours |
| Capture screenshots | 2 hours |
| Create narration script | 2 hours |
| Video editing | 4 hours |

### Future Enhancements

- Real-time drilling data monitoring
- Automated stratigraphic correlation
- 3D geological model integration

---

## Technical Notes

| Component | Role |
|--------------|------|
| Step Functions | Workflow orchestration |
| Lambda (LAS Parser) | Well log data format parsing |
| Lambda (Anomaly Detector) | Statistical anomaly detection |
| Lambda (Report Generator) | Compliance report generation via Bedrock |
| Amazon Athena | Well log data aggregation and analysis |

### Fallback

| Scenario | Response |
|---------|------|
| LAS parsing failure | Use pre-parsed data |
| Bedrock latency | Display pre-generated report |

---

*This document is a production guide for technical presentation demo videos.*

---

## Verified UI/UX Screenshots

Following the same approach as Phase 7 UC15/16/17 and UC6/11/14 demos, we target **UI/UX screens that end users actually see in their daily work**. Technical views (Step Functions graphs, CloudFormation stack events, etc.) are consolidated in `docs/verification-results-*.md`.

### Verification Status for This Use Case

- ✅ **E2E Execution**: Verified in Phase 1-6 (see root README)
- 📸 **UI/UX Re-capture**: ✅ Captured in 2026-05-10 redeployment verification (UC8 Step Functions graph, Lambda execution success confirmed)
- 🔄 **Reproduction Method**: See "Capture Guide" at the end of this document

### Captured in 2026-05-10 Redeployment Verification (UI/UX Focus)

#### UC8 Step Functions Graph view (SUCCEEDED)

![UC8 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc8-demo/uc8-stepfunctions-graph.png)

Step Functions Graph view is the most critical end-user screen that visualizes the execution status of each Lambda / Parallel / Map state with colors.

### Existing Screenshots (Relevant from Phase 1-6)

#### UC8 Step Functions Graph (SUCCEEDED — Re-captured After Phase 8 IAM Fix)

![UC8 Step Functions Graph (SUCCEEDED)](../../docs/screenshots/masked/uc8-demo/step-functions-graph-succeeded.png)

Redeployed after IAM S3AP fix. All steps SUCCEEDED (2:59).

#### UC8 Step Functions Graph (Zoomed View — Each Step Detail)

![UC8 Step Functions Graph (Zoomed View)](../../docs/screenshots/masked/uc8-demo/step-functions-graph-zoomed.png)

### UI/UX Target Screens for Re-verification (Recommended Capture List)

- S3 output bucket (segy-metadata/, anomalies/, reports/)
- Athena query results (SEG-Y metadata statistics)
- Rekognition well log image labels
- Anomaly detection reports

### Capture Guide

1. **Preparation**:
   - Verify prerequisites with `bash scripts/verify_phase7_prerequisites.sh` (check for shared VPC/S3 AP)
   - Package Lambda with `UC=energy-seismic bash scripts/package_generic_uc.sh`
   - Deploy with `bash scripts/deploy_generic_ucs.sh UC8`

2. **Sample Data Placement**:
   - Upload sample files to `seismic/` prefix via S3 AP Alias
   - Start Step Functions `fsxn-energy-seismic-demo-workflow` (input `{}`)

3. **Capture** (close CloudShell/terminal, mask username in browser top-right):
   - Overview of S3 output bucket `fsxn-energy-seismic-demo-output-<account>`
   - AI/ML output JSON preview (refer to `build/preview_*.html` format)
   - SNS email notification (if applicable)

4. **Masking**:
   - Auto-mask with `python3 scripts/mask_uc_demos.py energy-seismic-demo`
   - Apply additional masking as needed per `docs/screenshots/MASK_GUIDE.md`

5. **Cleanup**:
   - Delete with `bash scripts/cleanup_generic_ucs.sh UC8`
   - VPC Lambda ENI release takes 15-30 minutes (AWS specification)
