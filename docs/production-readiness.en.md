# Production Readiness — Maturity Model

🌐 **Language / 言語**: [日本語](production-readiness.md) | [English](production-readiness.en.md)

## Overview

This document defines a staged maturity model from PoC to production. It clarifies the required deliverables, design items, and operational items at each level, enabling you to determine "where you are now and what to do next."

> **Note**: This document supports architecture and operations review. It does not substitute for legal judgment, compliance assessment, privacy evaluation, or regulatory response. Final regulatory determinations must be made by the responsible organization's legal and compliance departments.

### Field-Ready Baseline

Phase 13 is not a final destination but a practical baseline for:
- **Informed evaluation** — Information needed for evaluation is available
- **Governed experimentation** — Controlled experimentation is possible
- **Structured delivery** — A structured delivery path exists
- **Production-readiness planning** — Materials for production planning are available

See [Exit Criteria](#exit-criterialevel-completion-conditions) for completion conditions at each level.

---

## Maturity Model

```
Level 1          Level 2          Level 3          Level 4
Sandbox    →    Scheduled    →    Monitored    →    Production
(Manual)        (Periodic)       (Observability)    (Production ops)
```

---

## Level 1: Sandbox (Manual Execution)

### Purpose
- Verify pattern operation
- Validate file access via S3 AP
- Confirm AI/ML service output quality

### Required Deliverables
- [ ] Successful CloudFormation template deployment
- [ ] Confirmed ListObjectsV2 / GetObject operation via S3 AP
- [ ] Confirmed AI/ML processing results with sample files
- [ ] Successful manual Step Functions execution

### Design Items
| Item | Level 1 State |
|------|---------------|
| Trigger | Manual execution (console or CLI) |
| Data | Sample data (under test-data/) |
| Error handling | Lambda default retry only |
| Monitoring | Visual inspection of CloudWatch Logs |
| Security | Default IAM (included in template) |
| Cost | Charged only during execution |

### Time Required: 1-2 hours

---

## Level 2: Scheduled (Periodic Execution)

### Purpose
- Automated execution via EventBridge Scheduler
- Continuous processing with real data
- Basic error detection

### Required Deliverables
- [ ] EventBridge Scheduler configuration (rate or cron)
- [ ] Confirmed processing success with real data (minimum 1 week)
- [ ] DLQ (Dead Letter Queue) configuration
- [ ] Basic alarm (SNS notification on Step Functions failure)

### Design Items
| Item | Level 2 State |
|------|---------------|
| Trigger | EventBridge Scheduler (rate(1h) etc.) |
| Data | Real data (FSx for ONTAP Volume) |
| Error handling | DLQ + SNS notification |
| Monitoring | CloudWatch Alarm (error rate) |
| Security | Least-privilege IAM + S3 AP Policy |
| Cost | ~$6-21/month (POLLING mode) |

### Time Required: 1-2 days

---

## Level 3: Monitored (With Observability)

### Purpose
- Establish comprehensive observability
- Visualize performance and cost
- Early detection and response to failures

### Required Deliverables
- [ ] CloudWatch Dashboard (processing count, latency, error rate)
- [ ] X-Ray tracing enabled
- [ ] EMF metrics output (FilesProcessed, Duration, Errors)
- [ ] Alarm Profile configuration (BATCH / REALTIME / HIGH_VOLUME)
- [ ] Cost visualization (Cost Scheduling metrics)
- [ ] Operations Runbook (incident response procedures)

### Design Items
| Item | Level 3 State |
|------|---------------|
| Trigger | Scheduler + Business Hours optimization |
| Data | Real data + change detection (LastModified comparison) |
| Error handling | DLQ + Retry + SNS + Runbook |
| Monitoring | Dashboard + Alarm + X-Ray + EMF |
| Security | IAM + AP Policy + VPC Endpoint Policy |
| Cost | ~$20-60/month + visualization |

### Time Required: 3-5 days

---

## Level 4: Production (Production Operations)

### Purpose
- Multi-account support
- CI/CD pipeline
- DR / disaster recovery
- Compliance and audit support
- SLO definition and operations

### Required Deliverables
- [ ] Multi-account deployment via StackSets
- [ ] CI/CD pipeline (cfn-lint + pytest + automated deployment)
- [ ] Data lineage (DynamoDB + S3 Object Lock)
- [ ] SLO definition and violation Runbook
- [ ] DR design (SnapMirror + Cross-Region)
- [ ] Security review completed
- [ ] Operations handover documentation
- [ ] Periodic AI output quality review process

### Design Items
| Item | Level 4 State |
|------|---------------|
| Trigger | POLLING + EVENT_DRIVEN (HYBRID) |
| Data | Real data + idempotency guarantee + lineage |
| Error handling | Full retry + DLQ + Runbook + auto-recovery |
| Monitoring | SLO + Dashboard + Alarm + X-Ray + Lineage |
| Security | Full dual-layer + SCP + VPC EP + audit logs |
| Cost | ~$50-200/month + cost anomaly detection |
| DR | SnapMirror + Cross-Region backup |
| CI/CD | StackSets + GitHub Actions + cfn-lint |

### Time Required: 2-4 weeks

---

## Maturity Level vs Success Metrics Mapping

| Level | Corresponding Success Metrics | Measurement Focus |
|-------|------------------------------|-------------------|
| Level 1 (Sandbox) | Deployment success, manual execution success | Operation verification |
| Level 2 (Scheduled) | Files processed/execution, processing time, error rate | Stability verification |
| Level 3 (Monitored) | Latency P90/P99, cost/execution, alert response time | Performance/cost visualization |
| Level 4 (Production) | SLO achievement rate, Human Review rate, audit trail completeness, cost target achievement | Operational quality |

> Measure and evaluate each UC's Success Metrics (Outcome / Metric / Measurement Method) progressively according to the above Levels. Level 1 requires only operation verification; Level 4 requires continuous monitoring of all indicators.

---

## Exit Criteria (Level Completion Conditions)

### Level 1 → Level 2 Transition Conditions
- [ ] CloudFormation deployment succeeded and manual execution produced expected results
- [ ] ListObjectsV2 / GetObject via S3 AP operated normally
- [ ] AI/ML processing result quality confirmed to meet business requirements

### Level 2 → Level 3 Transition Conditions
- [ ] Periodic execution via EventBridge Scheduler has been stable for 1+ weeks
- [ ] SNS notifications on errors confirmed to arrive correctly
- [ ] Processing time for target dataset has been measured and recorded
- [ ] Confirmed no messages accumulating in DLQ

### Level 3 → Level 4 Transition Conditions
- [ ] Metrics are visualized in CloudWatch Dashboard
- [ ] Alarm Profile is configured and notifications arrive on threshold breach
- [ ] Execution paths are verifiable via X-Ray tracing
- [ ] Operations Runbook has been created and incident response drills conducted
- [ ] Cost visualization is active and monthly reviews are conducted
- [ ] Security review has been completed

### Operational Notes (Level 3 and above)

#### S3 AP Impact During FSx Throughput Capacity Changes

When changing FSx for ONTAP throughput capacity, **S3 Access Points may become temporarily unavailable** (observed in Phase 14).

| Item | Details |
|------|---------|
| Impact Scope | All S3 APs across all SVMs on the same file system |
| Error | `ServiceUnavailable` or `ConnectionClosedError` |
| Recovery Time | Unknown (under confirmation with AWS Support) |
| NFS/SMB Impact | AWS documentation states typically no impact. Only S3 AP may have been affected (unverified) |

**Recommendations**:
- Perform throughput capacity changes during a maintenance window
- Execute at a time when S3 AP workload stoppage is acceptable
- Confirm S3 AP normal operation after the change before resuming workloads
- Configure CloudWatch Alarm for S3 AP health checks to detect recovery

## Level Checklist Matrix

### CI/CD Badge Correspondence

| Level | Corresponding Badge / Verification State |
|-------|----------------------------------------|
| Level 1 (Sandbox) | `sam build` success, `sam deploy` success |
| Level 2 (Scheduled) | ![tests](https://img.shields.io/badge/tests-passed-brightgreen) All pytest tests PASS |
| Level 3 (Monitored) | ![cfn-lint](https://img.shields.io/badge/cfn--lint-0%20errors-brightgreen) cfn-lint + ruff 0 errors |
| Level 4 (Production) | ![region](https://img.shields.io/badge/verified-ap--northeast--1-blue) AWS live environment verified + security check PASS |

| Item | L1 | L2 | L3 | L4 |
|------|:--:|:--:|:--:|:--:|
| CloudFormation Deploy | ✅ | ✅ | ✅ | ✅ |
| EventBridge Scheduler | — | ✅ | ✅ | ✅ |
| DLQ | — | ✅ | ✅ | ✅ |
| SNS Notification | — | ✅ | ✅ | ✅ |
| CloudWatch Dashboard | — | — | ✅ | ✅ |
| X-Ray | — | — | ✅ | ✅ |
| Alarm Profile | — | — | ✅ | ✅ |
| Business Hours Scheduling | — | — | ✅ | ✅ |
| Runbook | — | — | ✅ | ✅ |
| StackSets | — | — | — | ✅ |
| CI/CD | — | — | — | ✅ |
| Data Lineage | — | — | — | ✅ |
| SLO | — | — | — | ✅ |
| DR | — | — | — | ✅ |
| Governance Checklist | — | — | — | ✅ |
| Human-in-the-loop | — | — | — | ✅ (regulated) |

---

## References

- [Deployment Profiles](deployment-profiles.md) — FPolicy-specific PoC/Prod/Compliance classification
- [Governance Checklist](governance-checklist.md) — For regulated/public sector
- [Partner/SI Delivery Checklist](partner-si-delivery-checklist.md) — Proposal/build checklist
- [Trigger Mode Decision Guide](trigger-mode-decision-guide.md) — Mode selection
