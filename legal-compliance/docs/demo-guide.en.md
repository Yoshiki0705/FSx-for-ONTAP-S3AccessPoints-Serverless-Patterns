# File Server Permission Audit — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | English | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> Note: This translation is produced by Amazon Bedrock Claude. Contributions to improve translation quality are welcome.

## Executive Summary

This demo demonstrates an audit workflow that automatically detects excessive access permissions on file servers. It parses NTFS ACLs, identifies entries that violate the principle of least privilege, and automatically generates compliance reports.

**Core Demo Message**: Automate file server permission audits that would take weeks manually, and instantly visualize the risk of excessive permissions.

**Estimated Time**: 3–5 minutes

---

## Target Audience & Persona

| Item | Details |
|------|------|
| **Role** | Information Security Officer / IT Compliance Manager |
| **Daily Tasks** | Access permission reviews, audit response, security policy management |
| **Challenge** | Manually checking permissions on thousands of folders is impractical |
| **Expected Outcome** | Early detection of excessive permissions and automated compliance audit trails |

### Persona: Mr. Sato (Information Security Manager)

- Annual audit requires permission review of all shared folders
- Wants to immediately detect dangerous settings like "Everyone Full Control"
- Wants to efficiently create reports for submission to audit firms

---

## Demo Scenario: Automating Annual Permission Audits

### Overall Workflow

```
File Server      ACL Collection    Permission Analysis    Report Generation
(NTFS Shares) →  Metadata      →   Violation Detection → Audit Report
                 Extraction        (Rule Matching)       (AI Summary)
```

---

## Storyboard (5 Sections / 3–5 minutes)

### Section 1: Problem Statement (0:00–0:45)

**Narration Summary**:
> It's annual audit time. Permission reviews are required for thousands of shared folders, but manual verification takes weeks. If excessive permissions are left unaddressed, the risk of information leakage increases.

**Key Visual**: Large folder structure with "Manual Audit: Estimated 3–4 weeks" overlay

### Section 2: Workflow Trigger (0:45–1:30)

**Narration Summary**:
> Specify the volume to be audited and launch the permission audit workflow.

**Key Visual**: Step Functions execution screen, target path specification

### Section 3: ACL Analysis (1:30–2:30)

**Narration Summary**:
> Automatically collect NTFS ACLs for each folder and detect violations using the following rules:
> - Excessive permissions for Everyone / Authenticated Users
> - Accumulation of unnecessary inheritance
> - Remaining accounts of former employees

**Key Visual**: ACL scan progress via parallel processing

### Section 4: Results Review (2:30–3:45)

**Narration Summary**:
> Query detection results with SQL. Review violation counts and distribution by risk level.

**Key Visual**: Athena query results — violation list table

### Section 5: Compliance Report (3:45–5:00)

**Narration Summary**:
> AI automatically generates an audit report. Presents risk assessment, recommended actions, and prioritized action items.

**Key Visual**: Generated audit report (risk summary + action recommendations)

---

## Screen Capture Plan

| # | Screen | Section |
|---|------|-----------|
| 1 | File server folder structure | Section 1 |
| 2 | Workflow execution start | Section 2 |
| 3 | ACL scan parallel processing in progress | Section 3 |
| 4 | Athena violation detection query results | Section 4 |
| 5 | AI-generated audit report | Section 5 |

---

## Narration Outline

| Section | Time | Key Message |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "Manually auditing permissions on thousands of folders is impractical" |
| Trigger | 0:45–1:30 | "Specify target volume and start audit" |
| Analysis | 1:30–2:30 | "Automatically collect ACLs and detect policy violations" |
| Results | 2:30–3:45 | "Instantly understand violation counts and risk levels" |
| Report | 3:45–5:00 | "Automatically generate audit report, present action priorities" |

---

## Sample Data Requirements

| # | Data | Purpose |
|---|--------|------|
| 1 | Folders with normal permissions (50+) | Baseline |
| 2 | Everyone Full Control settings (5 cases) | High-risk violations |
| 3 | Remaining former employee accounts (3 cases) | Medium-risk violations |
| 4 | Excessive inheritance folders (10 cases) | Low-risk violations |

