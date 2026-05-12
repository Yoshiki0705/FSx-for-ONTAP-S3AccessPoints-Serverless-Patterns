# EDA Design File Validation — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | English | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> Note: This translation is produced by Amazon Bedrock Claude. Contributions to improve translation quality are welcome.

## Executive Summary

This guide defines a technical demonstration for semiconductor design engineers. The demo showcases an automated quality validation workflow for design files (GDS/OASIS), demonstrating the value of streamlining pre-tapeout design reviews.

**Core Demo Message**: Automate quality checks across IP blocks that design engineers previously performed manually, completing them within minutes, and enabling immediate action based on AI-generated design review reports.

**Expected Duration**: 3–5 minutes (narrated screen capture video)

---

## Target Audience & Persona

### Primary Audience: EDA End Users (Design Engineers)

| Item | Details |
|------|---------|
| **Role** | Physical Design Engineer / DRC Engineer / Design Lead |
| **Daily Tasks** | Layout design, DRC execution, IP block integration, tapeout preparation |
| **Challenges** | Time-consuming to comprehensively assess quality across multiple IP blocks |
| **Tool Environment** | EDA tools such as Calibre, Virtuoso, IC Compiler, Innovus |
| **Expected Outcomes** | Early detection of design quality issues, meeting tapeout schedules |

### Persona: Tanaka-san (Physical Design Lead)

- Manages 40+ IP blocks in a large-scale SoC project
- Needs to conduct quality review of all blocks 2 weeks before tapeout
- Individually checking GDS/OASIS files for each block is impractical
- "I want to grasp the quality summary of all blocks at a glance"

---

## Demo Scenario: Pre-tapeout Quality Review

### Scenario Overview

In the pre-tapeout quality review phase, the design lead executes automated quality validation on multiple IP blocks (40+ files) and makes action decisions based on AI-generated review reports.

### Overall Workflow

```
Design File Set       Automated          Analysis Results      AI Review
(GDS/OASIS)    →     Validation    →    Statistical      →    Report Generation
                     Workflow           Aggregation           (Natural Language)
                     Trigger            (Athena SQL)
```

### Value Demonstrated in Demo

1. **Time Reduction**: Complete cross-block review in minutes instead of days of manual work
2. **Comprehensiveness**: Validate all IP blocks without omission
3. **Quantitative Judgment**: Objective quality assessment through statistical outlier detection (IQR method)
4. **Actionable**: AI presents specific recommended actions

---

## Storyboard (5 Sections / 3–5 minutes)

### Section 1: Problem Statement (0:00–0:45)

**Screen**: Design project file list (40+ GDS/OASIS files)

**Narration Summary**:
> Two weeks before tapeout. Need to verify design quality of over 40 IP blocks.
> Opening and checking each file individually in EDA tools is not realistic.
> Need a method to detect cell count anomalies, bounding box outliers, and naming convention violations across all blocks.

**Key Visual**:
- Design file directory structure (.gds, .gds2, .oas, .oasis)
- Text overlay: "Manual review: estimated 3–5 days"

---

### Section 2: Workflow Trigger (0:45–1:30)

**Screen**: Design engineer triggering the quality validation workflow

**Narration Summary**:
> After reaching a design milestone, launch the quality validation workflow.
> Simply specify the target directory, and automated validation of all design files begins.

**Key Visual**:
- Workflow execution screen (Step Functions console)
- Input parameters: target volume path, file filter (.gds/.oasis)
- Execution start confirmation

**Engineer's Action**:
```
Target: All design files under /vol/eda_designs/
Filter: .gds, .gds2, .oas, .oasis
Execute: Start quality validation workflow
```

---

### Section 3: Automated Analysis (1:30–2:30)

**Screen**: Progress display during workflow execution

**Narration Summary**:
> The workflow automatically executes the following:
> 1. Design file detection and listing
> 2. Metadata extraction from each file's header (library_name, cell_count, bounding_box, units)
> 3. Statistical analysis on extracted data (SQL queries)
> 4. AI-generated design review report generation
>
> Even for large GDS files (several GB), processing is fast because only the header portion (64KB) is read.

