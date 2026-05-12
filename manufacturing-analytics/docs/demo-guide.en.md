# IoT Sensor Anomaly Detection and Quality Inspection — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | English | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> Note: This translation is produced by Amazon Bedrock Claude. Contributions to improve translation quality are welcome.

## Executive Summary

This demo demonstrates a workflow that automatically detects anomalies from IoT sensor data on manufacturing lines and generates quality inspection reports.

**Core Demo Message**: Automatically detect anomaly patterns in sensor data to achieve early detection of quality issues and preventive maintenance.

**Estimated Duration**: 3–5 minutes

---

## Target Audience & Persona

| Item | Details |
|------|---------|
| **Role** | Manufacturing Department Manager / Quality Control Engineer |
| **Daily Tasks** | Production line monitoring, quality inspection, equipment maintenance planning |
| **Challenges** | Missing sensor data anomalies, defective products flowing to downstream processes |
| **Expected Outcomes** | Early anomaly detection and quality trend visualization |

### Persona: Suzuki-san (Quality Control Engineer)

- Monitors 100+ sensors across 5 manufacturing lines
- Threshold-based alerts generate many false positives, often missing true anomalies
- "I want to detect only statistically significant anomalies"

---

## Demo Scenario: Sensor Anomaly Detection Batch Analysis

### Overall Workflow

```
Sensor Data         Data Collection    Anomaly Detection    Quality Report
(CSV/Parquet)  →   Preprocessing  →   Statistical      →   AI Generation
                   Normalization       Analysis
                                      (Outlier Detection)
```

---

## Storyboard (5 Sections / 3–5 minutes)

### Section 1: Problem Statement (0:00–0:45)

**Narration Summary**:
> Large volumes of data are generated daily from 100+ sensors on manufacturing lines. Simple threshold alerts produce many false positives, risking missed detection of true anomalies.

**Key Visual**: Time series graph of sensor data, alert overload situation

### Section 2: Data Ingestion (0:45–1:30)

**Narration Summary**:
> When sensor data accumulates on the file server, the analysis pipeline automatically starts.

**Key Visual**: Data file placement → Workflow activation

### Section 3: Anomaly Detection (1:30–2:30)

**Narration Summary**:
> Calculate anomaly scores for each sensor using statistical methods (moving average, standard deviation, IQR). Also perform correlation analysis across multiple sensors.

**Key Visual**: Anomaly detection algorithm in progress, anomaly score heatmap

### Section 4: Quality Inspection (2:30–3:45)

**Narration Summary**:
> Analyze detected anomalies from a quality inspection perspective. Identify which line and which process has issues.

**Key Visual**: Athena query results — anomaly distribution by line and process

### Section 5: Report & Action (3:45–5:00)

**Narration Summary**:
> AI generates a quality inspection report. Presents root cause candidates and recommended actions.

**Key Visual**: AI-generated quality report (anomaly summary + recommended actions)

---

## Screen Capture Plan

| # | Screen | Section |
|---|--------|---------|
| 1 | Sensor data file list | Section 1 |
| 2 | Workflow launch screen | Section 2 |
| 3 | Anomaly detection progress | Section 3 |
| 4 | Anomaly distribution query results | Section 4 |
| 5 | AI quality inspection report | Section 5 |

---

## Narration Outline

| Section | Time | Key Message |
|---------|------|-------------|
| Problem | 0:00–0:45 | "Threshold alerts miss true anomalies" |
| Ingestion | 0:45–1:30 | "Analysis starts automatically upon data accumulation" |
| Detection | 1:30–2:30 | "Detect only significant anomalies using statistical methods" |
| Inspection | 2:30–3:45 | "Identify problem locations at line and process level" |
| Report | 3:45–5:00 | "AI presents root cause candidates and countermeasures" |

---

## Sample Data Requirements

| # | Data | Purpose |
|---|------|---------|
| 1 | Normal sensor data (5 lines × 7 days) | Baseline |
| 2 | Temperature anomaly data (2 cases) | Anomaly detection demo |
| 3 | Vibration anomaly data (3 cases) | Correlation analysis demo |
| 4 | Quality degradation pattern (1 case) | Report generation demo |

---

## Timeline

### Achievable Within 1 Week

| Task | Time Required |
|------|--------------|
| Generate sample sensor data | 3 hours |
| Verify pipeline execution | 2 hours |
| Capture screenshots | 2 hours |
| Create narration script | 2 hours |
| Video editing | 4 hours |

### Future Enhancements

- Real-time streaming analysis
- Automatic preventive maintenance schedule generation
- Digital twin integration

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Workflow orchestration |
| Lambda (Data Preprocessor) | Sensor data normalization and preprocessing |
| Lambda (Anomaly Detector) | Statistical anomaly detection |
| Lambda (Report Generator) | Quality report generation via Bedrock |
| Amazon Athena | Anomaly data aggregation and analysis |

