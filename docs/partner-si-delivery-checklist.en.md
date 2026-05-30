# Partner/SI Delivery Checklist

🌐 **Language / 言語**: [日本語](partner-si-delivery-checklist.md) | [English](partner-si-delivery-checklist.en.md)

## Overview

This checklist organizes verification items for partners and SIs when proposing, designing, and building FSx for ONTAP S3 Access Points serverless patterns for customers.

> 📄 **For initial proposals**: [Partner/SI One-Pager](partner-si-one-pager.md) — Grasp What / When / How / Where in one page

## How to Use This Checklist

1. Identify the closest use case or FlexCache/FlexClone pattern
2. Review the relevant Success Metrics
3. Copy the Customer-Ready PoC Plan Template
4. Replace the Sample Baseline with customer-specific measurements
5. Agree on Go / No-Go criteria and next-phase ownership

## Customer Workload Classification

### Step 1: Data Characteristics Verification

| Verification Item | Options | Design Impact |
|-------------------|---------|---------------|
| Workload type | SAP peripheral / File server / Regulated records / AI analytics / Batch processing | UC pattern selection |
| Data protocol | NFSv3 / NFSv4.1 / SMB | FPolicy compatibility (NFSv4.2 not supported) |
| File size distribution | Small (<1MB) / Medium (1-100MB) / Large (100MB-5GB) / Very large (>5GB) | Lambda memory and processing strategy |
| Files per day | ~100 / ~1,000 / ~10,000 / 100,000+ | Map concurrency and cost estimation |
| Data sensitivity | General / Internal confidential / Regulated (FISC/HIPAA/GDPR) | Deployment Profile selection |

### Step 2: Trigger Mode Selection

| Verification Item | Options | Recommended Mode |
|-------------------|---------|-----------------|
| Detection latency requirement | Hourly is acceptable | POLLING |
| | Sub-minute required | EVENT_DRIVEN or HYBRID |
| Event loss tolerance | Acceptable | EVENT_DRIVEN (is-mandatory=false) |
| | Not acceptable | EVENT_DRIVEN + Persistent Store or HYBRID |
| Operational complexity tolerance | Minimal desired | POLLING |
| | Moderate acceptable | EVENT_DRIVEN |
| | High acceptable | HYBRID |

Details: [Trigger Mode Decision Guide](trigger-mode-decision-guide.md)

### Step 3: Deployment Profile Selection

| Verification Item | PoC/Demo | Production | Compliance-sensitive |
|-------------------|----------|------------|---------------------|
| Purpose | Functional verification/demo | Production workloads | Regulatory compliance |
| Event loss | Acceptable | Near-zero | Zero |
| ONTAP version | 9.14.1+ | 9.15.1+ | 9.15.1+ |
| Persistent Store | Not required | Recommended | Required |
| Idempotency guarantee | Not required | DynamoDB | DynamoDB + S3 Object Lock |
| Audit trail | Not required | Recommended | Required |

Details: [Deployment Profiles](deployment-profiles.md)

### Step 4: Access Model Design

| Layer | Verification Item | Design Decision |
|-------|-------------------|-----------------|
| AWS IAM | Lambda Role permission scope | ListBucket + GetObject (minimum) or + PutObject |
| S3 AP Policy | Resource policy configuration | Principal restriction + Condition (OrgID, VPC) |
| VPC Endpoint Policy | VPC restriction requirement | Required for VPC Origin AP |
| SCP | Organization-level controls | Required in regulated environments |
| ONTAP File System | Identity associated with AP | Dedicated user (root prohibited) |
| Security Style | UNIX or NTFS | Match the volume's style |

> **Important**: S3 API access does not bypass ONTAP file system permissions. Least-privilege must be designed on both the AWS side and the ONTAP side.

Details: [S3AP Dual-Layer Authorization Model](s3ap-authorization-model.md)

### Step 5: Network Model

| Configuration | Description | Applicable Scenario |
|--------------|-------------|---------------------|
| Single VPC (Private) | FSx + Lambda + S3AP all in same VPC | Simplest, for PoC |
| VPC Origin AP | AP bound to specific VPC | High-security environments |
| Internet Origin AP + VPC-external Lambda | Lambda runs outside VPC | Workaround for S3 Gateway EP limitation |
| Cross-Account | RAM sharing or Cross-Account IAM | Multi-account environments |
| Shared Services | Centralized monitoring/log aggregation | Enterprise operations |

### Step 6: Operations Model