**Key Visual**:
- Each workflow step completing sequentially
- Parallel processing (Map State) showing multiple files being processed simultaneously
- Processing time: approximately 2–3 minutes (for 40 files)

---

### Section 4: Results Review (2:30–3:45)

**Screen**: Athena SQL query results and statistical summary

**Narration Summary**:
> Analysis results can be freely queried with SQL.
> For example, ad-hoc analysis such as "display cells with abnormally large bounding boxes" is possible.

**Key Visual — Athena Query Example**:
```sql
-- Detection of bounding box outliers
SELECT file_key, library_name, 
       bounding_box_width, bounding_box_height
FROM eda_metadata
WHERE bounding_box_width > (SELECT Q3 + 1.5 * IQR FROM stats)
ORDER BY bounding_box_width DESC;
```

**Key Visual — Query Results**:

| file_key | library_name | width | height | Assessment |
|----------|-------------|-------|--------|------|
| analog_frontend.oas | ANALOG_FE | 15200.3 | 12100.8 | Outlier |
| test_block_debug.gds | TEST_DBG | 8900.1 | 14500.2 | Outlier |
| legacy_io_v1.gds2 | LEGACY_IO | 11200.5 | 13800.7 | Outlier |

---

### Section 5: Actionable Insights (3:45–5:00)

**Screen**: AI-generated design review report

**Narration Summary**:
> AI interprets statistical analysis results and automatically generates a review report for design engineers.
> Includes risk assessment, specific recommended actions, and prioritized action items.
> Based on this report, discussions can immediately begin in pre-tapeout review meetings.

**Key Visual — AI Review Report (Excerpt)**:

```markdown
# Design Review Report

## Risk Assessment: Medium

## Findings Summary
- Bounding box outliers: 3 cases
- Naming convention violations: 2 cases
- Invalid files: 2 cases

## Recommended Actions (by priority)
1. [High] Investigate cause of 2 invalid files
2. [Medium] Consider layout optimization for analog_frontend.oas
3. [Low] Unify naming conventions (block-a-io → block_a_io)
```

**Closing**:
> Cross-block review that used to take days manually is now complete in minutes.
> Design engineers can focus on reviewing analysis results and making action decisions.

---

## Screen Capture Plan

### Required Screen Captures List

| # | Screen | Section | Notes |
|---|------|-----------|------|
| 1 | Design file directory list | Section 1 | File structure on FSx ONTAP |
| 2 | Workflow execution start screen | Section 2 | Step Functions console |
| 3 | Workflow in progress (Map State parallel processing) | Section 3 | Progress visible |
| 4 | Workflow completion screen | Section 3 | All steps successful |
| 5 | Athena query editor + results | Section 4 | Outlier detection query |
| 6 | Metadata JSON output example | Section 4 | Extraction result for 1 file |
| 7 | AI design review report full text | Section 5 | Markdown rendered display |
| 8 | SNS notification email | Section 5 | Report completion notification |

### Capture Procedure

1. Place sample data in demo environment
2. Manually execute workflow and capture screens at each step
3. Execute queries in Athena console and capture results
4. Download generated report from S3 and display

---

## Verified UI/UX Screenshots (Re-verified 2026-05-10)

Following the same approach as Phase 7 UC15/16/17, capturing **UI/UX screens that design engineers actually see in daily work**.
Technical views like Step Functions graphs are excluded (details in
[`docs/verification-results-phase7.md`](../../docs/verification-results-phase7.md)).

### 1. FSx for NetApp ONTAP Volumes — Design File Volumes

ONTAP volume list as seen by design engineers. GDS/OASIS files are placed in `eda_demo_vol`
managed with NTFS ACLs.

<!-- SCREENSHOT: uc6-fsx-volumes-list.png
     Content: FSx console showing ONTAP Volumes list (eda_demo_vol etc.), Status=Created, Type=ONTAP
     Masked: Account ID, actual SVM ID values, file system ID -->