---

## Timeline

### Achievable Within 1 Week

| Task | Time Required |
|--------|---------|
| Generate sample ACL data | 2 hours |
| Verify workflow execution | 2 hours |
| Capture screenshots | 2 hours |
| Create narration script | 2 hours |
| Video editing | 4 hours |

### Future Enhancements

- Automatic detection of former employees via Active Directory integration
- Real-time permission change monitoring
- Automatic execution of remediation actions

---

## Technical Notes

| Component | Role |
|--------------|------|
| Step Functions | Workflow orchestration |
| Lambda (ACL Collector) | NTFS ACL metadata collection |
| Lambda (Policy Checker) | Policy violation rule matching |
| Lambda (Report Generator) | Audit report generation via Bedrock |
| Amazon Athena | SQL analysis of violation data |

### Fallback

| Scenario | Response |
|---------|------|
| ACL collection failure | Use pre-collected data |
| Bedrock delay | Display pre-generated report |

---

*This document is a production guide for demo videos for technical presentations.*

---

## About Output Destination: FSxN S3 Access Point (Pattern A)

UC1 legal-compliance is classified as **Pattern A: Native S3AP Output**
(see `docs/output-destination-patterns.md`).

**Design**: Contract metadata, audit logs, and summary reports are all written back via FSxN S3 Access Point to
the **same FSx ONTAP volume** as the original contract data. No standard S3 bucket is
created ("no data movement" pattern).

**CloudFormation Parameters**:
- `S3AccessPointAlias`: S3 AP Alias for reading input contract data
- `S3AccessPointOutputAlias`: S3 AP Alias for output writing (can be the same as input)

**Deployment Example**:
```bash
aws cloudformation deploy \
  --template-file legal-compliance/template-deploy.yaml \
  --stack-name fsxn-legal-compliance-demo \
  --parameter-overrides \
    S3AccessPointAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    S3AccessPointOutputAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    ... (other required parameters)
```

**How SMB/NFS users see it**:
```
/vol/contracts/
  ├── 2026/Q2/contract_ABC.pdf         # Original contract
  └── summaries/2026/05/                # AI-generated summary (same volume)
      └── contract_ABC.json
```

