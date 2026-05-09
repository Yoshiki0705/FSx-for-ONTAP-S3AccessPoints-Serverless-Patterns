# EDA Design File Validation — Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | English | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

This guide defines a technical demonstration for semiconductor design engineers. The demo showcases an automated quality validation workflow for design files (GDS/OASIS), demonstrating the value of streamlining pre-tapeout design reviews.

**Core Demo Message**: Automate cross-IP-block quality checks that engineers previously performed manually, completing them within minutes and enabling immediate action through AI-generated design review reports.

**Estimated Duration**: 3–5 minutes (narrated screen capture video)

---

## Target Audience & Persona

### Primary Audience: EDA End Users (Design Engineers)

| Item | Details |
|------|---------|
| **Role** | Physical Design Engineer / DRC Engineer / Design Lead |
| **Daily Tasks** | Layout design, DRC execution, IP block integration, tapeout preparation |
| **Challenges** | Time-consuming to get a cross-cutting view of quality across multiple IP blocks |
| **Tool Environment** | EDA tools such as Calibre, Virtuoso, IC Compiler, Innovus |
| **Expected Outcome** | Early detection of design quality issues to meet tapeout schedules |

### Persona: Tanaka-san (Physical Design Lead)

- Manages 40+ IP blocks in a large-scale SoC project
- Needs to conduct quality reviews of all blocks 2 weeks before tapeout
- Individually checking GDS/OASIS files for each block is impractical
- "I want to see a quality summary of all blocks at a glance"

---

## Demo Scenario: Pre-tapeout Quality Review

### Scenario Overview

During the pre-tapeout quality review phase, the design lead runs automated quality validation on multiple IP blocks (40+ files) and decides on actions based on AI-generated review reports.

### Overall Workflow

```
Design Files        Automated          Analysis         AI Review
(GDS/OASIS)   →   Validation    →    Statistical   →  Report
                   Workflow            Aggregation      Generation
                   Trigger             (Athena SQL)     (Natural Language)
```

### Value Demonstrated

1. **Time Reduction**: Complete cross-cutting reviews in minutes instead of days
2. **Completeness**: Validate all IP blocks without omissions
3. **Quantitative Judgment**: Objective quality assessment via statistical outlier detection (IQR method)
4. **Actionable**: AI presents specific recommended actions

---

## Storyboard (5 Sections / 3–5 minutes)

### Section 1: Problem Statement (0:00–0:45)

**Screen**: File listing of the design project (40+ GDS/OASIS files)

**Narration Summary**:
> Two weeks before tapeout. We need to verify design quality across 40+ IP blocks.
> Opening each file individually in an EDA tool is not realistic.
> Abnormal cell counts, bounding box outliers, naming convention violations — we need a way to detect these across all blocks.

**Key Visual**:
- Design file directory structure (.gds, .gds2, .oas, .oasis)
- Text overlay: "Manual review: estimated 3–5 days"

---

### Section 2: Workflow Trigger (0:45–1:30)

**Screen**: Design engineer triggering the quality validation workflow

**Narration Summary**:
> After reaching the design milestone, we launch the quality validation workflow.
> Simply specify the target directory, and automated validation of all design files begins.

**Key Visual**:
- Workflow execution screen (Step Functions console)
- Input parameters: target volume path, file filter (.gds/.oasis)
- Execution start confirmation

**Engineer's Action**:
```
Target: All design files under /vol/eda_designs/
Filter: .gds, .gds2, .oas, .oasis
Action: Start quality validation workflow
```

---

### Section 3: Automated Analysis (1:30–2:30)

**Screen**: Workflow execution progress display

**Narration Summary**:
> The workflow automatically performs the following:
> 1. Detection and listing of design files
> 2. Metadata extraction from each file's header (library_name, cell_count, bounding_box, units)
> 3. Statistical analysis on extracted data (SQL queries)
> 4. AI-generated design review report
>
> Even for large GDS files (several GB), processing is fast because only the header portion (64KB) is read.