![UC6: FSx Volumes List](../../docs/screenshots/masked/uc6-demo/uc6-fsx-volumes-list.png)

### 2. S3 Output Bucket — Design Documents and Analysis Results List

Screen where design review personnel verify results after workflow completion.
Organized into 3 prefixes: `metadata/` / `athena-results/` / `reports/`.

<!-- SCREENSHOT: uc6-s3-output-bucket.png
     Content: S3 console showing bucket top-level prefixes
     Masked: Account ID, bucket name prefix -->
![UC6: S3 Output Bucket](../../docs/screenshots/masked/uc6-demo/uc6-s3-output-bucket.png)

### 2. S3 Output Bucket — Design Documents and Analysis Results List

Screen where design review personnel verify results after workflow completion.
Organized into 3 prefixes: `metadata/` / `athena-results/` / `reports/`.

<!-- SCREENSHOT: uc6-s3-output-bucket.png
     Content: S3 console showing bucket top-level prefixes
     Masked: Account ID, bucket name prefix -->
![UC6: S3 Output Bucket](../../docs/screenshots/masked/uc6-demo/uc6-s3-output-bucket.png)

### 3. Athena Query Results — SQL Analysis of EDA Metadata

Screen where design lead performs ad-hoc exploration of DRC information.
Workgroup is `fsxn-eda-uc6-workgroup`, database is `fsxn-eda-uc6-db`.

<!-- SCREENSHOT: uc6-athena-query-result.png
     Content: SELECT results from EDA metadata table (file_key, library_name, cell_count, bounding_box)
     Masked: Account ID -->
![UC6: Athena Query Results](../../docs/screenshots/masked/uc6-demo/uc6-athena-query-result.png)

### 4. Bedrock-Generated Design Review Report

**UC6's flagship feature**: Based on Athena's DRC aggregation results, Bedrock Nova Lite generates
a Japanese design review report for Physical Design Leads.

<!-- SCREENSHOT: uc6-bedrock-design-review.png
     Content: Executive summary + cell count analysis + naming convention violation list + risk assessment (High/Medium/Low)
     Actual sample content:
       ## Design Review Summary
       ### Executive Summary
       Based on the current DRC aggregation results, the overall design quality assessment is presented below.
       There are a total of 2 design files, cell count distribution is stable, and no bounding box outliers were confirmed.
       However, 6 naming convention violations were found.
       ...
       ### Risk Assessment
       - **High**: None
       - **Medium**: 6 naming convention violations confirmed.
       - **Low**: No issues with cell count distribution or bounding box outliers.
     Masked: Account ID -->
![UC6: Bedrock Design Review Report](../../docs/screenshots/masked/uc6-demo/uc6-bedrock-design-review.png)

### Measured Values (AWS Deployment Verification 2026-05-10)

- **Step Functions execution time**: ~30 seconds (Discovery + Map(2 files) + DRC + Report)
- **Bedrock-generated report**: 2,093 bytes (Japanese in Markdown format)
- **Athena query**: 0.02 KB scanned, runtime 812 ms
- **Actual stack**: `fsxn-eda-uc6` (running in ap-northeast-1 as of 2026-05-10)

---

## Narration Outline

### Tone & Style

- **Perspective**: First-person perspective of design engineer (Tanaka-san)
- **Tone**: Practical, problem-solving oriented
- **Language**: Japanese (English subtitle option)
- **Speed**: Slow and clear (for technical demo)

### Narration Structure

| Section | Time | Key Message |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "Need to verify quality of 40+ blocks before tapeout. Manual process won't make it in time" |
| Trigger | 0:45–1:30 | "Just launch the workflow after design milestone" |
| Analysis | 1:30–2:30 | "Header parsing → metadata extraction → statistical analysis proceeds automatically" |
| Results | 2:30–3:45 | "Query freely with SQL. Identify outliers immediately" |
| Insights | 3:45–5:00 | "AI report presents prioritized actions. Directly feeds into review meetings" |

---

## Sample Data Requirements

### Required Sample Data

