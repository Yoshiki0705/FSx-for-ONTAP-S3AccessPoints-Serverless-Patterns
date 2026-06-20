# Enterprise Workload Examples

🌐 **Language / 言語**: [日本語](enterprise-workload-examples.md) | [English](enterprise-workload-examples.en.md)

## Overview

The patterns in this repository are not limited to AI/ML use cases. S3 Access Points provide connectivity to AWS native services for all enterprise file data stored on FSx for ONTAP.

> **Design Point**: File data remains on FSx for ONTAP. S3 Access Points serve as a bridge to "connect with AWS services without moving data." Existing NFS/SMB access is not changed at all.

## Enterprise Workload Examples

### 1. SAP Peripheral Files and Export Documents

| Item | Content |
|------|---------|
| **File Types** | SAP IDoc exports, ABAP report output, Crystal Reports PDF, BW data extracts |
| **Storage Location** | FSx for ONTAP (NFS/SMB mount from SAP application server) |
| **S3 AP Usage** | Automatic classification of export files, summary generation via Bedrock, query analysis with Athena |
| **Value** | Integrate SAP data with AI/analytics services without moving it. No changes to existing SAP file interfaces required |

**Architecture Pattern**:
```
SAP App Server → NFS → FSx for ONTAP Volume
                              ↓ (S3 Access Point)
                        Lambda (GetObject) → Bedrock (classification/summarization)
                                           → Athena (structured analysis)
                                           → S3 (analysis results storage)
```

### 2. EDI / HULFT Landing Zone

| Item | Content |
|------|---------|
| **File Types** | EDI (EDIFACT/X12) messages, HULFT transfer files, CSV/fixed-length data |
| **Storage Location** | FSx for ONTAP (receiving directory from HULFT/EDI gateway) |
| **S3 AP Usage** | Automatic validation of received files, format conversion, anomaly detection |
| **Value** | Build automated processing pipelines for received data without changing existing EDI/HULFT infrastructure |

**Architecture Pattern**:
```
HULFT/EDI Gateway → SMB → FSx for ONTAP Volume (/landing/)
                                ↓ (S3 Access Point + EventBridge Scheduler)
                          Step Functions
                            ├─→ Validation Lambda (format check)
                            ├─→ Transform Lambda (normalization)
                            └─→ Notification (alert on anomalies)
```

### 3. Audit Trails and Compliance Reports

| Item | Content |
|------|---------|
| **File Types** | Internal audit reports (PDF), compliance trails, approval flow records |
| **Storage Location** | FSx for ONTAP (department-level access control via NTFS ACL) |
| **S3 AP Usage** | Periodic integrity checks, metadata extraction, retention period management |
| **Value** | Achieve automated audit and compliance checks while maintaining NTFS permissions |

**Architecture Pattern**:
```
Audit System → SMB (NTFS ACL) → FSx for ONTAP Volume
                                       ↓ (S3 AP, Windows identity)
                                 Lambda (periodic scan)
                                   ├─→ Integrity hash verification
                                   ├─→ Retention period check
                                   └─→ SNS (expiration alert)
```

### 4. Batch Output from EC2/ECS-Based Business Applications

| Item | Content |
|------|---------|
| **File Types** | Batch job output (CSV/JSON/XML), report PDFs, log files |
| **Storage Location** | FSx for ONTAP (NFS mount from application server) |
| **S3 AP Usage** | Automatic post-processing of batch output, quality checks, delivery to downstream systems |
| **Value** | Add serverless post-processing pipelines without changing batch application output destinations |

#### Access Patterns by Compute Type

| Compute | Write to FSx for ONTAP | Post-processing via S3 AP | Notes |
|---------|------------------------|--------------------------|-------|
| **EC2** | ✅ Direct NFS/SMB mount | ✅ S3 AP (Lambda) | Simplest. Can share with containers via host volume |
| **ECS on EC2** | ✅ NFS mount via host volume | ✅ S3 AP (Lambda) | NFS mount on EC2 → reference host volume in task definition |
| **ECS Fargate** | ❌ Direct NFS mount not supported | ✅ **Read/write via S3 AP** | Fargate only supports native EFS mount. Access FSx for ONTAP via S3 AP |
| **Lambda** | ❌ NFS mount not supported | ✅ Via S3 AP | S3 AP is the only access path |

> **Fargate and FSx for ONTAP connectivity**: ECS Fargate tasks cannot directly NFS-mount FSx for ONTAP volumes ([AWS documentation](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/mount-ontap-ecs-containers.html) only covers ECS on EC2). When Fargate tasks need to process FSx for ONTAP data, **S3 Access Points** is the recommended path. This is exactly the pattern in this repository.

#### Architecture Pattern: EC2 Batch Output + S3 AP Post-processing

```
EC2/ECS on EC2 Batch App → NFS → FSx for ONTAP Volume (/batch-output/YYYYMMDD/)
                                        ↓ (S3 Access Point + EventBridge Scheduler)
                                  Step Functions (daily)
                                    ├─→ Discovery (detect today's output files)
                                    ├─→ Quality Check (count/format validation)
                                    ├─→ Transform (convert as needed)
                                    └─→ Delivery (deliver to downstream systems)
```

