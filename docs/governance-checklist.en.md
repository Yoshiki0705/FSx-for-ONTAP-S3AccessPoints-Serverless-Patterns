# Governance Checklist — For Regulated, Public Sector, and Healthcare Workloads

🌐 **Language / 言語**: [日本語](governance-checklist.md) | [English](governance-checklist.en.md)

## Overview

This checklist organizes governance verification items when adopting these patterns for regulated, public sector workloads such as Healthcare (UC5), Government Archives (UC16), Education/Research (UC13), and Defense (UC15).

> **Important**: AI/ML processing outputs in this repository are **decision support** and assume that final decisions are made by humans. For areas with significant business impact such as medical diagnosis, administrative actions, and legal judgments, **Human-in-the-loop** is recommended.

### Responsible AI Review Principle

These patterns treat AI outputs as assistive signals, not final decisions. The goal is to make AI-assisted processing:
- **Reviewable** — outputs can be inspected before action
- **Attributable** — processing lineage traces input to output
- **Auditable** — review decisions are recorded with who/when/what

### Executive Summary (For Decision Makers)

This checklist confirms that the following aspects are incorporated into the design:

- **Data classification**: Sensitivity level of processing target data (personal information, medical information, sensitive information, public documents) has been identified
- **Access control**: Dual-layer authorization with AWS IAM and file system permissions is designed
- **Auditability**: Processing history, access logs, and data lineage are retained
- **Cross-region**: Feasibility of cross-region invocation for certain AI services has been confirmed
- **AI output review**: Human review process for high-risk outputs is defined
- **Operational responsibility**: Responsible parties for incident response, patch management, and cost management are clear
- **Compliance**: Alignment with applicable regulations and guidelines has been confirmed

> Technical details can be verified in the following sections. Decision makers should focus on this summary and the "Pre-deployment Checklist" (at the end).

> **Note**: This document supports architecture and operations review. It does not substitute for legal judgment, compliance assessment, privacy evaluation, or regulatory response. Final regulatory determinations must be made by the responsible organization's legal and compliance departments.

---

## 1. Data Classification

| Classification | Description | Example UCs | Additional Measures |
|---------------|-------------|-------------|---------------------|
| Personal Information (PII) | Name, address, phone number, email | UC2, UC14, UC16 | Comprehend PII detection + redaction |
| Medical Information (PHI) | Patient ID, diagnostic info, DICOM metadata | UC5, UC7 | Comprehend Medical + anonymization |
| Sensitive Information | Defense-related, security clearance targets | UC15 | VPC-only processing, encryption required |
| Public Documents | Government documents, FOIA targets, retention-period documents | UC16 | Tamper-proofing, retention period management |
| General Business Data | Manufacturing logs, media files, research data | UC1-4, UC6-14 | Standard encryption and access control |

---

## 2. Data Flow / Storage Locations

| Data | Storage Location | Encryption | Access Control |
|------|-----------------|------------|----------------|
| Input files (originals) | FSx for ONTAP Volume | SSE-FSX (KMS managed) | NTFS ACL / UNIX permissions + S3 AP dual-layer |
| AI/ML processing results | S3 Output Bucket or FSxN S3AP | SSE-KMS or SSE-FSX | IAM + Bucket/AP Policy |
| Execution logs | CloudWatch Logs | SSE (default) | IAM + Log Group Policy |
| Execution history | Step Functions | SSE (default) | IAM |
| Metrics | CloudWatch Metrics | — | IAM |
| AI service invocations | Bedrock / Textract / Comprehend | TLS in-transit | IAM + Service Policy |

---

## 3. Cross-Region Confirmation

| AI Service | ap-northeast-1 Support | Cross-Region Invocation | Verification Items |
|------------|----------------------|------------------------|-------------------|
| Amazon Bedrock | ✅ | Not required | — |
| Amazon Rekognition | ✅ | Not required | — |
| Amazon Comprehend | ✅ | Not required | — |
| Amazon Textract | ❌ | Routed to us-east-1 etc. | Data temporarily sent to another region |
| Comprehend Medical | ❌ | Routed to us-east-1 etc. | PHI sent to another region |

> **Cross-region invocation for regulated data**: For UCs using Textract / Comprehend Medical (UC2, UC5, UC7, UC10, UC12, UC13, UC14), input data is temporarily sent to the supported region. If medical or personal information is included, verify alignment with your organization's data residency requirements.

---

## 4. Audit Logs / Trails