| # | File | Format | Purpose |
|---|---------|------------|------|
| 1 | `top_chip_v3.gds` | GDSII | Main chip (large-scale, 1000+ cells) |
| 2 | `block_a_io.gds2` | GDSII | I/O block (normal data) |
| 3 | `memory_ctrl.oasis` | OASIS | Memory controller (normal data) |
| 4 | `analog_frontend.oas` | OASIS | Analog block (outlier: large BB) |
| 5 | `test_block_debug.gds` | GDSII | Debug use (outlier: abnormal height) |
| 6 | `legacy_io_v1.gds2` | GDSII | Legacy block (outlier: width/height) |
| 7 | `block-a-io.gds2` | GDSII | Naming convention violation sample |
| 8 | `TOP CHIP (copy).gds` | GDSII | Naming convention violation sample |

### Sample Data Generation Policy

- **Minimum configuration**: 8 files (above list) covers all demo scenarios
- **Recommended configuration**: 40+ files (improves statistical analysis credibility)
- **Generation method**: Python script generates test files with valid GDSII/OASIS headers
- **Size**: Approximately 100KB per file is sufficient since only header parsing is performed

### Existing Demo Environment Checklist

- [ ] Sample data placed in FSx ONTAP volume
- [ ] S3 Access Point configured
- [ ] Glue Data Catalog table definitions exist
- [ ] Athena workgroup available

---

## Timeline

### Achievable Within 1 Week

| # | Task | Time Required | Prerequisites |
|---|--------|---------|---------|
| 1 | Generate sample data (8 files) | 2 hours | Python environment |
| 2 | Verify workflow execution in demo environment | 2 hours | Deployed environment |
| 3 | Capture screens (8 screens) | 3 hours | After task 2 completion |
| 4 | Finalize narration script | 2 hours | After task 3 completion |
| 5 | Video editing (captures + narration) | 4 hours | After tasks 3, 4 completion |
| 6 | Review & revisions | 2 hours | After task 5 completion |
| **Total** | | **15 hours** | |

### Prerequisites (Required to Achieve 1-Week Timeline)

- Step Functions workflow deployed and functioning normally
- Lambda functions (Discovery, MetadataExtraction, DrcAggregation, ReportGeneration) verified operational
- Athena tables and queries executable
- Bedrock model access enabled

### Future Enhancements

| # | Enhancement | Overview | Priority |
|---|---------|------|--------|
| 1 | DRC tool integration | Direct import of Calibre/Pegasus DRC result files | High |
| 2 | Interactive dashboard | Design quality dashboard using QuickSight | Medium |
| 3 | Slack/Teams notifications | Chat notifications on review report completion | Medium |
| 4 | Differential review | Automatic detection and reporting of differences from previous execution | High |
| 5 | Custom rule definition | Enable configuration of project-specific quality rules | Medium |
| 6 | Multi-language reports | Report generation in English/Japanese/Chinese | Low |
| 7 | CI/CD integration | Incorporate as automated quality gate in design flow | High |
| 8 | Large-scale data support | Optimize parallel processing for 1000+ files | Medium |

---

## Technical Notes (For Demo Creators)

### Components Used (Existing Implementation Only)

| Component | Role |
|--------------|------|
| Step Functions | Orchestration of entire workflow |
| Lambda (Discovery) | Design file detection and listing |
| Lambda (MetadataExtraction) | GDSII/OASIS header parsing and metadata extraction |
| Lambda (DrcAggregation) | Statistical analysis execution via Athena SQL |
| Lambda (ReportGeneration) | AI review report generation via Bedrock |
| Amazon Athena | SQL queries on metadata |
| Amazon Bedrock | Natural language report generation (Nova Lite / Claude) |

### Fallbacks During Demo Execution

| Scenario | Response |
|---------|------|
| Workflow execution failure | Use pre-recorded execution screens |
| Bedrock response delay | Display pre-generated report |
| Athena query timeout | Display pre-fetched result CSV |
| Network failure | All screens pre-captured and converted to video |

---

*This document was created as a production guide for technical presentation demo videos.*
