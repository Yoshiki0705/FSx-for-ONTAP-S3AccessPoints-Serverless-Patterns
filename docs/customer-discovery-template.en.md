# Customer Discovery Template — Hearing Sheet

🌐 **Language / 言語**: [日本語](customer-discovery-template.md) | [English](customer-discovery-template.en.md)

## Overview

This template organizes the questions for initial customer hearings to determine the applicability of FSx for ONTAP S3 Access Points serverless patterns.

---

## 1. Current Data Access

| Question | Response | Design Impact |
|----------|----------|---------------|
| What protocol is used to access existing data? | SMB / NFS / Both / S3 | FPolicy compatibility, S3 AP identity type |
| What NFS version is in use? | NFSv3 / NFSv4.0 / NFSv4.1 / NFSv4.2 | NFSv4.2 is not supported by FPolicy |
| What is the current storage? | FSx for ONTAP / On-prem ONTAP / Other NAS / S3 | Migration requirement assessment |
| What is the data volume? | ___TB, ___ million files | FSx sizing, Map concurrency |
| What is the average file size? | Small (<1MB) / Medium (1-100MB) / Large (>100MB) | Lambda memory, processing strategy |

---

## 2. Why Data Cannot Be Copied to S3

| Question | Response | Design Impact |
|----------|----------|---------------|
| Is cost (duplicate storage) a concern? | Yes / No | S3 AP "no data movement" value proposition |
| Are there regulatory restrictions on data duplication? | Yes / No | Governance Checklist applicability |
| Is the operational burden of synchronization mechanisms a concern? | Yes / No | S3 AP operational simplification value |
| Do NFS/SMB users also need to see AI processing results? | Yes / No | OutputDestination=FSXN_S3AP |
| Is data freshness (recency) important? | Yes / No | Polling interval or EVENT_DRIVEN |

---

## 3. AI/ML Processing Requirements

| Question | Response | Design Impact |
|----------|----------|---------------|
| What processing do you want to automate? | OCR / Classification / Summarization / Anomaly detection / Image analysis / Other | UC pattern selection |
| Who will view the AI/ML processing results? | Business users / Analysts / Auditors / System integration | Output destination/format design |
| Where do you want to view processing results? | Same file server / S3 / BI tools / API | OutputDestination selection |
| Is automatic confirmation of AI output acceptable? | Yes / Conditional / No (human review required) | Human-in-the-loop design |
| Does the processing target data contain personal information? | Yes / No / Unknown | PII detection, Governance |

---

## 4. Latency and Frequency Requirements

| Question | Response | Design Impact |
|----------|----------|---------------|
| What is the acceptable time from file change to processing completion? | Real-time / Minutes / 1 hour / Daily / Weekly | TriggerMode selection |
| What is the processing frequency? | Continuous / Business hours only / Daily batch / Weekly | Business Hours Scheduling |
| What is the peak file generation rate? | ___ files/hour | Map concurrency, FSx throughput |

---

## 5. Audit and Compliance Requirements

| Question | Response | Design Impact |
|----------|----------|---------------|
| What is the audit log retention period? | 1 year / 3 years / 7 years / Permanent | S3 Object Lock, Lineage |
| Is event loss acceptable? | Yes / No | Persistent Store requirement |
| Are there data region constraints? | Domestic only / Specific region / No constraints | Cross-region invocation feasibility |
| Is tamper-proofing required? | Yes / No | S3 Object Lock |
| Are periodic audit reports required? | Yes / No | Lineage export + reporting |

---

## 6. Operations and Organization

| Question | Response | Design Impact |
|----------|----------|---------------|
| What is the AWS account structure? | Single / Multi-account / Organizations | StackSets, Cross-Account |
| What is the operations team's AWS experience level? | Beginner / Intermediate / Advanced | Maturity Level selection |
| Is there an existing CI/CD pipeline? | Yes / No | Deployment approach |
| What is the incident response structure? | Auto-recovery only / Business hours / 24/7 | Alarm Profile, Runbook |
| What is the budget limit? | ___/month | Cost optimization design |

---

## 7. Next Steps Decision Matrix

Based on hearing results, recommend the following paths:

| Condition | Recommended Path |
|-----------|-----------------|
| "Want to see something working first" | Level 1 Sandbox → 30-minute path |
| "Want periodic automated processing" | Level 2 Scheduled → 60-minute path |
| "Want to use in production" | Level 3-4 → 1-day workshop |
| "Handling regulated data" | Governance Checklist + Compliance Profile |
| "Need real-time detection" | EVENT_DRIVEN + Deployment Profiles |

---

---

## 7a. Sample Data Policy

At PoC initiation, confirm the nature of the data to be used:

| # | Question | Response |
|---|----------|----------|
| 1 | Will the PoC use synthetic data, anonymized data, or production-like data? | |
| 2 | Who approves the use of sample data? | |
| 3 | Does the sample data contain personal information, regulated information, or confidential information? | |
| 4 | Is masking or anonymization required before testing? | |
| 5 | What is the test data deletion policy after PoC completion? | |

## 8. Cache / Clone / RAG Governance Questions

Additional questions when considering FlexCache / FlexClone / RAG patterns:

| # | Question | Response Format |
|---|----------|----------------|
| 1 | Does the workload use cached or cloned data? | Yes / No |
| 2 | Which volume is the authoritative source? | Volume name + Data owner |
| 3 | Which teams can access the cache/clone volume? | Team name + Approver |
| 4 | Who can approve route changes or failover decisions? | Decision owner + Approval role |
| 5 | Should route changes be recorded as audit events? | Yes / No + Retention period |
| 6 | Do file system permissions (ACL / groups) need to be preserved in RAG preprocessing? | Yes / No |
| 7 | Who reviews AI-generated output before external sharing or business use? | Reviewer |
| 8 | What is the retention period for review trails and route change logs? | Period + Deletion authority |
| 9 | Who can delete or modify review trails? | Authorized person |

## References

- [Choose Your Path](../README.md#choose-your-path)
- [Production Readiness](production-readiness.md)
- [Governance Checklist](governance-checklist.md)
- [Partner/SI Delivery Checklist](partner-si-delivery-checklist.md)
- [Trigger Mode Decision Guide](trigger-mode-decision-guide.md)