| Verification Item | Options |
|-------------------|---------|
| Operations owner | Customer self-operated / Partner-operated / Managed service |
| Monitoring | CloudWatch Alarm only / Dashboard + Alarm / SLO + Runbook |
| Incident response | Auto-recovery only / Runbook manual response / 24/7 on-call |
| Change management | Manual deploy / CI/CD (StackSets) / GitOps |
| Cost management | Fixed budget / Usage monitoring / Cost Anomaly Detection |

### Step 7: Success Criteria Definition

| Metric | Measurement Method | Target (Example) |
|--------|-------------------|------------------|
| Detection latency | EventBridge event timestamp - file creation time | < 30 sec (EVENT_DRIVEN) |
| Processing throughput | Files processed / hour | > 1,000 files/hour |
| Error rate | Failed executions / total executions | < 1% |
| Cost | Monthly AWS bill for the pipeline | < $100/month (PoC) |
| Availability | Pipeline uptime | > 99.5% |
| Recovery time | Time to recover from Fargate task restart | < 5 min |
| Audit compliance | Event lineage completeness | 100% (Compliance profile) |

### Deliverable Templates for Each Step

#### Overall Delivery Flow

```
Discover → Design → Deploy → Validate → Govern → Operate → Optimize
   │          │        │         │         │        │         │
   ▼          ▼        ▼         ▼         ▼        ▼         ▼
Discovery  Architecture  CFn    PoC      Security  Runbook   Cost
  Note      Diagram    Deploy  Results   Review    Handover  Review
```

| Step | Deliverable | Format |
|------|-------------|--------|
| 1. Data characteristics | Discovery Note (data classification, protocol, file profile) | Markdown / Word |
| 2. Trigger mode | Current-state data flow + Target architecture diagram | Draw.io / Mermaid |
| 3. Deployment Profile | Security review checklist (authorization model verification results) | Checklist |
| 4. Access model | IAM + ONTAP permission design document | Markdown |
| 5. Network | Network architecture diagram + VPC Endpoint decision | Draw.io |
| 6. Operations model | Operations handover checklist | Checklist |
| 7. Success criteria | PoC success criteria + Cost estimate | Spreadsheet |

---

## PoC Implementation Guide

### Phase 1: Environment Preparation (1-2 days)

1. Verify FSx for ONTAP file system (existing or create new)
2. Create S3 Access Point + configure file system identity
3. Place test files (via NFS/SMB)
4. Verify ListObjectsV2 / GetObject operation via S3 AP

### Phase 2: POLLING Pattern Validation (1-2 days)

1. Deploy UC template (CloudFormation)
2. Verify periodic execution via EventBridge Scheduler
3. Confirm Discovery Lambda → Processing Lambda → Output
4. Review CloudWatch metrics and logs

### Phase 3: EVENT_DRIVEN Pattern Validation (2-3 days)

1. Deploy FPolicy Server (Fargate or EC2)
2. Configure ONTAP FPolicy (external-engine, policy, scope)
3. Verify NFS/SMB file creation → SQS → EventBridge arrival
4. Verify IP Updater Lambda operation (for Fargate)

### Phase 4: Results Evaluation and Next Steps (1 day)

1. Organize latency, throughput, and cost measurement results
2. Select Deployment Profile (migration plan from PoC → Production)
3. Identify additional requirements (Persistent Store, idempotency, audit, etc.)

---

## Frequently Asked Questions (For Partners)

### Q: Does this affect existing NFS/SMB access?

A: No. Attaching an S3 Access Point does not change existing NFS/SMB access at all. AP policy restrictions apply only to requests via the AP.

### Q: Can this be used with SAP environments?

A: It is suitable for automated processing of SAP peripheral files (IDoc exports, report output, BW data extracts, etc.). Attaching S3 AP directly to SAP HANA data volumes is not recommended (potential performance impact). Use it for SAP peripheral shared file storage.

### Q: What is needed for production use?

A: See the Production profile in [Deployment Profiles](deployment-profiles.md). Key additional requirements: EC2 static IP or NLB, DynamoDB idempotency, full alarm profile, periodic polling for reconciliation.

### Q: Can zero event loss be guaranteed?

A: With the combination of ONTAP 9.14.1+ Persistent Store + is-mandatory=true (ONTAP 9.15.1+), zero event loss has been confirmed in tested scenarios (5-event / 20-event disconnect). However, behavior when Persistent Store volume capacity is exceeded requires additional design.

### Q: What is the cost estimate guideline?

A: POLLING mode (1-hour interval, 1,000 files/day): ~$6-21/month. EVENT_DRIVEN mode: ~$32-60/month (including Fargate 24/7). Processing Lambda cost is workload-dependent.

---

---

## PoC Proposal Example

