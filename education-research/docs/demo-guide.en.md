# Paper Classification & Citation Network Analysis — Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | English | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

This demo showcases an automated paper classification and citation network analysis pipeline. It extracts metadata from large collections of academic paper PDFs and visualizes research trends.

**Core Message**: Automatically classify paper collections and analyze citation relationships to instantly grasp the overall landscape and key papers in a research field.

**Target Duration**: 3–5 minutes

---

## Target Audience & Persona

| Item | Details |
|------|---------|
| **Role** | Researcher / Library Information Specialist / Research Administrator |
| **Daily Tasks** | Literature surveys, research trend analysis, paper management |
| **Challenge** | Cannot efficiently discover related research from large paper volumes |
| **Expected Outcome** | Research field mapping and automatic identification of key papers |

### Persona: Researcher

- Conducting a literature survey for a new research theme
- Collected 500+ paper PDFs but cannot grasp the overall picture
- "I want to auto-classify by field and identify highly-cited key papers"

---

## Demo Scenario: Automated Literature Collection Analysis

### Workflow Overview

```
Paper PDFs        Metadata Extraction   Classification     Visualization
(500+ papers) →   Title/Author       →  Topic            → Network Map
                  Citation Info         Classification      Report
                                        Citation Analysis   Generation
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1: Problem Statement (0:00–0:45)

**Narration Summary**:
> Collected over 500 paper PDFs. Want to understand field distribution, key papers, and research trends, but reading them all is impossible.

**Key Visual**: Paper PDF file list (large volume)

### Section 2: Metadata Extraction (0:45–1:30)

**Narration Summary**:
> Automatically extract title, authors, abstract, and citation list from each paper PDF.

**Key Visual**: Metadata extraction processing, sample extraction results

### Section 3: Classification (1:30–2:30)

**Narration Summary**:
> AI analyzes abstracts and automatically classifies research topics. Clustering forms related paper groups.

**Key Visual**: Topic classification results, paper count by category

### Section 4: Citation Analysis (2:30–3:45)

**Narration Summary**:
> Analyze citation relationships and identify highly-cited key papers. Analyze citation network structure.

**Key Visual**: Citation network statistics, key paper ranking

### Section 5: Research Map (3:45–5:00)

**Narration Summary**:
> AI generates a summary report of the research field landscape. Presents trends, gaps, and future research directions.

**Key Visual**: Research map report (trend analysis + recommended literature)

---

## Screen Capture Plan

| # | Screen | Section |
|---|--------|---------|
| 1 | Paper PDF collection | Section 1 |
| 2 | Metadata extraction results | Section 2 |
| 3 | Topic classification results | Section 3 |
| 4 | Citation network statistics | Section 4 |
| 5 | Research map report | Section 5 |

---

## Narration Outline

| Section | Time | Key Message |
|---------|------|-------------|
| Problem | 0:00–0:45 | "Want to grasp the big picture of 500 papers" |
| Extraction | 0:45–1:30 | "Auto-extract metadata from PDFs" |
| Classification | 1:30–2:30 | "AI auto-classifies by topic" |
| Citation | 2:30–3:45 | "Citation network identifies key papers" |
| Map | 3:45–5:00 | "Visualize field landscape and trends" |

---

## Sample Data Requirements

| # | Data | Purpose |
|---|------|---------|
| 1 | Paper PDFs (30, across 3 fields) | Main processing target |
| 2 | Citation relationship data (with cross-citations) | Network analysis demo |
| 3 | Highly-cited papers (5) | Key paper identification demo |

---

## Timeline

### Achievable Within 1 Week

| Task | Duration |
|------|----------|
| Prepare sample paper data | 3 hours |
| Verify pipeline execution | 2 hours |
| Capture screenshots | 2 hours |
| Create narration script | 2 hours |
| Video editing | 4 hours |

### Future Enhancements

- Interactive citation network visualization
- Paper recommendation system
- Periodic automatic classification of new papers

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Workflow orchestration |
| Lambda (PDF Parser) | Paper PDF metadata extraction |
| Lambda (Classifier) | Topic classification via Bedrock |
| Lambda (Citation Analyzer) | Citation network construction/analysis |
| Amazon Athena | Metadata aggregation/search |

### Fallback

| Scenario | Response |
|----------|----------|
| PDF parse failure | Use pre-extracted data |
| Classification accuracy issues | Display pre-classified results |

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

![UC13 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc13-demo/step-functions-graph-succeeded.png)

![UC13 Step Functions Graph (overview)](../../docs/screenshots/masked/uc13-demo/step-functions-graph-overview.png)

![UC13 Step Functions Graph (zoomed — per-step detail)](../../docs/screenshots/masked/uc13-demo/step-functions-graph-zoomed.png)

### UI/UX Target Screens for Re-verification (Recommended Capture List)

- S3 output bucket (papers-ocr/, citations/, reports/)
- Textract paper OCR results (Cross-Region)
- Comprehend entity detection (authors, citations, keywords)
- Research network analysis report

### Capture Guide

1. **Preparation**: Run `bash scripts/verify_phase7_prerequisites.sh` to check prerequisites
2. **Sample Data**: Upload sample files via S3 AP Alias, then start Step Functions workflow
3. **Capture** (close CloudShell/terminal, mask username in browser top-right)
4. **Mask**: Run `python3 scripts/mask_uc_demos.py <uc-dir>` for automated OCR masking
5. **Cleanup**: Run `bash scripts/cleanup_generic_ucs.sh <UC>` to delete stack
