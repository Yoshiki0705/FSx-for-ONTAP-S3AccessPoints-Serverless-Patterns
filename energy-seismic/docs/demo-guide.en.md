# Well Log Anomaly Detection & Compliance Reporting — Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | English | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

This demo showcases a well log data anomaly detection and compliance report generation pipeline. It automatically detects quality issues in well log data and efficiently creates regulatory reports.

**Core Message**: Automatically detect anomalies in well log data and instantly generate compliance reports conforming to regulatory requirements.

**Target Duration**: 3–5 minutes

---

## Target Audience & Persona

| Item | Details |
|------|---------|
| **Role** | Geoscience Engineer / Data Analyst / Compliance Officer |
| **Daily Tasks** | Well log data analysis, well evaluation, regulatory report creation |
| **Challenge** | Manual anomaly detection from large volumes of well log data is time-consuming |
| **Expected Outcome** | Automated data quality verification and efficient regulatory reporting |

### Persona: Geoscience Engineer

- Manages well log data from 50+ wells
- Regular reporting to regulatory authorities required
- "I want to auto-detect data anomalies and streamline report creation"

---

## Demo Scenario: Well Log Batch Analysis

### Workflow Overview

```
Well Log Data      Data Validation    Anomaly Detection    Compliance
(LAS/DLIS)     →   Quality Check   →  Statistical      →  Report
                    Format              Analysis            Generation
                    Verification        Outlier Detection
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1: Problem Statement (0:00–0:45)

**Narration Summary**:
> Well log data from 50 wells needs periodic quality verification and regulatory reporting. Manual analysis carries high risk of oversight.

**Key Visual**: Well log data file list (LAS/DLIS format)

### Section 2: Data Ingestion (0:45–1:30)

**Narration Summary**:
> Upload well log data files and launch the quality verification pipeline. Start with format validation.

**Key Visual**: Workflow trigger, data format verification

### Section 3: Anomaly Detection (1:30–2:30)

**Narration Summary**:
> Execute statistical anomaly detection on each log curve (GR, SP, Resistivity, etc.). Detect outliers by depth interval.

**Key Visual**: Anomaly detection in progress, log curve anomaly highlights

### Section 4: Results Review (2:30–3:45)

**Narration Summary**:
> Review detected anomalies by well and curve. Classify anomaly types (spikes, gaps, out-of-range).

**Key Visual**: Anomaly detection results table, per-well summary

### Section 5: Compliance Report (3:45–5:00)

**Narration Summary**:
> AI automatically generates a compliance report conforming to regulatory requirements. Includes data quality summary, anomaly response records, and recommended actions.

**Key Visual**: Compliance report (regulatory format compliant)

---

## Screen Capture Plan

| # | Screen | Section |
|---|--------|---------|
| 1 | Well log data file list | Section 1 |
| 2 | Pipeline trigger / format verification | Section 2 |
| 3 | Anomaly detection results | Section 3 |
| 4 | Per-well anomaly summary | Section 4 |
| 5 | Compliance report | Section 5 |

---

## Narration Outline

| Section | Time | Key Message |
|---------|------|-------------|
| Problem | 0:00–0:45 | "Manual quality verification of 50 wells' log data is unsustainable" |
| Ingestion | 0:45–1:30 | "Data upload automatically starts verification" |
| Detection | 1:30–2:30 | "Statistical methods detect anomalies in each curve" |
| Results | 2:30–3:45 | "Classify and review anomalies by well and curve" |
| Report | 3:45–5:00 | "AI auto-generates regulatory-compliant report" |

---

## Sample Data Requirements

| # | Data | Purpose |
|---|------|---------|
| 1 | Normal well log data (LAS format, 10 wells) | Baseline |
| 2 | Spike anomaly data (3) | Anomaly detection demo |
| 3 | Gap interval data (2) | Quality check demo |
| 4 | Out-of-range data (2) | Classification demo |

---

## Timeline

### Achievable Within 1 Week

| Task | Duration |
|------|----------|
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
|-----------|------|
| Step Functions | Workflow orchestration |
| Lambda (LAS Parser) | Well log data format analysis |
| Lambda (Anomaly Detector) | Statistical anomaly detection |
| Lambda (Report Generator) | Compliance report generation via Bedrock |
| Amazon Athena | Well log data aggregation/analysis |

### Fallback

| Scenario | Response |
|----------|----------|
| LAS parse failure | Use pre-analyzed data |
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
- 📸 **UI/UX Capture**: ✅ SUCCEEDED (Phase 8 Theme D, commit 2b958db — re-deployed after IAM S3AP fix, 2:59 all steps green)

### Existing Screenshots (from Phase 1-6)

![UC8 Step Functions Graph (SUCCEEDED)](../../docs/screenshots/masked/uc8-demo/step-functions-graph-succeeded.png)

![UC8 Step Functions Graph (zoomed)](../../docs/screenshots/masked/uc8-demo/step-functions-graph-zoomed.png)

### UI/UX Target Screens for Re-verification (Recommended Capture List)

- S3 output bucket (segy-metadata/, anomalies/, reports/)
- Athena query results (SEG-Y metadata statistics)
- Rekognition well log image labels
- Anomaly detection report

### Capture Guide

1. **Preparation**: Run `bash scripts/verify_phase7_prerequisites.sh` to check prerequisites
2. **Sample Data**: Upload sample files via S3 AP Alias, then start Step Functions workflow
3. **Capture** (close CloudShell/terminal, mask username in browser top-right)
4. **Mask**: Run `python3 scripts/mask_uc_demos.py <uc-dir>` for automated OCR masking
5. **Cleanup**: Run `bash scripts/cleanup_generic_ucs.sh <UC>` to delete stack