UC1 (Legal Compliance) PoC proposal template example:

```markdown
### PoC Objective
Automate document discovery and audit report generation for legal file shares stored on FSx for ONTAP.

### Success Criteria
- Process 10,000+ files within the agreed batch window (1 hour)
- Generate a standardized audit report after each scheduled run
- Route files requiring manual review to the Human Review queue (target: < 10%)
- Keep processing cost within the agreed PoC budget (< $100/month)
- Achieve > 50% reduction in manual audit preparation effort

### Measurement Method
- Step Functions execution history (file count, duration, success/failure)
- CloudWatch Metrics (FilesProcessed, Duration, ErrorRate)
- Generated report metadata in S3 output bucket
- Human Review queue records in DynamoDB

### PoC Duration
2-4 weeks (Level 1 Sandbox → Level 2 Scheduled)

### Next Phase Criteria
See [Production Readiness Exit Criteria](production-readiness.md#exit-criterialevel-completion-conditions)
```

> The above is an example for UC1. Refer to each UC's Success Metrics and customize according to the customer's business requirements.

### Industry Expansion Guide

This template can be expanded across all UCs. Industry-specific examples:

| Industry | Reference UC | PoC Objective Example | Typical Stakeholder |
|----------|-------------|----------------------|---------------------|
| Legal / Compliance | UC1 | File server audit and compliance report automation | Legal Ops, Compliance, Audit |
| Public Sector | UC16 | Automatic classification of public document archives and FOIA response acceleration | Digital Transformation Office, Records Management |
| Healthcare | UC5 | Automatic classification and anonymization of DICOM images | Medical IT, Research, Privacy Office |
| Enterprise Integration | SAP/ERP Adjacent | Automated processing of IDoc/HULFT/EDI landing zones | Application Owner, Integration Team, ERP Ops |
| Financial Services | UC2, UC14 | Invoice OCR and insurance assessment report automation | Operations, Risk, Compliance |
| Manufacturing | UC3 | IoT log and quality inspection image anomaly detection | Plant IT, Quality Engineering, Data Platform |

Each UC's Success Metrics can be referenced from the [UC Success Metrics List](#uc-success-metrics-list).

---

---

## FlexCache / FlexClone Pattern Mapping

### By Industry

| Industry | Pattern | Customer Question | Recommended First Question |
|----------|---------|-------------------|---------------------------|
| Cross-industry DR / distributed read | FC1 FlexCache Anycast/DR | "Do you need faster distributed read access without a full independent copy?" | "What is your current read latency from remote sites, and what target would justify a caching layer?" |
| Media / VFX | FC2 Dynamic FlexCache Render | "Do you need per-job isolated cache for render workflows?" | "How many concurrent render jobs share the same source data, and what is the job lifecycle?" |
| Enterprise Knowledge / GenAI | FC3 GenAI RAG | "Do you need permission-aware RAG over enterprise files?" | "Which file shares contain the knowledge base, and do access permissions need to be preserved in RAG results?" |
| Automotive / Manufacturing | FC4 Automotive CAE | "Do you need automated solver output analysis?" | "What is the typical solver output size and how quickly must results be available for post-processing?" |
| Life Sciences / Research | FC5 Life Sciences Research | "Do you need research data classification with controlled collaboration?" | "How do you currently share research datasets between teams while maintaining data governance?" |
| Gaming / Build Pipeline | FC6 Gaming Build Pipeline | "Do you need build asset QC and pipeline acceleration?" | "What is your current build pipeline duration and which asset validation steps are bottlenecks?" |

### By Business Outcome

| Outcome | Pattern |
|---------|---------|
| Faster distributed read access | FC1 |
| Per-job isolated cache lifecycle | FC2 |
| Permission-aware enterprise RAG preprocessing | FC3 |
| Engineering workflow acceleration | FC4 |
| Research data classification and controlled collaboration | FC5 |
| Build asset quality control and pipeline acceleration | FC6 |

### FC1 PoC Success Criteria Example

FC1 FlexCache Anycast/DR pattern PoC success criteria example:

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| Route decision latency | < 500 ms | Step Functions execution duration |
| Cache health detection time | < 30 s | HealthCheck Lambda interval × detection count |
| Read-path recovery time | < 60 s | Time from origin failure to successful cache read |
| False positive failovers (24h test) | 0 | DynamoDB routing table change audit |
| Audit event completeness | 100% | DynamoDB Streams / CloudWatch Logs record count |

> The above are reference values. Adjust according to customer SLA requirements. See [flexcache-anycast-dr/docs/](../flexcache-anycast-dr/docs/) for details.