#### Architecture Pattern: Fargate App + S3 AP Bidirectional

```
ECS Fargate App ──→ S3 AP (PutObject) ──→ FSx for ONTAP Volume (/app-output/)
                                                ↓
                                          NFS/SMB users view results
                                                ↓ (EventBridge Scheduler)
                                          Step Functions (post-processing)
                                            ├─→ GetObject (via S3 AP)
                                            ├─→ AI/ML processing
                                            └─→ PutObject (write results back)
```

> In the **Fargate → S3 AP → FSx for ONTAP** pattern, Fargate tasks write files via S3 API (PutObject), and NFS/SMB users can directly view those files. No data copy occurs.

#### Reference Resources for Readers

| Resource | Content | Link |
|----------|---------|------|
| AWS Documentation: ECS + FSx for ONTAP | NFS/SMB mount procedure for EC2 launch type | [mount-ontap-ecs-containers](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/mount-ontap-ecs-containers.html) |
| This repository: UC1 (legal-compliance) | Basic pattern via S3 AP (Lambda + Step Functions) | [legal-compliance/](../legal-compliance/README.md) |
| This repository: event-driven-fpolicy | FPolicy Server implementation on Fargate | [event-driven-fpolicy/](../event-driven-fpolicy/README.md) |
| This repository: Fargate vs EC2 Decision | Compute selection guide for FPolicy Server | [fargate-vs-ec2-fpolicy-decision.md](fargate-vs-ec2-fpolicy-decision.md) |
| S3AP Benchmark Results | Measured PutObject/GetObject latency | [s3ap-benchmark-results.md](s3ap-benchmark-results.md) |
| AWS Blog: Bridge legacy and modern apps | Connect file-based and object-based apps with S3 AP | [AWS Storage Blog](https://aws.amazon.com/blogs/storage/bridge-legacy-and-modern-applications-with-amazon-s3-access-points-for-amazon-fsx/) |

### 5. Scanned Documents and Regulated Records

| Item | Content |
|------|---------|
| **File Types** | Scanned PDF/TIFF, contracts, medical records, legal documents |
| **Storage Location** | FSx for ONTAP (SMB share from scanner, long-term retention) |
| **S3 AP Usage** | OCR text extraction, automatic classification, PII detection, redaction |
| **Value** | Automate post-digitization processing of paper documents. Achieve AI-powered classification and search while keeping originals on FSx |

**Architecture Pattern**:
```
Scanner → SMB → FSx for ONTAP Volume (/scanned-docs/)
                       ↓ (S3 AP)
                 Step Functions
                   ├─→ Textract (OCR) ⚠️ Cross-Region
                   ├─→ Comprehend (classification + PII detection)
                   ├─→ Bedrock (summary generation)
                   └─→ Output (metadata + search index)
```

## Common Design Principles

### Data Does Not Move

```
┌─────────────────────────────────────────────────────────────┐
│  FSx for ONTAP Volume                                       │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Enterprise File Data                               │    │
│  │  (Accessible via NFS/SMB — no changes)              │    │
│  └─────────────────────────────────────────────────────┘    │
│           │                                                 │
│           │ S3 Access Points (read / write)                  │
│           ▼                                                 │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  AWS Native Services                                │    │
│  │  • AI/ML (Bedrock, Textract, Comprehend)            │    │
│  │  • Analytics (Athena, Glue)                         │    │
│  │  • Automation (Step Functions, Lambda)              │    │
│  │  • Storage (S3 for results)                         │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### Zero Impact on Existing Infrastructure

- NFS/SMB mount points require no changes
- NTFS ACL / UNIX permissions are maintained as-is
- No impact on existing backup/replication (SnapMirror)
- No application code changes required

### Incremental Adoption

1. **Phase 1**: Create S3 Access Point and retrieve file listings in read-only mode
2. **Phase 2**: Build automated processing pipelines for specific directories
3. **Phase 3**: Add real-time processing with event-driven (FPolicy)
4. **Phase 4**: Write processing results back to the same volume (PutObject)

## Mapping to Repository UC Patterns

| Enterprise Workload | Closest UC Pattern | Applicable Common Modules |
|--------------------|--------------------|-----------------------------|
| SAP peripheral files | UC1 (Legal), UC6 (EDA) | Discovery Lambda, Bedrock Helper |
| EDI / HULFT | UC12 (Logistics OCR), UC3 (Manufacturing) | S3AP Helper, Validation Lambda |
| Audit trails | UC1 (Legal), UC16 (Government) | Lineage, S3 Object Lock |
| Batch output | UC3 (Manufacturing), UC11 (Retail) | Discovery Lambda, Output Writer |
| Scanned documents | UC2 (Financial IDP), UC14 (Insurance) | Textract Helper, Comprehend Helper |

## References

- [S3AP Dual-Layer Authorization Model](s3ap-authorization-model.md)
- [Trigger Mode Decision Guide](trigger-mode-decision-guide.md)
- [Deployment Profiles](deployment-profiles.md)
- [Output Destination Patterns](output-destination-patterns.md)