**Key Visual**:
- Workflow steps completing sequentially
- Parallel processing (Map State) showing multiple files processed simultaneously
- Processing time: approximately 2–3 minutes (for 40 files)

---

### Section 4: Results Review (2:30–3:45)

**Screen**: Athena SQL query results and statistical summary

**Narration Summary**:
> Analysis results can be freely queried with SQL.
> For example, ad-hoc analysis like "show cells with abnormally large bounding boxes" is possible.

**Key Visual — Athena Query Example**:
```sql
-- Bounding box outlier detection
SELECT file_key, library_name, 
       bounding_box_width, bounding_box_height
FROM eda_metadata
WHERE bounding_box_width > (SELECT Q3 + 1.5 * IQR FROM stats)
ORDER BY bounding_box_width DESC;
```

**Key Visual — Query Results**:

| file_key | library_name | width | height | Verdict |
|----------|-------------|-------|--------|---------|
| analog_frontend.oas | ANALOG_FE | 15200.3 | 12100.8 | Outlier |
| test_block_debug.gds | TEST_DBG | 8900.1 | 14500.2 | Outlier |
| legacy_io_v1.gds2 | LEGACY_IO | 11200.5 | 13800.7 | Outlier |

---

### Section 5: Actionable Insights (3:45–5:00)

**Screen**: AI-generated design review report

**Narration Summary**:
> AI interprets the statistical analysis results and automatically generates a review report for design engineers.
> It includes risk assessment, specific recommended actions, and prioritized action items.
> Based on this report, discussions can begin immediately at the pre-tapeout review meeting.

**Key Visual — AI Review Report (Excerpt)**:

```markdown
# Design Review Report

## Risk Assessment: Medium

## Findings Summary
- Bounding box outliers: 3 items
- Naming convention violations: 2 items
- Invalid files: 2 items

## Recommended Actions (by priority)
1. [High] Investigate cause of 2 invalid files
2. [Medium] Consider layout optimization for analog_frontend.oas
3. [Low] Unify naming conventions (block-a-io → block_a_io)
```

**Closing**:
> Cross-cutting reviews that used to take days manually are now completed in minutes.
> Design engineers can focus on reviewing results and deciding on actions.

---

## Screen Capture Plan

### Required Screen Captures

| # | Screen | Section | Notes |
|---|--------|---------|-------|
| 1 | Design file directory listing | Section 1 | File structure on FSx ONTAP |
| 2 | Workflow execution start screen | Section 2 | Step Functions console |
| 3 | Workflow in progress (Map State parallel processing) | Section 3 | Progress visible |
| 4 | Workflow completion screen | Section 3 | All steps successful |
| 5 | Athena query editor + results | Section 4 | Outlier detection query |
| 6 | Metadata JSON output example | Section 4 | Extraction result for 1 file |
| 7 | AI design review report (full text) | Section 5 | Markdown rendered display |
| 8 | SNS notification email | Section 5 | Report completion notification |

### Capture Procedure

1. Place sample data in the demo environment
2. Manually execute the workflow and capture screens at each step
3. Execute queries in the Athena console and capture results
4. Download the generated report from S3 and display it

---

## Narration Outline

### Tone & Style

- **Perspective**: First-person from the design engineer (Tanaka-san)
- **Tone**: Practical, problem-solving oriented
- **Language**: Japanese (English subtitles optional)
- **Speed**: Slow and clear (for a technical demo)

### Narration Structure

| Section | Time | Key Message |
|---------|------|-------------|
| Problem | 0:00–0:45 | "Need to verify quality of 40+ blocks before tapeout. Manual review won't make it in time" |
| Trigger | 0:45–1:30 | "Just launch the workflow after the design milestone" |
| Analysis | 1:30–2:30 | "Header parsing → metadata extraction → statistical analysis proceeds automatically" |
| Results | 2:30–3:45 | "Query freely with SQL. Identify outliers immediately" |
| Insights | 3:45–5:00 | "AI report presents prioritized actions. Directly feeds into review meetings" |

---

## Sample Data Requirements

### Required Sample Data

