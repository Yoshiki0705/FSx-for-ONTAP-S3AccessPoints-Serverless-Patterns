# IoT Sensor Anomaly Detection & Quality Inspection — Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | English | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

This demo showcases a workflow that automatically detects anomalies from manufacturing line IoT sensor data and generates quality inspection reports.

**Core Message**: Automatically detect anomaly patterns in sensor data, enabling early quality issue detection and predictive maintenance.

**Target Duration**: 3–5 minutes

---

## Target Audience & Persona

| Item | Details |
|------|---------|
| **Role** | Manufacturing Manager / Quality Control Engineer |
| **Daily Tasks** | Production line monitoring, quality inspection, maintenance planning |
| **Challenge** | Missing sensor anomalies leads to defective products reaching downstream |
| **Expected Outcome** | Early anomaly detection and quality trend visualization |

### Persona: Quality Control Engineer

- Monitors 100+ sensors across 5 manufacturing lines
- Threshold-based alerts produce too many false positives, missing real anomalies
- "I want to detect only statistically significant anomalies"

---

## Demo Scenario: Sensor Anomaly Detection Batch Analysis

### Workflow Overview

```
Sensor Data       Data Collection    Anomaly Detection    Quality Report
(CSV/Parquet) →   Preprocessing  →   Statistical      →   AI Generated
                  Normalization      Analysis
                                     (Outlier Detection)
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1: Problem Statement (0:00–0:45)

**Narration Summary**:
> Massive data generated daily from 100+ sensors across manufacturing lines. Simple threshold alerts produce too many false positives, risking missed real anomalies.

**Key Visual**: Sensor data time-series graphs, alert overload situation

### Section 2: Data Ingestion (0:45–1:30)

**Narration Summary**:
> When sensor data accumulates on the file server, the analysis pipeline automatically triggers.

**Key Visual**: Data file placement → workflow trigger

### Section 3: Anomaly Detection (1:30–2:30)

**Narration Summary**:
> Statistical methods (moving average, standard deviation, IQR) calculate anomaly scores per sensor. Cross-sensor correlation analysis also executed.

**Key Visual**: Anomaly detection algorithm running, anomaly score heatmap

### Section 4: Quality Inspection (2:30–3:45)

**Narration Summary**:
> Analyze detected anomalies from a quality inspection perspective. Identify which line and which process has issues.

**Key Visual**: Athena query results — anomaly distribution by line and process

### Section 5: Report & Action (3:45–5:00)

**Narration Summary**:
> AI generates a quality inspection report presenting root cause candidates and recommended actions.

**Key Visual**: AI-generated quality report (anomaly summary + recommended actions)

---

## Screen Capture Plan

| # | Screen | Section |
|---|--------|---------|
| 1 | Sensor data file list | Section 1 |
| 2 | Workflow trigger screen | Section 2 |
| 3 | Anomaly detection progress | Section 3 |
| 4 | Anomaly distribution query results | Section 4 |
| 5 | AI quality inspection report | Section 5 |

---

## Narration Outline

| Section | Time | Key Message |
|---------|------|-------------|
| Problem | 0:00–0:45 | "Threshold alerts miss real anomalies" |
| Ingestion | 0:45–1:30 | "Data accumulation automatically starts analysis" |
| Detection | 1:30–2:30 | "Statistical methods detect only significant anomalies" |
| Inspection | 2:30–3:45 | "Identify problem areas at line and process level" |
| Report | 3:45–5:00 | "AI presents root cause candidates and countermeasures" |

---

## Sample Data Requirements

| # | Data | Purpose |
|---|------|---------|
| 1 | Normal sensor data (5 lines × 7 days) | Baseline |
| 2 | Temperature anomaly data (2) | Anomaly detection demo |
| 3 | Vibration anomaly data (3) | Correlation analysis demo |
| 4 | Quality degradation pattern (1) | Report generation demo |

---

## Timeline

### Achievable Within 1 Week

| Task | Duration |
|------|----------|
| Generate sample sensor data | 3 hours |
| Verify pipeline execution | 2 hours |
| Capture screenshots | 2 hours |
| Create narration script | 2 hours |
| Video editing | 4 hours |

### Future Enhancements

- Real-time streaming analysis
- Automated preventive maintenance scheduling
- Digital twin integration

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Workflow orchestration |
| Lambda (Data Preprocessor) | Sensor data normalization/preprocessing |
| Lambda (Anomaly Detector) | Statistical anomaly detection |
| Lambda (Report Generator) | Quality report generation via Bedrock |
| Amazon Athena | Anomaly data aggregation/analysis |

### Fallback

| Scenario | Response |
|----------|----------|
| Insufficient data volume | Use pre-generated data |
| Detection accuracy issues | Display parameter-tuned results |

---

*This document serves as a production guide for technical presentation demo videos.*
