# DICOM Anonymization Workflow — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | English | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> Note: This translation is produced by Amazon Bedrock Claude. Contributions to improve translation quality are welcome.

## Executive Summary

This demo demonstrates a medical image (DICOM) de-identification workflow. It shows the process of automatically removing patient personal information for research data sharing and verifying de-identification quality.

**Core Demo Message**: Automatically remove patient identifiable information from DICOM files and securely generate de-identified datasets available for research use.

**Estimated Time**: 3–5 minutes

---

## Target Audience & Persona

| Item | Details |
|------|------|
| **Role** | Healthcare Information Manager / Clinical Research Data Manager |
| **Daily Work** | Medical image management, research data provision, privacy protection |
| **Challenge** | Manual de-identification of large volumes of DICOM files is time-consuming and carries risk of errors |
| **Expected Outcome** | Automation of secure and reliable de-identification with audit trails |

### Persona: Takahashi-san (Clinical Research Data Manager)

- Needs to de-identify 10,000+ DICOM files for multi-center collaborative research
- Required to reliably remove patient names, IDs, dates of birth, etc.
- "I want to guarantee zero de-identification leaks while maintaining image quality"

---

## Demo Scenario: DICOM De-identification for Research Data Sharing

### Overall Workflow

```
DICOM Files        Tag Analysis     De-identification   Quality Verification
(with patient   →  Metadata      →  Remove PII       →  Confirm anonymization
 information)      Extraction       Hashing             Report generation
```

---

## Storyboard (5 Sections / 3–5 minutes)

### Section 1: Problem Statement (0:00–0:45)

**Narration Summary**:
> Need to de-identify 10,000 DICOM files for multi-center collaborative research. Manual processing carries risk of errors, and personal information leakage is unacceptable.

**Key Visual**: DICOM file list, highlighted patient information tags

### Section 2: Workflow Trigger (0:45–1:30)

**Narration Summary**:
> Specify the dataset to be de-identified and trigger the de-identification workflow. Configure de-identification rules (removal, hashing, generalization).

**Key Visual**: Workflow trigger, de-identification rule configuration screen

### Section 3: De-identification (1:30–2:30)

**Narration Summary**:
> Automatically process personal information tags in each DICOM file. Patient name → hash, date of birth → age range, facility name → anonymous code. Image pixel data is preserved.

**Key Visual**: De-identification processing progress, before/after tag conversion

### Section 4: Quality Verification (2:30–3:45)

**Narration Summary**:
> Automatically verify de-identified files. Scan all tags for any remaining personal information. Also verify image integrity.

**Key Visual**: Verification results — de-identification success rate, list of remaining risk tags

### Section 5: Audit Report (3:45–5:00)

**Narration Summary**:
> Automatically generate audit report of de-identification processing. Record number of files processed, number of removed tags, verification results. Can be used as submission material for research ethics committee.

**Key Visual**: Audit report (processing summary + compliance trail)

---

## Screen Capture Plan

| # | Screen | Section |
|---|------|-----------|
| 1 | DICOM file list (before de-identification) | Section 1 |
| 2 | Workflow trigger / rule configuration | Section 2 |
| 3 | De-identification processing progress | Section 3 |
| 4 | Quality verification results | Section 4 |
| 5 | Audit report | Section 5 |

---

## Narration Outline

| Section | Time | Key Message |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "De-identification leaks in large volumes of DICOM are unacceptable" |
| Trigger | 0:45–1:30 | "Configure de-identification rules and trigger workflow" |
| Processing | 1:30–2:30 | "Automatically remove personal information tags, maintain image quality" |
| Verification | 2:30–3:45 | "Confirm zero de-identification leaks with full tag scan" |
| Report | 3:45–5:00 | "Automatically generate audit trail, submittable to ethics committee" |

---

## Sample Data Requirements

| # | Data | Purpose |
|---|--------|------|
| 1 | Test DICOM files (20 files) | Main processing target |
| 2 | DICOM with complex tag structure (5 files) | Edge cases |
| 3 | DICOM with private tags (3 files) | High-risk verification |

---

## Timeline

### Achievable Within 1 Week

| Task | Time Required |
|--------|---------|
| Prepare test DICOM data | 3 hours |
| Verify pipeline execution | 2 hours |
| Capture screenshots | 2 hours |
| Create narration script | 2 hours |
| Video editing | 4 hours |

### Future Enhancements

- Automatic detection and removal of burned-in text in images
- De-identification mapping management via FHIR integration
- Differential de-identification (incremental processing of additional data)

---

## Technical Notes

