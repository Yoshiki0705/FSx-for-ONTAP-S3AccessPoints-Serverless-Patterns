# Sequencing QC・Variant Aggregation — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | English | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> Note: This translation is produced by Amazon Bedrock Claude. Contributions to improve translation quality are welcome.

## Executive Summary

This demo demonstrates a quality control and variant aggregation pipeline for next-generation sequencing (NGS) data. It automatically validates sequencing quality and aggregates and reports variant calling results.

**Core Demo Message**: Automate sequencing data QC and instantly generate variant aggregation reports. Ensure analysis reliability.

**Estimated Time**: 3–5 minutes

---

## Target Audience & Persona

| Item | Details |
|------|------|
| **Role** | Bioinformatician / Genomic Analysis Researcher |
| **Daily Work** | Sequencing data QC, variant calling, result interpretation |
| **Challenge** | Manually checking QC for large numbers of samples is time-consuming |
| **Expected Outcome** | QC automation and variant aggregation efficiency |

### Persona: Kato-san (Bioinformatician)

- Processes 100+ sequencing data samples per week
- Needs early detection of samples that don't meet QC criteria
- "I want to automatically send only QC-passed samples to downstream analysis"

---

## Demo Scenario: Sequencing Batch QC

### Overall Workflow

```
FASTQ/BAM files    QC Analysis      Quality          Variant
(100+ samples)  →  Metrics     →    Pass/Fail   →    Aggregation
                   Calculation      Filter           Report Generation
```

---

## Storyboard (5 Sections / 3–5 minutes)

### Section 1: Problem Statement (0:00–0:45)

**Narration Summary**:
> Over 100 sequencing data samples per week. When poor-quality samples are mixed into downstream analysis, the reliability of the entire result decreases.

**Key Visual**: List of sequencing data files

### Section 2: Pipeline Trigger (0:45–1:30)

**Narration Summary**:
> After sequencing run completion, the QC pipeline automatically starts. All samples are processed in parallel.

**Key Visual**: Workflow launch, sample list

### Section 3: QC Metrics (1:30–2:30)

**Narration Summary**:
> Calculate QC metrics for each sample: read count, Q30 rate, mapping rate, coverage depth, duplication rate.

**Key Visual**: QC metrics calculation in progress, metrics list

### Section 4: Quality Filtering (2:30–3:45)

**Narration Summary**:
> Determine Pass/Fail based on QC criteria. Classify causes of failed samples (low-quality reads, low coverage, etc.).

**Key Visual**: Pass/Fail determination results, failure cause classification

### Section 5: Variant Summary (3:45–5:00)

**Narration Summary**:
> Aggregate variant calling results for QC-passed samples. Generate cross-sample comparison, variant distribution, and AI summary report.

**Key Visual**: Variant aggregation report (statistical summary + AI interpretation)

---

## Screen Capture Plan

| # | Screen | Section |
|---|------|-----------|
| 1 | Sequencing data list | Section 1 |
| 2 | Pipeline launch screen | Section 2 |
| 3 | QC metrics results | Section 3 |
| 4 | Pass/Fail determination results | Section 4 |
| 5 | Variant aggregation report | Section 5 |

---

## Narration Outline

| Section | Time | Key Message |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "Contamination with low-quality samples compromises the reliability of the entire analysis" |
| Trigger | 0:45–1:30 | "QC automatically starts upon run completion" |
| Metrics | 1:30–2:30 | "Calculate key QC metrics for all samples" |
| Filtering | 2:30–3:45 | "Automatically determine Pass/Fail based on criteria" |
| Summary | 3:45–5:00 | "Instantly generate variant aggregation and AI summary" |

---

## Sample Data Requirements

| # | Data | Purpose |
|---|--------|------|
| 1 | High-quality FASTQ metrics (20 samples) | Baseline |
| 2 | Low-quality samples (Q30 < 80%, 3 cases) | Fail detection demo |
| 3 | Low-coverage samples (2 cases) | Classification demo |
| 4 | Variant calling results (VCF summary) | Aggregation demo |

---

## Timeline

### Achievable within 1 week

| Task | Time Required |
|--------|---------|
| Sample QC data preparation | 3 hours |
| Pipeline execution verification | 2 hours |
| Screen capture acquisition | 2 hours |
| Narration script creation | 2 hours |
| Video editing | 4 hours |

### Future Enhancements

