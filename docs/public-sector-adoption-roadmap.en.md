# Public Sector Adoption Roadmap

🌐 **Language / 言語**: [日本語](public-sector-adoption-roadmap.md) | [English](public-sector-adoption-roadmap.en.md)

## Overview

A 3-phase roadmap for municipalities, educational institutions, healthcare organizations, and central government agencies adopting these patterns.

> **Note**: This document supports architecture and operations review. It does not substitute for legal judgment, compliance assessment, privacy evaluation, or regulatory response. Final regulatory determinations must be made by the responsible organization's legal and compliance departments.

---

## 3-Phase Roadmap

```
Phase A              Phase B              Phase C
PoC/Validation  →   Limited Production  →  Organization-wide Deployment
(2-4 weeks)         (1-3 months)           (3-6 months)
```

### Correspondence with Production Readiness Levels

| Public Sector Phase | Production Readiness Level | Description |
|--------------------|--------------------------|-------------|
| Phase A: PoC/Validation | Level 1 (Sandbox) → Level 2 (Scheduled) | Manual execution for verification → Periodic execution for stability confirmation |
| Phase B: Limited Production | Level 3 (Monitored) | Establish observability with Dashboard + Alarm + Runbook |
| Phase C: Organization-wide Deployment | Level 4 (Production) | StackSets + CI/CD + SLO + DR + Audit compliance |

Details: [Production Readiness Maturity Model](production-readiness.md)

---

## Phase A: PoC/Validation (2-4 weeks)

### Purpose
- Verify pattern operation and determine applicability
- Confirm alignment with security and governance requirements
- Obtain cost and performance estimates

### Deliverables
- [ ] PoC environment built (single AWS account)
- [ ] 1-2 UC templates deployed and operation confirmed
- [ ] File access via S3 AP verified
- [ ] AI/ML processing result quality evaluated
- [ ] Security review results (S3AP authorization model confirmed)
- [ ] Cost estimate (monthly approximation)
- [ ] PoC report

### Security Review Items
| Item | Verification Content | Judgment |
|------|---------------------|----------|
| Data classification | Identify sensitivity level of processing target data | □ |
| Authorization model | IAM + ONTAP file system identity design | □ |
| Encryption | At-rest (SSE-FSX) + in-transit (TLS) | □ |
| Network | VPC isolation, VPC Endpoint design | □ |
| Logging | CloudTrail, CloudWatch Logs retention design | □ |
| Cross-region | Textract/Comprehend Medical invocation feasibility | □ |

### Go / No-Go Criteria

> **Note**: A successful sample run validates the technical processing path and does not constitute approval for production use, publication, or operational decision-making.

**Phase A → Phase B Transition Conditions**:
- [ ] Target data classification confirmed (presence of personal/medical information)
- [ ] Audit log collection policy agreed upon
- [ ] Human-in-the-loop responsible party defined
- [ ] Business impact of AI output errors evaluated
- [ ] Operations team has confirmed alerts and incident response
- [ ] Cross-region invocation feasibility determined
- [ ] Cost estimate confirmed within budget
- [ ] Impact on end beneficiaries (residents, patients, students) evaluated
- [ ] Business impact and response procedures defined for AI mis-output scenarios
- [ ] Able to explain AI usage purpose, data usage scope, and responsibility boundaries for mis-output to stakeholders
- [ ] Relevant stakeholders identified (business department, IT systems, security, privacy officer)

**Judgment**:
- ✅ All conditions met → Proceed to Phase B
- ⚠️ Some conditions unmet → Evaluate whether additional measures (enhanced Human-in-the-loop, etc.) can address
- ❌ Critical non-conformance → Consider alternative approaches

---

## Phase B: Limited Production (1-3 months)

### Purpose
- Begin operations with limited production data
- Establish operational procedures and hand over to operations team
- Define SLOs and build monitoring framework

### Deliverables
- [ ] Production environment built (Production Deployment Profile)
- [ ] Operations Runbook created
- [ ] Alarms and dashboards configured
- [ ] SLO defined (detection latency, error rate, availability)
- [ ] Incident response procedure drills conducted
- [ ] Operations handover documentation
- [ ] Monthly operations report template
- [ ] Security audit preparation

### Operations Design Items
| Item | Design Content |
|------|---------------|
| Monitoring | CloudWatch Dashboard + Alarm Profile (BATCH/REALTIME) |
| Incident response | Runbook + SNS notification + escalation flow |
| Change management | CloudFormation update procedures + pre-verification in test environment |
| Backup | FSx SnapMirror + S3 versioning (Output Bucket) |
| Patch management | Lambda Runtime updates + EC2 AMI updates (for EC2 configurations) |
| Cost management | Monthly cost review + Budget Alert |

### Governance Response
| Item | Response Content |
|------|-----------------|
| Human-in-the-loop | Build review framework for high-risk AI outputs |
| Audit trail | Set retention periods for CloudTrail + DynamoDB Lineage |
| Data lineage | Ensure processing history traceability |
| Incident response | Define response procedures for AI mis-output |

---

## Phase C: Organization-wide Deployment (3-6 months)