| Component | Role |
|--------------|------|
| Step Functions | Workflow orchestration |
| Lambda (Tag Parser) | DICOM tag analysis and PII detection |
| Lambda (De-identifier) | Tag de-identification processing |
| Lambda (Verifier) | De-identification quality verification |
| Lambda (Report Generator) | Audit report generation |

### Fallback

| Scenario | Response |
|---------|------|
| DICOM parse failure | Use pre-processed data |
| Verification error | Switch to manual verification flow |

---

*This document is a production guide for demo videos for technical presentations.*

---

## About Output Destination: FSxN S3 Access Point (Pattern A)

UC5 healthcare-dicom is classified as **Pattern A: Native S3AP Output**
(see `docs/output-destination-patterns.md`).

**Design**: DICOM metadata, de-identification results, and PII detection logs are all written back via FSxN S3 Access Point to the **same FSx ONTAP volume** as the original DICOM medical images. No standard S3 bucket is created ("no data movement" pattern).

**CloudFormation Parameters**:
- `S3AccessPointAlias`: S3 AP Alias for reading input data
- `S3AccessPointOutputAlias`: S3 AP Alias for writing output (can be the same as input)

**Deployment Example**:
```bash
aws cloudformation deploy \
  --template-file healthcare-dicom/template-deploy.yaml \
  --stack-name fsxn-healthcare-dicom-demo \
  --parameter-overrides \
    S3AccessPointAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    S3AccessPointOutputAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    ... (other required parameters)
```

**View from SMB/NFS Users**:
```
/vol/dicom/
  ├── patient_001/study_A/image.dcm    # Original DICOM
  └── metadata/patient_001/             # AI de-identification results (same volume)
      └── study_A_anonymized.json
```

For AWS specification constraints, see
[the "AWS Specification Constraints and Workarounds" section in the project README](../../README.md#aws-仕様上の制約と回避策)
and [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md).

---

## Verified UI/UX Screenshots

Following the same policy as Phase 7 UC15/16/17 and UC6/11/14 demos, targeting **UI/UX screens that end users actually see in daily work**. Technical views (Step Functions graph, CloudFormation stack events, etc.) are consolidated in `docs/verification-results-*.md`.

### Verification Status for This Use Case

- ⚠️ **E2E Verification**: Partial functionality only (additional verification recommended in production)
- 📸 **UI/UX Capture**: ✅ SFN Graph completed (Phase 8 Theme D, commit c66084f)

### Captured in 2026-05-10 Redeployment Verification (UI/UX Focus)

#### UC5 Step Functions Graph view (SUCCEEDED)

![UC5 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc5-demo/uc5-stepfunctions-graph.png)

Step Functions Graph view is the most important end-user screen that visualizes the execution status of each Lambda / Parallel / Map state with colors.

### Existing Screenshots (Applicable from Phase 1-6)

![UC5 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc5-demo/step-functions-graph-succeeded.png)

![UC5 Step Functions Graph (Zoomed view — each step detail)](../../docs/screenshots/masked/uc5-demo/step-functions-graph-zoomed.png)

### UI/UX Target Screens for Re-verification (Recommended Capture List)

- S3 output bucket (dicom-metadata/, deid-reports/, diagnoses/)
- Comprehend Medical entity detection results (Cross-Region)
- De-identified DICOM metadata JSON

### Capture Guide

1. **Preparation**:
   - Verify prerequisites with `bash scripts/verify_phase7_prerequisites.sh` (check for shared VPC/S3 AP)
   - Package Lambda with `UC=healthcare-dicom bash scripts/package_generic_uc.sh`
   - Deploy with `bash scripts/deploy_generic_ucs.sh UC5`

2. **Place Sample Data**:
   - Upload sample files to `dicom/` prefix via S3 AP Alias
   - Trigger Step Functions `fsxn-healthcare-dicom-demo-workflow` (input `{}`)

3. **Capture** (close CloudShell/terminal, mask username in browser top-right):
   - Overview of S3 output bucket `fsxn-healthcare-dicom-demo-output-<account>`
   - Preview of AI/ML output JSON (refer to `build/preview_*.html` format)
   - SNS email notification (if applicable)

4. **Masking**:
   - Auto-mask with `python3 scripts/mask_uc_demos.py healthcare-dicom-demo`
   - Additional masking as needed following `docs/screenshots/MASK_GUIDE.md`

5. **Cleanup**:
   - Delete with `bash scripts/cleanup_generic_ucs.sh UC5`
   - VPC Lambda ENI release takes 15-30 minutes (AWS specification)