### Fallback

| Scenario | Response |
|----------|----------|
| Insufficient data volume | Use pre-generated data |
| Insufficient detection accuracy | Display parameter-tuned results |

---

*This document is a production guide for technical presentation demo videos.*

---

## About Output Destination: FSxN S3 Access Point (Pattern A)

UC3 manufacturing-analytics is classified as **Pattern A: Native S3AP Output**
(refer to `docs/output-destination-patterns.md`).

**Design**: Sensor data analysis results, anomaly detection reports, and image inspection results are all written back via FSxN S3 Access Point to the **same FSx ONTAP volume** as the original sensor CSV and inspection images. No standard S3 bucket is created ("no data movement" pattern).

**CloudFormation Parameters**:
- `S3AccessPointAlias`: S3 AP Alias for reading input data
- `S3AccessPointOutputAlias`: S3 AP Alias for writing output (can be the same as input)

**Deployment Example**:
```bash
aws cloudformation deploy \
  --template-file manufacturing-analytics/template-deploy.yaml \
  --stack-name fsxn-manufacturing-analytics-demo \
  --parameter-overrides \
    S3AccessPointAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    S3AccessPointOutputAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    ... (other required parameters)
```

**View from SMB/NFS Users**:
```
/vol/sensors/
  ├── 2026/05/line_A/sensor_001.csv    # Original sensor data
  └── analysis/2026/05/                 # AI anomaly detection results (same volume)
      └── line_A_report.json
```

For AWS specification constraints, refer to
[the "AWS Specification Constraints and Workarounds" section in the project README](../../README.md#aws-仕様上の制約と回避策)
and [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md).

---

## Verified UI/UX Screenshots

Following the same policy as Phase 7 UC15/16/17 and UC6/11/14 demos, we target **UI/UX screens that end users actually see in their daily work**. Technical views (Step Functions graphs, CloudFormation stack events, etc.) are consolidated in `docs/verification-results-*.md`.

### Verification Status for This Use Case

- ✅ **E2E Execution**: Confirmed in Phase 1-6 (refer to root README)
- 📸 **UI/UX Re-capture**: ✅ Captured in 2026-05-10 redeployment verification (confirmed UC3 Step Functions graph, Lambda execution success)
- 🔄 **Reproduction Method**: Refer to "Capture Guide" at the end of this document

### Captured in 2026-05-10 Redeployment Verification (UI/UX Focus)

#### UC3 Step Functions Graph view (SUCCEEDED)

![UC3 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc3-demo/uc3-stepfunctions-graph.png)

Step Functions Graph view is the most important end-user screen that visualizes the execution status of each Lambda / Parallel / Map state with colors.

### Existing Screenshots (Relevant from Phase 1-6)

![UC3 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc3-demo/step-functions-graph-succeeded.png)

![UC3 Step Functions Graph (Expanded View)](../../docs/screenshots/masked/uc3-demo/step-functions-graph-expanded.png)

![UC3 Step Functions Graph (Zoomed View — Step Details)](../../docs/screenshots/masked/uc3-demo/step-functions-graph-zoomed.png)

### UI/UX Target Screens for Re-verification (Recommended Capture List)

- S3 output bucket (metrics/, anomalies/, reports/)
- Athena query results (IoT sensor anomaly detection)
- Rekognition quality inspection image labels
- Manufacturing quality summary report

### Capture Guide

1. **Preparation**:
   - Verify prerequisites with `bash scripts/verify_phase7_prerequisites.sh` (check for shared VPC/S3 AP)
   - Package Lambda with `UC=manufacturing-analytics bash scripts/package_generic_uc.sh`
   - Deploy with `bash scripts/deploy_generic_ucs.sh UC3`

2. **Place Sample Data**:
   - Upload sample files to `sensors/` prefix via S3 AP Alias
   - Start Step Functions `fsxn-manufacturing-analytics-demo-workflow` (input `{}`)

3. **Capture** (close CloudShell/terminal, mask username in browser top-right):
   - Overview of S3 output bucket `fsxn-manufacturing-analytics-demo-output-<account>`
   - AI/ML output JSON preview (refer to `build/preview_*.html` format)
   - SNS email notification (if applicable)

4. **Masking**:
   - Auto-mask with `python3 scripts/mask_uc_demos.py manufacturing-analytics-demo`
   - Apply additional masking as needed following `docs/screenshots/MASK_GUIDE.md`

5. **Cleanup**:
   - Delete with `bash scripts/cleanup_generic_ucs.sh UC3`
   - VPC Lambda ENI release takes 15-30 minutes (AWS specification)