### Purpose
- Expand to multiple departments and workloads
- Migrate to multi-account configuration
- Establish organization-wide governance framework

### Deliverables
- [ ] Multi-account configuration (StackSets deployment)
- [ ] Multiple UCs in production operation
- [ ] Cross-organizational dashboard
- [ ] Compliance response completed (FISC/Personal Information Protection Act, etc.)
- [ ] Periodic AI output quality review framework
- [ ] Operational improvement cycle established
- [ ] Reflected in next fiscal year budget planning

### Expansion Pattern

```
[Phase A: 1 department × 1 UC]
    ↓
[Phase B: 1 department × 2-3 UCs]
    ↓
[Phase C-1: 2-3 departments × 1-2 UCs each]
    ↓
[Phase C-2: Organization-wide × Standardized]
```

### Multi-Account Configuration

```
Management Account
├── Shared Services Account (monitoring/log aggregation)
├── Workload Account A (Department A)
│   ├── UC1 (Legal/Compliance)
│   └── UC2 (Financial/IDP)
├── Workload Account B (Department B)
│   ├── UC5 (Healthcare/DICOM)
│   └── UC16 (Government Archives)
└── Security Account (CloudTrail aggregation/GuardDuty)
```

---

## Public Sector-Specific Considerations

### Mini-Scenarios by Domain

#### Municipalities
| Scenario | Corresponding UC | Expected Benefit | Key Stakeholders |
|----------|-----------------|------------------|------------------|
| Automatic classification/search of public document archives | UC16 | Reduced FOIA response time | General Affairs, Information Policy, Records Management |
| Automatic organization/metadata tagging of audit materials | UC1 | Reduced audit preparation effort | Audit Office, IT Systems |
| Geospatial analysis of disaster prevention/urban planning data | UC17 | Faster disaster risk assessment | Disaster Prevention, Urban Planning, GIS |

#### Educational Institutions
| Scenario | Corresponding UC | Expected Benefit | Key Stakeholders |
|----------|-----------------|------------------|------------------|
| Automatic classification/retention management of school documents | UC1, UC16 | Reduced administrative burden on teachers | Board of Education, School Administration, IT |
| Organization/searchability improvement of teaching materials/learning data | UC13 | Improved teaching material reuse rate | Academic Affairs, ICT Support |
| Automatic generation of educational data analysis reports | UC13 | Data-driven educational improvement | Board of Education, Data Analysis |

#### Healthcare Organizations
| Scenario | Corresponding UC | Expected Benefit | Key Stakeholders |
|----------|-----------------|------------------|------------------|
| Automatic classification/metadata organization of DICOM images | UC5 | Improved radiology search efficiency | Radiology, Medical IT, PACS Admin |
| Discharge summary/medical record summarization support | UC2 | Reduced physician documentation burden | Medical Records, Medical IT |
| Research data classification/anonymization review | UC7, UC5 | Promoted research data utilization | Research Support Center, Ethics Committee, Privacy Officer |

> **Note**: AI processing outputs in the above scenarios are decision support. Final decisions for medical diagnosis, administrative actions, and educational evaluation are made by humans.

### Cache-Aware Routing / Read-Path Resilience Checkpoints

Additional verification items when considering the FlexCache Anycast/DR pattern (FC1):

| Item | Verification Content |
|------|---------------------|
| Authoritative data source | Which volume is the authoritative source |
| Cache access policy | Who can access the cache volume |
| Failover decision maker | Who is the decision owner |
| Approval flow | Route change approval process |
| Route change audit trail | How change records are retained and referenced |
| Audit trail reviewer | Who reviews the audit trail |
| Operations owner | Who is responsible for daily operations and incident response |

### Procurement and Contracts
| Item | Considerations |
|------|---------------|
| AWS usage agreement | Confirm government-specific contract terms |
| Data location | Confirm processing in domestic region (ap-northeast-1) |
| Cross-region | Determine Textract/Comprehend Medical usage feasibility |
| Third-party certification | Confirm SOC 2, ISO 27001, ISMAP, etc. |

### Regulatory Mapping
| Regulation | Target UCs | Key Requirements |
|-----------|-----------|------------------|
| Personal Information Protection Act | All UCs | Purpose specification, security management measures |
| Administrative Agency Personal Information Protection Act | UC16 | Proper management of administrative documents |
| Medical Information Guidelines | UC5 | Three-ministry two-guideline compliance |
| FISC Security Standards | UC2, UC14 | Financial institution security |
| Educational Data Utilization | UC13 | Proper management of learning data |

### Human Resource Development
| Phase | Required Skills | Development Method |
|-------|----------------|-------------------|
| Phase A | CloudFormation basics, S3 AP concept understanding | AWS Training + PoC hands-on |
| Phase B | Operations monitoring, incident response, security | Runbook drills + OJT |
| Phase C | Multi-account design, CI/CD | AWS SA support + Partner collaboration |

---

## References

- [Governance Checklist](governance-checklist.md)
- [Production Readiness](production-readiness.md)
- [Partner/SI Delivery Checklist](partner-si-delivery-checklist.md)
- [Deployment Profiles](deployment-profiles.md)
- [Customer Discovery Template](customer-discovery-template.md)
