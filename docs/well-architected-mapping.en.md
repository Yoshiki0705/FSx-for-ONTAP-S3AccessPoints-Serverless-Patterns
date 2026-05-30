# AWS Well-Architected Framework Mapping

🌐 **Language / 言語**: [日本語](well-architected-mapping.md) | [English](well-architected-mapping.en.md)

## Overview

This document maps the architecture design decisions of this repository to the 6 pillars of the AWS Well-Architected Framework.

---

## 1. Operational Excellence

| Design Decision | Implementation | Related Documentation |
|----------------|---------------|----------------------|
| Infrastructure as Code | CloudFormation (SAM Transform) for all UC templates | Each UC `template.yaml` |
| Observability | X-Ray tracing + CloudWatch EMF metrics + Dashboard | Phase 3+ |
| Alarm Automation | BATCH / REALTIME / HIGH_VOLUME profiles | Phase 10 |
| Runbook | Response procedures for SLO violations | `docs/runbooks/` |
| Staged Deployment | 4-level Maturity Model | [Production Readiness](production-readiness.md) |
| CI/CD | cfn-lint + pytest + ruff + 6 validators | `scripts/` |
| Cost Visibility | Business Hours Scheduling + EstimatedMonthlySavings metric | Phase 10 |

## 2. Security

| Design Decision | Implementation | Related Documentation |
|----------------|---------------|----------------------|
| Least Privilege IAM | S3 AP ARN format + action restrictions | [S3AP Authorization Model](s3ap-authorization-model.md) |
| Dual-Layer Authorization | IAM + ONTAP file system identity | [S3AP Authorization Model](s3ap-authorization-model.md) |
| Encryption (at rest) | SSE-FSX (KMS managed) + SSE-KMS (S3 Output) | Each template |
| Encryption (in transit) | TLS enabled by default | `shared/ontap_client.py` |
| Secrets Management | Secrets Manager + rotation | Phase 12 |
| VPC Isolation | Lambda in VPC + VPC Endpoint | Phase 9 |
| Block Public Access | Always enabled on S3 AP (cannot be changed) | AWS specification |
| SCP / Organization | OrgID condition on StackSets execution role | Phase 10 |
| PII Detection | Comprehend PII detection + redaction | UC2, UC14, UC16 |
| Audit Logging | CloudTrail + S3 Access Logs + DynamoDB Lineage | [Governance Checklist](governance-checklist.md) |

## 3. Reliability

| Design Decision | Implementation | Related Documentation |
|----------------|---------------|----------------------|
| Event Durability | Persistent Store (ONTAP 9.14.1+) | [Deployment Profiles](deployment-profiles.md) |
| Idempotency | DynamoDB conditional write | Phase 11+ |
| DLQ | SQS Dead Letter Queue | Each template |
| Retry | Step Functions Retry + Lambda retry | Each template |
| Auto Recovery | ECS Service auto-recovery / ASG | [Fargate vs EC2](fargate-vs-ec2-fpolicy-decision.md) |
| Multi-AZ | FSx for ONTAP Multi-AZ support | AWS specification |
| DR | SnapMirror Cross-Region | Phase 5 |
| Replay Storm Protection | Flow control + backpressure | Phase 12 |

## 4. Performance Efficiency

| Design Decision | Implementation | Related Documentation |
|----------------|---------------|----------------------|
| FSx Throughput Dependency Awareness | Map parallelism designed to match FSx provisioned throughput | [S3AP Performance](s3ap-performance-considerations.md) |
| Dynamic MaxConcurrency | Automatic parallelism calculation based on file count | Phase 10 |
| Lambda Memory Optimization | Recommended memory size per UC | [S3AP Performance](s3ap-performance-considerations.md) |
| ARM64 | Graviton (Lambda + Fargate + EC2) | All templates |
| Prefix Filtering | Leveraging ListObjectsV2 Prefix | Discovery Lambda |
| Streaming Processing | Chunk processing for large files | `shared/s3ap_helper.py` |

## 5. Cost Optimization

| Design Decision | Implementation | Related Documentation |
|----------------|---------------|----------------------|
| Serverless | Lambda + Step Functions (pay-per-execution) | All UCs |
| Business Hours Scheduling | Reduce polling frequency during off-hours | Phase 10 |
| VPC Endpoint Optionality | Interface EP controlled via Conditions | Phase 9 |
| Graviton | ~20% cost reduction with ARM64 | All templates |
| Opt-in via Conditions | SageMaker, Kinesis, etc. incur no charges unless enabled | Phase 3 |
| Cost Visibility | EstimatedMonthlySavings metric | Phase 10 |
| EC2 vs Fargate Selection | Cost difference $5-7 vs $42-70/month | [Fargate vs EC2](fargate-vs-ec2-fpolicy-decision.md) |

## 6. Sustainability

| Design Decision | Implementation | Related Documentation |
|----------------|---------------|----------------------|
| Minimize Data Movement | Process data in place on FSx via S3 AP | Overall architecture |
| Graviton (ARM64) | Energy-efficient processor | All templates |
| On-Demand Execution | Minimize always-on resources | POLLING mode |
| Differential Processing | Process only changed files (avoid full scans) | Discovery Lambda |

---

## Trade-offs

| Design Decision | Benefit | Trade-off |
|----------------|---------|-----------|
| VPC Endpoint Enabled | Improved security (private communication) | Increased cost (Interface EP ~$30-50/month) |
| POLLING Mode | Predictable, idempotent, no event loss | No real-time capability (depends on schedule interval) |
| EVENT_DRIVEN Mode | Sub-second detection | Increased operational complexity (FPolicy + Fargate/EC2) |
| FSxN S3AP Output (OutputDestination=FSXN_S3AP) | One-copy experience, NFS/SMB users can view results | S3 native features (Lifecycle, Versioning) not supported |
| EC2 FPolicy Server | Static IP, low cost | OS patch management, increased operational responsibility |
| Fargate FPolicy Server | No OS management required | IP variability, VPC EP cost, startup latency |
| ARM64 (Graviton) | ~20% cost reduction, energy efficiency | Compatibility verification needed for some native-dependent libraries |
| Business Hours Scheduling | Cost reduction (lower execution frequency during off-peak) | Increased detection latency during off-peak hours |
| Persistent Store | Zero event loss (replay on reconnection) | Requires ONTAP 9.14.1+, volume capacity management needed |

## Reference Links

- [AWS Well-Architected Framework](https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html)
- [Production Readiness](production-readiness.md)
- [Governance Checklist](governance-checklist.md)
- [S3AP Performance Considerations](s3ap-performance-considerations.md)
