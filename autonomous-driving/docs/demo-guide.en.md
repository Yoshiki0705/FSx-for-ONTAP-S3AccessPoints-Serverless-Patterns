# Driving Data Preprocessing & Annotation — Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | English | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

This demo showcases a driving data preprocessing and annotation pipeline for autonomous driving development. It automatically classifies and quality-checks large volumes of sensor data, efficiently building training datasets.

**Core Message**: Automate driving data quality verification and metadata tagging, accelerating AI training dataset construction.

**Target Duration**: 3–5 minutes

---

## Target Audience & Persona

| Item | Details |
|------|---------|
| **Role** | Data Engineer / ML Engineer |
| **Daily Tasks** | Driving data management, annotation, training dataset construction |
| **Challenge** | Cannot efficiently extract useful scenes from massive driving data |
| **Expected Outcome** | Automated data quality verification and efficient scene classification |

### Persona: Data Engineer

- TB-scale driving data accumulates daily
- Camera/LiDAR/radar synchronization verification is manual
- "I want only quality data to automatically flow to the training pipeline"

---

## Demo Scenario: Driving Data Batch Preprocessing

### Workflow Overview

```
Driving Data       Data Validation    Scene Classification   Dataset
(ROS bag etc.) →   Quality Check   →  Metadata           →  Catalog
                   Sync Verification   Tagging (AI)          Generation
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1: Problem Statement (0:00–0:45)

**Narration Summary**:
> TB-scale driving data accumulates daily. Poor quality data (sensor dropouts, sync misalignment) is mixed in, making manual selection impractical.

**Key Visual**: Driving data folder structure, data volume visualization

### Section 2: Pipeline Trigger (0:45–1:30)

**Narration Summary**:
> When new driving data is uploaded, the preprocessing pipeline automatically triggers.

**Key Visual**: Data upload → workflow auto-trigger

### Section 3: Quality Validation (1:30–2:30)

**Narration Summary**:
> Sensor data completeness check: automatically detect frame drops, timestamp sync issues, and data corruption.

**Key Visual**: Quality check results — per-sensor health scores

### Section 4: Scene Classification (2:30–3:45)

**Narration Summary**:
> AI automatically classifies scenes: intersections, highways, adverse weather, nighttime, etc. Tagged as metadata.

**Key Visual**: Scene classification results table, category distribution

### Section 5: Dataset Catalog (3:45–5:00)

**Narration Summary**:
> Automatically generate a catalog of quality-verified data. Available as a searchable dataset by scene conditions.

**Key Visual**: Dataset catalog, search interface

---

## Screen Capture Plan

| # | Screen | Section |
|---|--------|---------|
| 1 | Driving data folder structure | Section 1 |
| 2 | Pipeline trigger screen | Section 2 |
| 3 | Quality check results | Section 3 |
| 4 | Scene classification results | Section 4 |
| 5 | Dataset catalog | Section 5 |

---

## Narration Outline

| Section | Time | Key Message |
|---------|------|-------------|
| Problem | 0:00–0:45 | "Manual selection of useful scenes from TB-scale data is impossible" |
| Trigger | 0:45–1:30 | "Upload automatically starts preprocessing" |
| Validation | 1:30–2:30 | "Auto-detect sensor dropouts and sync misalignment" |
| Classification | 2:30–3:45 | "AI auto-classifies scenes and tags metadata" |
| Catalog | 3:45–5:00 | "Auto-generate searchable dataset catalog" |

---

## Sample Data Requirements

| # | Data | Purpose |
|---|------|---------|
| 1 | Normal driving data (5 sessions) | Baseline |
| 2 | Frame dropout data (2) | Quality check demo |
| 3 | Diverse scene data (intersection, highway, nighttime) | Classification demo |

---

## Timeline

### Achievable Within 1 Week

| Task | Duration |
|------|----------|
| Prepare sample driving data | 3 hours |
| Verify pipeline execution | 2 hours |
| Capture screenshots | 2 hours |
| Create narration script | 2 hours |
| Video editing | 4 hours |

### Future Enhancements

- Automatic 3D annotation generation
- Active learning-based data selection
- Data versioning integration

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Workflow orchestration |
| Lambda (Python 3.13) | Sensor data quality validation, scene classification, catalog generation |
| Lambda SnapStart | Cold start reduction (`EnableSnapStart=true` opt-in) |
| SageMaker (4-way routing) | Inference (Batch / Serverless / Provisioned / Inference Components) |
| SageMaker Inference Components | True scale-to-zero (`EnableInferenceComponents=true`) |
| Amazon Bedrock | Scene classification / annotation suggestions |
| Amazon Athena | Metadata search and aggregation |
| CloudFormation Guard Hooks | Deploy-time security policy enforcement |

### Local Testing (Phase 6A)

```bash
# Local test with SAM CLI
sam local invoke \
  --template autonomous-driving/template-deploy.yaml \
  --event events/uc09-autonomous-driving/discovery-event.json \
  --env-vars events/env.json \
  DiscoveryFunction
```

### Fallback

| Scenario | Response |
|----------|----------|
| Large data processing delay | Execute on subset |
| Classification accuracy issues | Display pre-classified results |

---

*This document serves as a production guide for technical presentation demo videos.*