| # | File | Format | Purpose |
|---|------|--------|---------|
| 1 | `top_chip_v3.gds` | GDSII | Main chip (large-scale, 1000+ cells) |
| 2 | `block_a_io.gds2` | GDSII | I/O block (normal data) |
| 3 | `memory_ctrl.oasis` | OASIS | Memory controller (normal data) |
| 4 | `analog_frontend.oas` | OASIS | Analog block (outlier: large BB) |
| 5 | `test_block_debug.gds` | GDSII | Debug block (outlier: abnormal height) |
| 6 | `legacy_io_v1.gds2` | GDSII | Legacy block (outlier: width & height) |
| 7 | `block-a-io.gds2` | GDSII | Naming convention violation sample |
| 8 | `TOP CHIP (copy).gds` | GDSII | Naming convention violation sample |

### Sample Data Generation Policy

- **Minimum configuration**: 8 files (above list) covering all demo scenarios
- **Recommended configuration**: 40+ files (for more convincing statistical analysis)
- **Generation method**: Python script to generate test files with valid GDSII/OASIS headers
- **Size**: ~100KB per file is sufficient since only header parsing is performed

### Existing Demo Environment Checklist

- [ ] Sample data placed on FSx ONTAP volume
- [ ] S3 Access Point configured
- [ ] Glue Data Catalog table definition exists
- [ ] Athena workgroup available

---

## Timeline

### Achievable Within 1 Week

| # | Task | Time Required | Prerequisites |
|---|------|---------------|---------------|
| 1 | Sample data generation (8 files) | 2 hours | Python environment |
| 2 | Workflow execution verification in demo environment | 2 hours | Deployed environment |
| 3 | Screen capture acquisition (8 screens) | 3 hours | After task 2 |
| 4 | Narration script finalization | 2 hours | After task 3 |
| 5 | Video editing (captures + narration) | 4 hours | After tasks 3, 4 |
| 6 | Review & revisions | 2 hours | After task 5 |
| **Total** | | **15 hours** | |

### Prerequisites (Required for 1-week completion)

- Step Functions workflow deployed and functioning normally
- Lambda functions (Discovery, MetadataExtraction, DrcAggregation, ReportGeneration) verified
- Athena tables and queries executable
- Bedrock model access enabled

### Future Enhancements

| # | Enhancement | Overview | Priority |
|---|-------------|----------|----------|
| 1 | DRC tool integration | Directly ingest DRC result files from Calibre/Pegasus | High |
| 2 | Interactive dashboard | Design quality dashboard via QuickSight | Medium |
| 3 | Slack/Teams notifications | Chat notification on report completion | Medium |
| 4 | Differential review | Automatically detect and report differences from previous run | High |
| 5 | Custom rule definitions | Enable project-specific quality rules | Medium |
| 6 | Multilingual reports | Report generation in English/Japanese/Chinese | Low |
| 7 | CI/CD integration | Embed as an automated quality gate in the design flow | High |
| 8 | Large-scale data support | Parallel processing optimization for 1000+ files | Medium |

---

## Technical Notes (For Demo Creators)

### Components Used (Existing Implementation Only)

| Component | Role |
|-----------|------|
| Step Functions | Overall workflow orchestration |
| Lambda (Discovery) | Design file detection and listing |
| Lambda (MetadataExtraction) | GDSII/OASIS header parsing and metadata extraction |
| Lambda (DrcAggregation) | Statistical analysis execution via Athena SQL |
| Lambda (ReportGeneration) | AI review report generation via Bedrock |
| Amazon Athena | SQL queries on metadata |
| Amazon Bedrock | Natural language report generation (Nova Lite / Claude) |

### Demo Execution Fallbacks

| Scenario | Response |
|----------|----------|
| Workflow execution failure | Use pre-recorded execution screens |
| Bedrock response delay | Display pre-generated report |
| Athena query timeout | Display pre-fetched result CSV |
| Network failure | All screens pre-captured and compiled into video |

---

*This document was created as a production guide for a technical presentation demo video.*
