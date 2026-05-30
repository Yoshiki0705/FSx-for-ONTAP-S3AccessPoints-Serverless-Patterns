# Partner Workshop Guide — Customer PoC Workshop

🌐 **Language / 言語**: [日本語](workshop-guide.md) | [English](workshop-guide.en.md)

## Overview

A guide for 1-day workshops conducted by partners/SIs for customers.

---

## Workshop Structure (1 day / 6 hours)

| Time | Session | Content | Lead |
|------|---------|---------|------|
| 09:00-09:30 | Opening | Challenge hearing, goal setting | Partner |
| 09:30-10:30 | Session 1 | Architecture overview + S3AP authorization model | Partner |
| 10:30-10:45 | Break | — | — |
| 10:45-12:00 | Session 2 | Hands-on: UC template deployment | Participants |
| 12:00-13:00 | Lunch | — | — |
| 13:00-14:30 | Session 3 | Hands-on: FPolicy Event-Driven pipeline | Participants |
| 14:30-14:45 | Break | — | — |
| 14:45-15:45 | Session 4 | Security & governance review | Partner + Customer |
| 15:45-16:30 | Session 5 | Production planning + next steps | All |
| 16:30-17:00 | Closing | Q&A, action item organization | Partner |

### Recommended Participant Roles

| Role | Participating Sessions | Responsibility |
|------|----------------------|----------------|
| Storage / Infrastructure Owner | Session 1-3 | FSx environment and network verification |
| Application Owner | Session 1-2, 5 | Business requirements and target data verification |
| Security / Compliance Reviewer | Session 1, 4 | Authorization model and governance verification |
| Data / Analytics Owner | Session 2-3 | AI/ML processing requirements and output destination verification |
| Operations Team | Session 3, 5 | Operations design and incident response verification |
| Partner Delivery Lead | All sessions | Facilitation and next steps organization |
| Business Sponsor | Session 1, 5 | Business value, budget, and priority decisions |

---

## Session 1: Architecture Overview (60 min)

### Agenda
1. What are FSx for ONTAP S3 Access Points (10 min)
2. Dual-layer authorization model (15 min)
3. Trigger Mode: POLLING / EVENT_DRIVEN / HYBRID (15 min)
4. Use case selection (10 min)
5. Q&A (10 min)

### Materials
- [S3AP Authorization Model](s3ap-authorization-model.md)
- [Trigger Mode Decision Guide](trigger-mode-decision-guide.md)
- README architecture diagrams

---

## Session 2: Hands-on — UC Template Deployment (75 min)

### Prerequisites
- AWS account (individual or shared for participants)
- FSx for ONTAP file system (pre-provisioned)
- S3 Access Point (pre-created)
- Test files (pre-placed via NFS/SMB)

### Procedure
1. Deploy CloudFormation template (15 min)
2. Verify EventBridge Scheduler (5 min)
3. Manual execution for operation verification (15 min)
4. Review CloudWatch logs and metrics (15 min)
5. Review results and discussion (25 min)

### Recommended UCs (First Workshop)
- **UC1 (legal-compliance)**: Simplest, Bedrock + Athena
- **UC11 (retail-catalog)**: Rekognition + Bedrock, visually intuitive

---

## Session 3: Hands-on — FPolicy Event-Driven (90 min)

### Procedure
1. Deploy FPolicy Server (Fargate or EC2) (20 min)
2. ONTAP FPolicy configuration (external-engine, policy, scope) (20 min)
3. NFS file creation → SQS → EventBridge arrival confirmation (20 min)
4. IP Updater Lambda operation verification (for Fargate) (10 min)
5. Failure simulation (task stop → restart) (20 min)

### Notes
- NFSv4.2 is not supported by FPolicy. Explicitly specify `vers=4.1`
- Events are lost during Fargate task restart (30-60 seconds)
- Persistent Store requires separate configuration (explanation only in workshop)

---

## Session 4: Security & Governance Review (60 min)

### Agenda
1. Review [Governance Checklist](governance-checklist.md) (20 min)
2. Data classification discussion (15 min)
3. Human-in-the-loop requirement determination (10 min)
4. Compliance requirement confirmation (15 min)

### Recommended Customer Participants
- Information security officer
- Compliance officer
- Data management owner

---

## Session 5: Production Planning (45 min)

### Agenda
1. Confirm [Production Readiness](production-readiness.md) Level (10 min)
2. Select [Deployment Profile](deployment-profiles.md) (10 min)
3. Define success criteria (10 min)
4. Agree on timeline and next steps (15 min)

### Deliverable Template

```markdown
## Workshop Outcomes

### Selected UC: ___
### Trigger Mode: POLLING / EVENT_DRIVEN / HYBRID
### Deployment Profile: PoC / Production / Compliance
### Success Criteria:
- Detection latency: ___
- Processing throughput: ___
- Cost limit: ___
- Availability target: ___

### Next Steps:
1. ___ (Owner: ___, Deadline: ___)
2. ___ (Owner: ___, Deadline: ___)
3. ___ (Owner: ___, Deadline: ___)
```

---

## Preparation Checklist (For Partners)

### Pre-workshop Requests to Customer Participants

One week before the workshop, request that customer participants prepare the following information:

| # | Preparation Item | Responsible Role | Purpose |
|---|-----------------|------------------|---------|
| 1 | Existing file server / NAS architecture diagram | Storage / Infra Owner | Current state understanding in Session 1-2 |
| 2 | Sample of target dataset (10-50 files) | Application Owner | Deployment testing in Session 2 |
| 3 | Data classification policy (presence of PII/confidential data) | Security / Compliance | Governance verification in Session 4 |
| 4 | Existing batch / HULFT / EDI flow diagrams | Application Owner | Use case selection in Session 1 |
| 5 | Network constraints (VPC configuration, Internet connectivity) | Storage / Infra Owner | Environment design in Session 2-3 |
| 6 | IAM / AD / authorization model assumptions | Security / Compliance | Authorization design in Session 4 |
| 7 | PoC success conditions (latency, cost, processing volume) | Business Sponsor | Agreement in Session 5 |
| 8 | Expected cost limit (monthly) | Business Sponsor | Cost design in Session 5 |

### 1 Week Before
- [ ] Confirm customer's AWS account
- [ ] Prepare FSx for ONTAP file system
- [ ] Create S3 Access Point
- [ ] Place test files
- [ ] Verify network reachability (VPC, Security Group)
- [ ] Conduct hearing using [Customer Discovery Template](customer-discovery-template.md)

### Day Before
- [ ] Pre-deployment test of CloudFormation template
- [ ] Verify FPolicy Server operation
- [ ] Send pre-workshop materials to participants
- [ ] Confirm meeting room / remote environment

---

## References

- [Choose Your Path](../README.md#choose-your-path)
- [Partner/SI Delivery Checklist](partner-si-delivery-checklist.md)
- [Customer Discovery Template](customer-discovery-template.md)
- [Production Readiness](production-readiness.md)
- [Governance Checklist](governance-checklist.md)