For AWS specification constraints, see
[the "AWS Specification Constraints and Workarounds" section in the project README](../../README.md#aws-仕様上の制約と回避策)
and [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md).

---

## Verified UI/UX Screenshots

Following the same policy as Phase 7 UC15/16/17 and UC6/11/14 demos, we target **UI/UX screens that
end users actually see in daily operations**. Technical views (Step Functions graphs, CloudFormation
stack events, etc.) are consolidated in `docs/verification-results-*.md`.

### Verification Status for This Use Case

- ✅ **E2E Execution**: Verified in Phase 1-6 (see root README)
- 📸 **UI/UX Re-capture**: ✅ Captured in 2026-05-10 redeployment verification (UC1 Step Functions graph, Lambda execution success confirmed)
- 🔄 **Reproduction Method**: See "Capture Guide" at the end of this document

### Captured in 2026-05-10 Redeployment Verification (UI/UX Focus)

#### UC1 Step Functions Graph view (SUCCEEDED)

![UC1 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc1-demo/uc1-stepfunctions-graph.png)

Step Functions Graph view is the most important end-user screen that visualizes the execution status
of each Lambda / Parallel / Map state with colors.

#### UC1 Step Functions Graph (SUCCEEDED — Phase 8 Theme D/E/N Verification, 2:38:20)

![UC1 Step Functions Graph (SUCCEEDED)](../../docs/screenshots/masked/uc1-demo/step-functions-graph-succeeded.png)

Executed with Phase 8 Theme E (event-driven) + Theme N (observability) enabled.
549 ACL iterations, 3871 events, all steps SUCCEEDED in 2:38:20.

#### UC1 Step Functions Graph (Zoomed View — Step Details)

![UC1 Step Functions Graph (Zoomed View)](../../docs/screenshots/masked/uc1-demo/step-functions-graph-zoomed.png)

#### UC1 S3 Access Points for FSx ONTAP (Console View)

![UC1 S3 Access Points for FSx ONTAP](../../docs/screenshots/masked/uc1-demo/s3-access-points-for-fsx.png)

#### UC1 S3 Access Point Details (Overview View)

![UC1 S3 Access Point Details](../../docs/screenshots/masked/uc1-demo/s3ap-detail-overview.png)

### Existing Screenshots (Relevant from Phase 1-6)

#### UC1 CloudFormation Stack Deployment Complete (2026-05-02 Verification)

![UC1 CloudFormation Stack Deployment Complete (2026-05-02 Verification)](../../docs/screenshots/masked/phase1/phase1-cloudformation-uc1-deployed.png)

#### UC1 Step Functions SUCCEEDED (E2E Execution Success)

![UC1 Step Functions SUCCEEDED (E2E Execution Success)](../../docs/screenshots/masked/phase1/phase1-step-functions-uc1-succeeded.png)


### UI/UX Target Screens for Re-verification (Recommended Capture List)

- S3 output bucket (audit-reports/, acl-audits/, athena-results/ prefixes)
- Athena query results (ACL violation detection SQL)
- Bedrock-generated audit report (compliance violation summary)
- SNS notification email (audit alert)

### Capture Guide

1. **Preparation**:
   - Verify prerequisites with `bash scripts/verify_phase7_prerequisites.sh` (check for shared VPC/S3 AP)
   - Package Lambda with `UC=legal-compliance bash scripts/package_generic_uc.sh`
   - Deploy with `bash scripts/deploy_generic_ucs.sh UC1`

2. **Place Sample Data**:
   - Upload sample files to `contracts/` prefix via S3 AP Alias
   - Start Step Functions `fsxn-legal-compliance-demo-workflow` (input `{}`)

3. **Capture** (close CloudShell/terminal, mask username in browser top-right):
   - Overview of S3 output bucket `fsxn-legal-compliance-demo-output-<account>`
   - Preview of AI/ML output JSON (refer to `build/preview_*.html` format)
   - SNS email notification (if applicable)

4. **Masking**:
   - Auto-mask with `python3 scripts/mask_uc_demos.py legal-compliance-demo`
   - Apply additional masking as needed per `docs/screenshots/MASK_GUIDE.md`

5. **Cleanup**:
   - Delete with `bash scripts/cleanup_generic_ucs.sh UC1`
   - VPC Lambda ENI release takes 15-30 minutes (AWS specification)

---

## Execution Time Estimates (Phase 8 Verification Results)

UC1 processing time is proportional to the number of files on the ONTAP volume.

| Step | Processing Content | Actual Time (549 files) |
|---------|---------|---------------------|
| Discovery | Retrieve file list via ONTAP REST API | 8 minutes |
| AclCollection (Map) | Collect NTFS ACL for each file | 2 hours 20 minutes |
| AthenaAnalysis | Glue Data Catalog + Athena query | 5 minutes |
| ReportGeneration | Report generation with Bedrock Nova Lite | 5 minutes |
| **Total** | | **2 hours 38 minutes** |

### Estimated Processing Time by File Count

| File Count | Estimated Total Time | Recommended Use |
|-----------|------------|---------|
| 10 | ~5 minutes | Quick demo |
| 50 | ~15 minutes | Standard demo |
| 100 | ~30 minutes | Detailed verification |
| 500+ | ~2.5 hours | Production-equivalent test |

### Performance Optimization Tips

- **Map state MaxConcurrency**: Increase from default 40 → 100 to reduce AclCollection time
- **Lambda Memory**: 512MB or more recommended for Discovery Lambda (faster VPC ENI attach)
- **Lambda Timeout**: 900s recommended for large file environments (default 300s is insufficient)
- **SnapStart**: Python 3.13 + SnapStart can reduce cold starts by 50-80%

### Phase 8 New Features

- **Event-driven trigger** (`EnableEventDriven=true`): Auto-launch on file addition to S3AP
- **CloudWatch Alarms** (`EnableCloudWatchAlarms=true`): Auto-notification of SFN failures + Lambda errors
- **EventBridge failure notification**: Push notification to SNS Topic on execution failure