| Log Source | Recorded Content | Retention Period (Recommended) | Tamper-Proofing |
|-----------|-----------------|-------------------------------|-----------------|
| AWS CloudTrail | API call history | 1+ years | S3 Object Lock |
| Step Functions execution history | Workflow execution results | 90 days (default) | — |
| CloudWatch Logs | Lambda execution logs | Set per requirements | — |
| S3 Access Logs | Access records via S3 AP | 1+ years | S3 Object Lock |
| DynamoDB (Lineage) | Data lineage | 7 years (Compliance profile) | S3 Object Lock export |
| FPolicy event logs | File operation events | Per requirements | Persistent Store + SQS |

---

## 5. Human-in-the-loop Design

### AI Output Confidence Levels

| UC | AI Processing Content | Error Impact | Recommended Review Method |
|----|----------------------|--------------|--------------------------|
| UC5 | DICOM image classification/anonymization | High (patient privacy) | Human review of anonymization results required |
| UC16 | Public document PII detection/redaction | High (FOIA compliance) | Human confirmation of redaction results required |
| UC14 | Insurance claim damage assessment | Medium (financial impact) | Human review for high-value cases |
| UC2 | Invoice OCR/data extraction | Medium (financial impact) | Human confirmation below confidence score threshold |
| UC1 | Contract metadata extraction | Low-Medium | Sampling review |
| UC3 | Manufacturing log anomaly detection | Low | Alert notification only |

### Implementation Pattern

```
AI Processing Result
├── Confidence ≥ threshold → Auto-confirm (with logging)
└── Confidence < threshold → Human Review Queue
    ├── SNS notification → Reviewer
    ├── Stored in DynamoDB with pending status
    └── Human confirms/corrects → Finalized
```

### Human Review Points (Specific Examples)

| Review Timing | Target UC | Review Content | Reviewer |
|--------------|-----------|----------------|----------|
| AI classification result review | UC1, UC16 | Is the document category correct? | Legal / Records manager |
| Anonymization result review | UC5, UC16 | Is PII/PHI properly redacted? | Privacy officer |
| Summary result review | UC2, UC14 | Are amounts, dates, and party information accurate? | Business operator |
| Pre-alert approval | UC15 | Pre-issuance confirmation of defense-related alerts | Security officer |
| Pre-external-sharing review | UC16 | Final review of FOIA disclosure documents | Information disclosure officer |
| Variant classification review | UC7 | Confirmation of clinically significant variants | Researcher / Clinician |

### Audit Trail Record Items Example

