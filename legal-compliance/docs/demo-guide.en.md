# File Server Permission Audit — Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | English | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

This demo showcases an automated audit workflow that detects excessive access permissions on file servers. It analyzes NTFS ACLs, identifies entries violating the principle of least privilege, and automatically generates compliance reports.

**Core Message**: Automate file server permission audits that would take weeks manually, instantly visualizing excessive permission risks.

**Target Duration**: 3–5 minutes

---

## Target Audience & Persona

| Item | Details |
|------|---------|
| **Role** | Information Security Officer / IT Compliance Manager |
| **Daily Tasks** | Access permission reviews, audit responses, security policy management |
| **Challenge** | Manually reviewing permissions across thousands of folders is impractical |
| **Expected Outcome** | Early detection of excessive permissions and automated compliance evidence |

### Persona: Security Administrator

- Annual audit requires permission review of all shared folders
- Needs to instantly detect dangerous settings like "Everyone Full Control"
- Wants to efficiently create reports for submission to auditors

---

## Demo Scenario: Automated Annual Permission Audit

### Workflow Overview

```
File Server      ACL Collection    Permission Analysis    Report Generation
(NTFS Shares) →  Metadata       →  Violation Detection → Audit Report
                  Extraction        (Rule Matching)       (AI Summary)
```

---

## Output Destination: FSxN S3 Access Point (Pattern A)

This UC falls under **Pattern A: Native S3AP Output**
(see `docs/output-destination-patterns.md`).

**Design**: All AI/ML artifacts are written back to the **same FSx ONTAP
volume** as the source data via the FSxN S3 Access Point — no separate
standard S3 bucket is created ("no data movement" pattern).

**CloudFormation parameters**:
- `S3AccessPointAlias`: Input S3 AP Alias
- `S3AccessPointOutputAlias`: Output S3 AP Alias (can be same as input)

See [README.en.md — AWS Specification Constraints](../../README.en.md#aws-specification-constraints-and-workarounds)
for AWS-side limitations and workarounds.

---
## Storyboard (5 Sections / 3–5 min)

### Section 1: Problem Statement (0:00–0:45)

**Narration Summary**:
> It's audit season. Permission review is needed for thousands of shared folders, but manual verification would take weeks. Unaddressed excessive permissions increase data breach risk.

**Key Visual**: Large folder structure with "Manual audit: estimated 3–4 weeks" overlay

### Section 2: Workflow Trigger (0:45–1:30)

**Narration Summary**:
> Specify the target volume and launch the permission audit workflow.

**Key Visual**: Step Functions execution screen, target path specification

### Section 3: ACL Analysis (1:30–2:30)

**Narration Summary**:
> Automatically collect NTFS ACLs from each folder and detect violations against these rules:
> - Excessive permissions for Everyone / Authenticated Users
> - Accumulated unnecessary inheritance
> - Remaining accounts of departed employees

**Key Visual**: Parallel ACL scanning progress

### Section 4: Results Review (2:30–3:45)

**Narration Summary**:
> Query detection results via SQL. Review violation counts and distribution by risk level.

**Key Visual**: Athena query results — violation list table

### Section 5: Compliance Report (3:45–5:00)

**Narration Summary**:
> AI automatically generates an audit report presenting risk assessment, recommended actions, and prioritized action items.

**Key Visual**: Generated audit report (risk summary + recommended actions)

---

## Screen Capture Plan

| # | Screen | Section |
|---|--------|---------|
| 1 | File server folder structure | Section 1 |
| 2 | Workflow execution start | Section 2 |
| 3 | Parallel ACL scanning | Section 3 |
| 4 | Athena violation detection query results | Section 4 |
| 5 | AI-generated audit report | Section 5 |

---

## Narration Outline

| Section | Time | Key Message |
|---------|------|-------------|
| Problem | 0:00–0:45 | "Manual permission audit of thousands of folders is impractical" |
| Trigger | 0:45–1:30 | "Specify target volume and start the audit" |
| Analysis | 1:30–2:30 | "Automatically collect ACLs and detect policy violations" |
| Results | 2:30–3:45 | "Instantly grasp violation counts and risk levels" |
| Report | 3:45–5:00 | "Auto-generate audit report with prioritized actions" |

---

## Sample Data Requirements

| # | Data | Purpose |
|---|------|---------|
| 1 | Normal permission folders (50+) | Baseline |
| 2 | Everyone Full Control settings (5) | High-risk violations |
| 3 | Departed employee accounts remaining (3) | Medium-risk violations |
| 4 | Excessive inheritance folders (10) | Low-risk violations |

---

## Timeline

### Achievable Within 1 Week

| Task | Duration |
|------|----------|
| Generate sample ACL data | 2 hours |
| Verify workflow execution | 2 hours |
| Capture screenshots | 2 hours |
| Create narration script | 2 hours |
| Video editing | 4 hours |

### Future Enhancements

- Active Directory integration for automatic departed employee detection
- Real-time permission change monitoring
- Automated remediation action execution

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Workflow orchestration |
| Lambda (ACL Collector) | NTFS ACL metadata collection |
| Lambda (Policy Checker) | Policy violation rule matching |
| Lambda (Report Generator) | Audit report generation via Bedrock |
| Amazon Athena | SQL analysis of violation data |

### Fallback

| Scenario | Response |
|----------|----------|
| ACL collection failure | Use pre-collected data |
| Bedrock delay | Display pre-generated report |

---

*This document serves as a production guide for technical presentation demo videos.*
