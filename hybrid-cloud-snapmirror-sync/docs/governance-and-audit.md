# Governance, Audit, and Data Classification

[日本語](governance-and-audit-ja.md) | [English](governance-and-audit.md)

## Data Classification

| Layer | Data Location | Classification | Owner |
|-------|--------------|----------------|-------|
| Source of Record | On-premises ONTAP | Defined by customer | Customer data owner |
| Replicated Operational Copy | FSx for ONTAP (AWS) | Copy — not source of truth | Infrastructure team |
| Analytical / Visualization | Amazon Quick dataset/dashboard | Derived — read-only consumption | Business analytics team |

## Responsibility Matrix

| Responsibility | Owner | Evidence |
|---------------|-------|----------|
| Source data integrity | Customer (on-prem) | ONTAP audit logs, file permissions |
| SnapMirror replication health | Infrastructure team | SnapMirror relationship status, transfer logs |
| FSx for ONTAP management | Cloud infrastructure team | AWS CloudTrail, FSx audit logs |
| S3 Access Point policy | Security team | IAM policy, S3 AP resource policy |
| Amazon Quick access control | Analytics team | Quick user/group management |
| Data classification labeling | Data governance team | Metadata tags, naming conventions |

## Access Control Layers

```
[User] → [Amazon Quick IAM/SSO] → [S3 Access Point Policy] → [FSx File System Identity] → [ONTAP Volume]
```

Each layer independently enforces authorization:
1. **Amazon Quick**: User authentication via IAM Identity Center or Cognito
2. **S3 Access Point**: Resource-based policy restricts which principals can access
3. **FSx file system identity**: Maps S3 API calls to UNIX/NTFS file permissions
4. **ONTAP volume**: Export policies and share-level ACLs

## Audit Trail

| Event | Log Source | Retention |
|-------|-----------|-----------|
| SnapMirror transfer start/complete/fail | ONTAP audit log, FSx CloudWatch | Configurable |
| S3 AP GetObject / ListObjects | AWS CloudTrail (data events) | 90 days default |
| Quick dashboard access | Amazon Quick audit log | Per Quick plan |
| IAM authentication | AWS CloudTrail | 90 days default |
| One-click sync trigger | Sync Server audit.jsonl | Application-managed |

## Assessment Checklist (Pre-deployment)

- [ ] Data sensitivity classification completed
- [ ] Network path reviewed (VPN / Direct Connect / VPC peering)
- [ ] Replication interval aligned with RPO requirements
- [ ] IAM / S3 AP policy reviewed by security team
- [ ] ONTAP file identity mapping validated
- [ ] Quick user access scoped to appropriate data
- [ ] Audit evidence collection confirmed
- [ ] Operational owner designated
- [ ] Rollback / DR plan documented
- [ ] Change management process defined

## Regulatory Considerations

> **Governance Caveat**: This document provides technical governance guidance and architectural patterns. It does not constitute legal, compliance, or regulatory advice. Organizations must consult qualified professionals for binding compliance determinations.

For regulated industries (healthcare, finance, public sector):
- Confirm data residency requirements (replication stays within required region)
- Validate encryption requirements (KMS at rest, TLS in transit)
- Ensure audit retention meets regulatory minimums
- Confirm that replicated data classification does not exceed the destination environment's security posture


## AI / BI Usage Boundary

This pattern can support AI and BI exploration over replicated data.
However, replicated data must not be used for high-impact automated decisions unless:

- Data classification is reviewed and approved for the use case
- Freshness SLO is currently met (see `slo-design.md`)
- Source-of-record timestamp is visible in the AI/BI output
- Human review workflow is defined for high-impact actions
- Audit trail is enabled for all AI-generated recommendations

> This pattern does not assume that replicated data is automatically AI-ready.
> It provides freshness, governance, and observability signals that help determine
> whether the data is ready for BI, AI, or operational analysis.