- Real-time sequencing monitoring
- Automated clinical report generation
- Multi-omics integrated analysis

---

## Technical Notes

| Component | Role |
|--------------|------|
| Step Functions | Workflow orchestration |
| Lambda (QC Calculator) | Sequencing QC metrics calculation |
| Lambda (Quality Filter) | Pass/Fail determination and classification |
| Lambda (Variant Aggregator) | Variant aggregation |
| Lambda (Report Generator) | Summary report generation via Bedrock |

### Fallback

| Scenario | Response |
|---------|------|
| Large data processing delay | Execute with subset |
| Bedrock delay | Display pre-generated report |

---

*This document is a production guide for demo videos for technical presentations.*

---

## Verified UI/UX Screenshots

Following the same policy as Phase 7 UC15/16/17 and UC6/11/14 demos, targeting **UI/UX screens that end users actually see in their daily work**. Technical views (Step Functions graphs, CloudFormation stack events, etc.) are consolidated in `docs/verification-results-*.md`.

### Verification Status for This Use Case

- ✅ **E2E Execution**: Confirmed in Phase 1-6 (see root README)
- 📸 **UI/UX Re-capture**: ✅ Captured in 2026-05-10 redeployment verification (UC7 Step Functions graph, Lambda execution success confirmed)
- 📸 **UI/UX Capture (Phase 8 Theme D)**: ✅ SUCCEEDED capture completed (commit 2b958db — redeployed after IAM S3AP fix, all steps succeeded in 3:03)
- 🔄 **Reproduction Method**: Refer to "Capture Guide" at the end of this document

### Captured in 2026-05-10 Redeployment Verification (UI/UX Focus)

#### UC7 Step Functions Graph view (SUCCEEDED)

![UC7 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc7-demo/uc7-stepfunctions-graph.png)

Step Functions Graph view is the most important end-user screen that visualizes the execution status of each Lambda / Parallel / Map state with colors.

#### UC7 Step Functions Graph (SUCCEEDED — Phase 8 Theme D Re-capture)

![UC7 Step Functions Graph (SUCCEEDED)](../../docs/screenshots/masked/uc7-demo/step-functions-graph-succeeded.png)

Redeployed after IAM S3AP fix. All steps SUCCEEDED (3:03).

#### UC7 Step Functions Graph (Zoomed View — Each Step Detail)

![UC7 Step Functions Graph (Zoomed View)](../../docs/screenshots/masked/uc7-demo/step-functions-graph-zoomed.png)

### Existing Screenshots (Relevant from Phase 1-6)

#### UC7 Comprehend Medical Genomics Analysis Results (Cross-Region us-east-1)

![UC7 Comprehend Medical Genomics Analysis Results (Cross-Region us-east-1)](../../docs/screenshots/masked/phase2/phase2-comprehend-medical-genomics-analysis-fullpage.png)


### UI/UX Target Screens for Re-verification (Recommended Capture List)

- S3 output bucket (fastq-qc/, variant-summary/, entities/)
- Athena query results (variant frequency aggregation)
- Comprehend Medical medical entities (Genes, Diseases, Mutations)
- Bedrock-generated research report

### Capture Guide

1. **Preparation**:
   - Verify prerequisites with `bash scripts/verify_phase7_prerequisites.sh` (check for shared VPC/S3 AP)
   - Package Lambda with `UC=genomics-pipeline bash scripts/package_generic_uc.sh`
   - Deploy with `bash scripts/deploy_generic_ucs.sh UC7`

2. **Sample Data Placement**:
   - Upload sample files to `fastq/` prefix via S3 AP Alias
   - Start Step Functions `fsxn-genomics-pipeline-demo-workflow` (input `{}`)

3. **Capture** (close CloudShell/terminal, mask username in browser top-right):
   - Overview of S3 output bucket `fsxn-genomics-pipeline-demo-output-<account>`
   - AI/ML output JSON preview (refer to `build/preview_*.html` format)
   - SNS email notification (if applicable)

4. **Masking**:
   - Auto-mask with `python3 scripts/mask_uc_demos.py genomics-pipeline-demo`
   - Apply additional masking as needed following `docs/screenshots/MASK_GUIDE.md`

5. **Cleanup**:
   - Delete with `bash scripts/cleanup_generic_ucs.sh UC7`
   - VPC Lambda ENI release takes 15-30 minutes (AWS specification)