Example items to record in DynamoDB (or your organization's audit log platform):

| Item | Description | Example |
|------|-------------|---------|
| review_id | Unique review ID | `rev-2026-05-22-001` |
| use_case_id | Target UC | `UC16` |
| object_key | Processing target file | `archives/2026/doc-001.pdf` |
| ai_output_id | AI processing result ID | `step-exec-abc123` |
| reviewer_id | Reviewer ID | `user@example.com` |
| review_timestamp | Review date/time | `2026-05-22T10:30:00Z` |
| review_decision | Decision | `approved` / `rejected` / `escalated` |
| review_comment | Comment | "Corrected redaction scope" |
| confidence_score | AI confidence score | `0.72` |
| escalation_required | Escalation needed | `false` |
| retention_period | Retention period | `7 years` |

### Audit Trail Design Considerations

| Item | Considerations |
|------|---------------|
| Storage | DynamoDB (sample implementation). For actual projects, select based on your organization's SIEM, log platform, or document management system |
| Retention period | Depends on organizational policy (e.g., FISC 7 years, HIPAA 6 years, NARA permanent) |
| Access permissions | Audit personnel read-only. Operations team write-only |
| Deletion policy | Auto-deletion or archival after retention period |
| Tamper-proofing | Periodic export to S3 Object Lock recommended |
| Existing platform integration | CloudWatch Logs → S3 → existing SIEM, or EventBridge → existing audit platform |

### Tamper-Proofing Implementation Options

| Option | Description | Applicable Scenario |
|--------|-------------|---------------------|
| S3 Object Lock (Governance/Compliance) | DynamoDB → Export → S3 (Object Lock) | Long-term retention with tamper-proofing required |
| CloudTrail Lake | Immutable store for API call history | AWS API-level auditing |
| DynamoDB Streams → Kinesis → S3 | Real-time archival | Immediate preservation of high-frequency reviews |
| SIEM integration (Splunk, Datadog, etc.) | Transfer to existing audit platform | Organizational unified log management |
| CloudWatch Logs → S3 (Lifecycle) | Long-term log retention | Cost-efficiency priority |

### Separation of Duties

Design audit trail access permissions based on the following separation of duties:

| Role | Permission | Description |
|------|-----------|-------------|
| AI processing executor | Write (record creation) | Automatically recorded by Lambda / Step Functions |
| Reviewer | Write (decision recording) | Records Human Review results |
| Approver | Write (approval recording) | Final approval for escalated cases |
| Auditor | Read-only | Reference and report generation during audits |
| System operator | Admin (table settings) | DynamoDB configuration and backup management |

> **Principle**: The person who reviews and the person who approves must not be the same. The person who audits must not perform processing, review, or approval.

> **Note**: The above separation of duties represents general principles. For actual projects, adjust according to each organization's regulations, audit requirements, and staffing. In small organizations where some roles are combined, document the rationale for combining and alternative controls.

> **Note**: The sample implementation in this repository uses DynamoDB, but this is just one example. For actual projects, select the storage destination based on your organization's existing audit log platform (SIEM, Splunk, CloudTrail Lake, etc.).

---

## 6. Responsible AI Guardrails

### Assumptions About AI Usage in This Repository

1. **AI output is decision support**: Final decisions are made by humans
2. **Human-in-the-loop recommended for medical/government documents**: Auto-confirmation only for low-risk processing
3. **Bias and fairness**: Periodically evaluate whether AI model outputs contain bias
4. **Transparency**: Maintain lineage of which input generated which output
5. **Accountability**: Responsibility for AI processing results lies with the operating organization

### UC-Specific Guardrails

| UC | Guardrail | Implementation Method |
|----|-----------|----------------------|
| UC5 (Healthcare) | Anonymization leak detection | Comprehend Medical + human review |
| UC16 (Government) | Over-redaction prevention | Diff review before/after redaction |
| UC15 (Defense) | Classification level confirmation | Human approval gate before output |
| UC7 (Genomics) | Variant misclassification prevention | Cross-reference with known variant DB |

---

## 7. Compliance Mapping

| Regulation/Standard | Applicable UCs | Key Requirements | Response in This Pattern |
|--------------------|---------------|------------------|--------------------------|
| FISC Security Standards | UC2, UC14 | Data encryption, access control, audit trail | KMS encryption + IAM + CloudTrail |
| HIPAA | UC5, UC7 | PHI protection, access logs, encryption | Comprehend Medical + anonymization + audit logs |
| GDPR | UC1, UC2, UC14 | Data minimization, right to erasure, processing records | PII detection + lineage + deletion tracking |
| NARA / FOIA | UC16 | Public document retention, disclosure response, redaction | S3 Object Lock + redaction + retention management |
| Personal Information Protection Act | All UCs | Purpose specification, security management measures | IAM least-privilege + encryption + logging |
| Medical Information Guidelines | UC5 | Three-ministry two-guideline compliance | Encryption + access control + audit |

---

---

## 7a. Periodic Review Frequency

Governance checks need to be re-confirmed periodically, not just at deployment:

| Review Timing | Verification Content |
|--------------|---------------------|
| Quarterly | AI output quality review, Human Review rate confirmation, misclassification/mis-summarization trend analysis |
| On production changes | Governance re-confirmation when data classification changes, new UCs are added, or AI models change |
| Annual | Compliance mapping updates, audit trail retention period confirmation, response to regulatory changes |
| On incident | Root cause analysis, Human-in-the-loop process review, recurrence prevention measures |

> **Note**: The above review frequencies are general guidelines. For actual projects, adjust according to your organization's regulations, audit requirements, data classification level, and system criticality.

---

## 8. Pre-deployment Checklist (For Decision Makers)

- [ ] Has data classification been completed (identification of personal, medical, and sensitive information)?
- [ ] Has the acceptability of cross-region invocation been confirmed?
- [ ] Has the Human-in-the-loop requirement for AI output been determined?
- [ ] Have audit log retention period and tamper-proofing methods been determined?
- [ ] Have data lineage retention requirements been confirmed?
- [ ] Is the shared responsibility model (AWS Shared Responsibility Model) understood?
- [ ] Has the Deployment Profile (PoC / Production / Compliance) been selected?
- [ ] Have incident response procedures been defined?
- [ ] Has a mechanism for periodic AI output quality review been designed?

---

## References

- [Deployment Profiles](deployment-profiles.md)
- [S3AP Dual-Layer Authorization Model](s3ap-authorization-model.md)
- [Partner/SI Delivery Checklist](partner-si-delivery-checklist.md)
- [AWS Shared Responsibility Model](https://aws.amazon.com/compliance/shared-responsibility-model/)
- [Amazon Bedrock Responsible AI](https://aws.amazon.com/bedrock/responsible-ai/)