> FlexCache/FlexClone patterns are optional extensions for customers who need distributed read access, dataset branching, cache lifecycle automation, or workload-specific acceleration. Not all customers need these patterns.

---

## Customer-Ready PoC Plan Template

### Sample Baseline

As a reference for initial validation, the repository includes the following small-scale sample run results:

- **UC1 Legal Compliance**: 10 files, 404 ms total (discovery + sequential read)
- **UC16 Government Archives**: 10 documents, 389 ms total

> These are small-scale sample run results and are not production performance estimates. In customer PoCs, replace these sample baselines with measurements obtained using the customer's own dataset, file sizes, concurrency, and FSx throughput configuration.

```markdown
### Selected Use Case
- UC:
- Business context:
- Stakeholders:
  - Business sponsor: (Final authority for budget approval and Go/No-Go decisions)
  - Technical owner:
  - Measurement owner: (Responsible for measuring and reporting PoC success criteria)
  - Security reviewer:
  - Operations owner:
  - Partner/SI delivery lead:

### Architecture Option
- Trigger mode:
- Deployment profile:
- Output destination:
- FlexCache/FlexClone extension (if applicable):

### Success Metrics
- Outcome:
- Metrics:
- Measurement method:

### Governance Considerations
- Data classification:
- Human review:
- Audit evidence:
- Approval owner:

### Customer-Specific Baseline
- Sample data set:
- Number of files:
- Average file size:
- FSx throughput configuration:
- Concurrency:
- Measured processing time:
- Measured cost:
- Notes / constraints:

### Estimated Effort and Cost Assumptions
- PoC duration:
- Required roles:
- AWS cost assumptions:
- Partner/SI effort:

### Next-Phase Criteria
- Go criteria:
- No-Go criteria:
- Open risks:
- Business sponsor approval:
```

> Customize the above template according to the customer's business requirements and use as PoC agreement documentation.

---

## UC Success Metrics List

Links to each UC's Success Metrics (Outcome / Metrics / Measurement Method):

| UC | Industry | Success Metrics |
|----|----------|----------------|
| UC1 | Legal/Compliance | [legal-compliance/README.md](../legal-compliance/README.md#success-metrics) |
| UC2 | Financial/Insurance (IDP) | [financial-idp/README.md](../financial-idp/README.md#success-metrics) |
| UC3 | Manufacturing | [manufacturing-analytics/README.md](../manufacturing-analytics/README.md#success-metrics) |
| UC4 | Media (VFX) | [media-vfx/README.md](../media-vfx/README.md#success-metrics) |
| UC5 | Healthcare (DICOM) | [healthcare-dicom/README.md](../healthcare-dicom/README.md#success-metrics) |
| UC6 | Semiconductor / EDA | [semiconductor-eda/README.md](../semiconductor-eda/README.md#success-metrics) |
| UC7 | Genomics | [genomics-pipeline/README.md](../genomics-pipeline/README.md#success-metrics) |
| UC8 | Energy | [energy-seismic/README.md](../energy-seismic/README.md#success-metrics) |
| UC9 | Autonomous Driving / ADAS | [autonomous-driving/README.md](../autonomous-driving/README.md#success-metrics) |
| UC10 | Construction / BIM | [construction-bim/README.md](../construction-bim/README.md#success-metrics) |
| UC11 | Retail / EC | [retail-catalog/README.md](../retail-catalog/README.md#success-metrics) |
| UC12 | Logistics | [logistics-ocr/README.md](../logistics-ocr/README.md#success-metrics) |
| UC13 | Education / Research | [education-research/README.md](../education-research/README.md#success-metrics) |
| UC14 | Insurance | [insurance-claims/README.md](../insurance-claims/README.md#success-metrics) |
| UC15 | Defense / Space | [defense-satellite/README.md](../defense-satellite/README.md#success-metrics) |
| UC16 | Government (FOIA) | [government-archives/README.md](../government-archives/README.md#success-metrics) |
| UC17 | Smart City | [smart-city-geospatial/README.md](../smart-city-geospatial/README.md#success-metrics) |

## References

- [Trigger Mode Decision Guide](trigger-mode-decision-guide.md)
- [Deployment Profiles](deployment-profiles.md)
- [S3AP Dual-Layer Authorization Model](s3ap-authorization-model.md)
- [Enterprise Workload Examples](enterprise-workload-examples.md)
- [S3AP Performance Considerations](s3ap-performance-considerations.md)
- [FSx for ONTAP — SAP HANA Configuration Guide](https://docs.aws.amazon.com/sap/latest/sap-hana/sap-hana-amazon-fsx.html)
