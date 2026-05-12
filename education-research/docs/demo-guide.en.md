# Paper Classification and Citation Network Analysis — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | English | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> Note: This translation is produced by Amazon Bedrock Claude. Contributions to improve translation quality are welcome.

## Executive Summary

This demo demonstrates an automated classification and citation network analysis pipeline for academic papers. It extracts metadata from a large volume of paper PDFs and visualizes research trends.

**Core Message of the Demo**: By automatically classifying paper collections and analyzing citation relationships, instantly grasp the overall picture of research fields and identify important papers.

**Estimated Time**: 3–5 minutes

---

## Target Audience & Persona

| Item | Details |
|------|------|
| **Role** | Researcher / Library and Information Science Specialist / Research Administrator |
| **Daily Work** | Literature survey, research trend analysis, paper management |
| **Challenge** | Cannot efficiently discover related research from a large volume of papers |
| **Expected Outcome** | Mapping of research fields and automatic identification of important papers |

### Persona: Watanabe-san (Researcher)

- Currently conducting a literature survey for a new research theme
- Collected 500+ paper PDFs but cannot grasp the overall picture
- "Want to automatically classify by field and identify important papers with many citations"

---

## Demo Scenario: Automated Analysis of Literature Collection

### Overall Workflow

```
Paper PDF Collection    Metadata Extraction    Classification/Analysis    Visualization Report
(500+ items)        →   Title/Author       →   Topic Classification   →   Network
                        Citation Info          Citation Analysis          Map Generation
```

---

## Storyboard (5 Sections / 3–5 minutes)

### Section 1: Problem Statement (0:00–0:45)

**Narration Summary**:
> Collected 500+ paper PDFs. Want to understand distribution by field, important papers, and research trends, but reading all is impossible.

**Key Visual**: List of paper PDF files (large volume)

### Section 2: Metadata Extraction (0:45–1:30)

**Narration Summary**:
> Automatically extract title, author, abstract, and citation list from each paper PDF.

**Key Visual**: Metadata extraction process, sample extraction results

### Section 3: Classification (1:30–2:30)

**Narration Summary**:
> AI analyzes abstracts and automatically classifies research topics. Clustering forms related paper groups.

**Key Visual**: Topic classification results, number of papers by category

### Section 4: Citation Analysis (2:30–3:45)

**Narration Summary**:
> Analyze citation relationships and identify important papers with high citation counts. Analyze citation network structure.

**Key Visual**: Citation network statistics, important paper rankings

### Section 5: Research Map (3:45–5:00)

**Narration Summary**:
> AI generates an overall picture of the research field as a summary report. Presents trends, gaps, and future research directions.

**Key Visual**: Research map report (trend analysis + recommended literature)

---

## Screen Capture Plan

| # | Screen | Section |
|---|------|-----------|
| 1 | Paper PDF Collection | Section 1 |
| 2 | Metadata Extraction Results | Section 2 |
| 3 | Topic Classification Results | Section 3 |
| 4 | Citation Network Statistics | Section 4 |
| 5 | Research Map Report | Section 5 |

---

## Narration Outline

| Section | Time | Key Message |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "Want to grasp the overall picture of 500 papers" |
| Extraction | 0:45–1:30 | "Automatically extract metadata from PDFs" |
| Classification | 1:30–2:30 | "AI automatically classifies by topic" |
| Citation | 2:30–3:45 | "Identify important papers through citation network" |
| Map | 3:45–5:00 | "Visualize overall picture and trends of research field" |

---

## Sample Data Requirements

| # | Data | Purpose |
|---|--------|------|
| 1 | Paper PDFs (30 items, 3 fields) | Main processing target |
| 2 | Citation relationship data (with cross-citations) | Network analysis demo |
| 3 | Highly cited papers (5 items) | Important paper identification demo |

---

## Timeline

### Achievable Within 1 Week

| Task | Time Required |
|--------|---------|
| Prepare sample paper data | 3 hours |
| Verify pipeline execution | 2 hours |
| Capture screenshots | 2 hours |
| Create narration script | 2 hours |
| Video editing | 4 hours |

### Future Enhancements

- Interactive citation network visualization
- Paper recommendation system
- Automatic classification of new papers on a regular basis

---

## Technical Notes

| Component | Role |
|--------------|------|
| Step Functions | Workflow orchestration |
| Lambda (PDF Parser) | Paper PDF metadata extraction |
| Lambda (Classifier) | Topic classification by Bedrock |
| Lambda (Citation Analyzer) | Citation network construction and analysis |
| Amazon Athena | Metadata aggregation and search |

### Fallback

| Scenario | Response |
|---------|------|
| PDF parsing failure | Use pre-extracted data |
| Insufficient classification accuracy | Display pre-classified results |

---

*This document is a production guide for demo videos for technical presentations.*

---

## Verified UI/UX Screenshots

Following the same policy as Phase 7 UC15/16/17 and UC6/11/14 demos, targeting **UI/UX screens that end users actually see in their daily work**. Technical views (Step Functions graph, CloudFormation stack events, etc.) are consolidated in `docs/verification-results-*.md`.

### Verification Status for This Use Case

- ✅ **E2E Execution**: Confirmed in Phase 1-6 (see root README)
- 📸 **UI/UX Re-capture**: ✅ Captured in 2026-05-10 redeployment verification (UC13 Step Functions graph, Lambda execution success confirmed)
- 🔄 **Reproduction Method**: Refer to "Capture Guide" at the end of this document

### Captured in 2026-05-10 Redeployment Verification (UI/UX Focus)

#### UC13 Step Functions Graph view (SUCCEEDED)

![UC13 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc13-demo/uc13-stepfunctions-graph.png)

Step Functions Graph view is the most important end-user screen that visualizes the execution status of each Lambda / Parallel / Map state with colors.

### Existing Screenshots (Relevant from Phase 1-6)

![UC13 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc13-demo/step-functions-graph-succeeded.png)

![UC13 Step Functions Graph (Overall Overview)](../../docs/screenshots/masked/uc13-demo/step-functions-graph-overview.png)

![UC13 Step Functions Graph (Zoomed Display — Each Step Details)](../../docs/screenshots/masked/uc13-demo/step-functions-graph-zoomed.png)

### UI/UX Target Screens for Re-verification (Recommended Capture List)

- S3 output bucket (papers-ocr/, citations/, reports/)
- Textract paper OCR results (Cross-Region)
- Comprehend entity detection (author, citation, keywords)
- Research network analysis report

### Capture Guide

1. **Preparation**:
   - Verify prerequisites with `bash scripts/verify_phase7_prerequisites.sh` (check for common VPC/S3 AP)
   - Package Lambda with `UC=education-research bash scripts/package_generic_uc.sh`
   - Deploy with `bash scripts/deploy_generic_ucs.sh UC13`

2. **Place Sample Data**:
   - Upload sample files to `papers/` prefix via S3 AP Alias
   - Start Step Functions `fsxn-education-research-demo-workflow` (input `{}`)

3. **Capture** (close CloudShell/terminal, mask username in browser top right):
   - Overview of S3 output bucket `fsxn-education-research-demo-output-<account>`
   - Preview of AI/ML output JSON (refer to `build/preview_*.html` format)
   - SNS email notification (if applicable)

4. **Masking**:
   - Auto-mask with `python3 scripts/mask_uc_demos.py education-research-demo`
   - Apply additional masking as needed following `docs/screenshots/MASK_GUIDE.md`

5. **Cleanup**:
   - Delete with `bash scripts/cleanup_generic_ucs.sh UC13`
   - VPC Lambda ENI release takes 15-30 minutes (AWS specification)
