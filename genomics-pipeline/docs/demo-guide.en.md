# Sequencing QC & Variant Aggregation — Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | English | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

This demo showcases a next-generation sequencing (NGS) data quality control and variant aggregation pipeline. It automatically verifies sequencing quality and aggregates variant calling results into reports.

**Core Message**: Automate sequencing data QC and instantly generate variant aggregation reports, ensuring analysis reliability.

**Target Duration**: 3–5 minutes

---

## Target Audience & Persona

| Item | Details |
|------|---------|
| **Role** | Bioinformatician / Genomics Researcher |
| **Daily Tasks** | Sequencing data QC, variant calling, results interpretation |
| **Challenge** | Manual QC review of large sample volumes is time-consuming |
| **Expected Outcome** | Automated QC and efficient variant aggregation |

### Persona: Bioinformatician

- Processes 100+ sequencing samples per week
- Early detection of samples failing QC criteria is essential
- "I want only QC-passed samples to automatically flow to downstream analysis"

---

## Demo Scenario: Sequencing Batch QC

### Workflow Overview

```
FASTQ/BAM Files     QC Analysis      Quality Filtering    Variant Aggregation
(100+ samples)  →   Metrics       →  Pass/Fail        →  Report Generation
                    Calculation      Filtering
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1: Problem Statement (0:00–0:45)

**Narration Summary**:
> Over 100 sequencing samples per week. If poor-quality samples contaminate downstream analysis, overall result reliability degrades.

**Key Visual**: Sequencing data file list

### Section 2: Pipeline Trigger (0:45–1:30)

**Narration Summary**:
> After sequencing run completion, the QC pipeline auto-triggers. All samples processed in parallel.

**Key Visual**: Workflow trigger, sample list

### Section 3: QC Metrics (1:30–2:30)

**Narration Summary**:
> Calculate QC metrics for each sample: read count, Q30 rate, mapping rate, coverage depth, duplication rate.

**Key Visual**: QC metrics calculation in progress, metrics list

### Section 4: Quality Filtering (2:30–3:45)

**Narration Summary**:
> Determine Pass/Fail based on QC criteria. Classify Fail sample causes (low-quality reads, low coverage, etc.).

**Key Visual**: Pass/Fail determination results, Fail cause classification

### Section 5: Variant Summary (3:45–5:00)

**Narration Summary**:
> Aggregate variant calling results from QC-passed samples. Generate inter-sample comparison, variant distribution, and AI summary report.

**Key Visual**: Variant aggregation report (statistical summary + AI interpretation)

---

## Screen Capture Plan

| # | Screen | Section |
|---|--------|---------|
| 1 | Sequencing data list | Section 1 |
| 2 | Pipeline trigger screen | Section 2 |
| 3 | QC metrics results | Section 3 |
| 4 | Pass/Fail determination results | Section 4 |
| 5 | Variant aggregation report | Section 5 |

---

## Narration Outline

| Section | Time | Key Message |
|---------|------|-------------|
| Problem | 0:00–0:45 | "Low-quality sample contamination undermines overall reliability" |
| Trigger | 0:45–1:30 | "Run completion automatically starts QC" |
| Metrics | 1:30–2:30 | "Calculate key QC metrics across all samples" |
| Filtering | 2:30–3:45 | "Auto-determine Pass/Fail based on criteria" |
| Summary | 3:45–5:00 | "Instantly generate variant aggregation and AI summary" |

---

## Sample Data Requirements

| # | Data | Purpose |
|---|------|---------|
| 1 | High-quality FASTQ metrics (20 samples) | Baseline |
| 2 | Low-quality samples (Q30 < 80%, 3) | Fail detection demo |
| 3 | Low-coverage samples (2) | Classification demo |
| 4 | Variant calling results (VCF summary) | Aggregation demo |

---

## Timeline

### Achievable Within 1 Week

| Task | Duration |
|------|----------|
| Prepare sample QC data | 3 hours |
| Verify pipeline execution | 2 hours |
| Capture screenshots | 2 hours |
| Create narration script | 2 hours |
| Video editing | 4 hours |

### Future Enhancements

- Real-time sequencing monitoring
- Automated clinical report generation
- Multi-omics integrated analysis

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Workflow orchestration |
| Lambda (QC Calculator) | Sequencing QC metrics calculation |
| Lambda (Quality Filter) | Pass/Fail determination/classification |
| Lambda (Variant Aggregator) | Variant aggregation |
| Lambda (Report Generator) | Summary report generation via Bedrock |

### Fallback

| Scenario | Response |
|----------|----------|
| Large data processing delay | Execute on subset |
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

- S3 output bucket (fastq-qc/, variant-summary/, entities/)
- Athena query results (variant frequency aggregation)
- Comprehend Medical entities (Genes, Diseases, Mutations)
- Bedrock-generated research report

### Capture Guide

1. **Preparation**: Run `bash scripts/verify_phase7_prerequisites.sh` to check prerequisites
2. **Sample Data**: Upload sample files via S3 AP Alias, then start Step Functions workflow
3. **Capture** (close CloudShell/terminal, mask username in browser top-right)
4. **Mask**: Run `python3 scripts/mask_uc_demos.py <uc-dir>` for automated OCR masking
5. **Cleanup**: Run `bash scripts/cleanup_generic_ucs.sh <UC>` to delete stack
