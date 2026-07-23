# KNFSD File Cache — FSx for ONTAP NFS Read Acceleration

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md)

> **Status**: KNFSD File Cache is in **Preview** as of July 2026.
> **Verified**: Cache miss 55ms → hit 2ms (**32x speedup**) — 2026-07-22, ap-northeast-1

## Overview

Deployment environment for transparently caching FSx for ONTAP NFS exports via KNFSD File Cache, serving large compute fleets at local VPC speed.

## Architecture

```
┌─── Existing Environment (this project) ──────────────────┐
│                                                          │
│  FSx for ONTAP ◄── S3 AP ──► Lambda (serverless)        │
│       ▲                                                  │
│       │ NFS mount (source)                               │
│       ▼                                                  │
│  KNFSD File Cache (EC2, deployed by this directory)      │
│       ▲                                                  │
│       │ NFS re-export (cached, 32x speedup)              │
│       ▼                                                  │
│  Compute Fleet / Test Client                             │
└──────────────────────────────────────────────────────────┘
```

## Quick Start (3 commands)

```bash
# 1. Build AMI + Deploy (~40 min total)
git clone https://github.com/awslabs/knfsd-file-cache.git /tmp/knfsd-file-cache
cp terraform/terraform.tfvars.example terraform/terraform.tfvars
# ↑ Edit: VPC ID, Subnet, FSx NFS IP

# 2. Deploy
./scripts/deploy.sh

# 3. Validate
./scripts/validate.sh
```

Full walkthrough: [Demo Guide](docs/demo-guide.en.md)

## FSID Backend Selection

NFS re-export requires consistent file handle (FSID) management. Choose based on your needs:

| Option | Method | Cost | Use Case | tfvars Setting |
|:---:|------|:---:|------|------|
| **D** (recommended) | SQLite on FSx for ONTAP | **$0** | Test/PoC/Single-node | `fsid_mode = "local"` |
| **A** | RDS PostgreSQL | ~$15/mo | Multi-node production | `fsid_mode = "external"` + `fsid_db_engine = "rds"` |
| **B** | Aurora Serverless v2 | ~$5-15/mo | Cost-optimized production | `fsid_mode = "external"` + `fsid_db_engine = "aurora-serverless"` |

> **Option D recommended**: SQLite on FSx for ONTAP's NFS mount. $0 additional cost, 99.99% SLA persistence via FSx for ONTAP.

Details: [FSID Backend Selection Guide](docs/fsid-backend-options.en.md)

## Cost

| Phase | Resource | Cost |
|-------|----------|------|
| AMI Build | Spot c6g.16xlarge × 25min | ~$0.30 |
| Test (1hr) | m6gd.xlarge | ~$0.29 |
| **Test Total** | | **< $1 (KNFSD incremental only. FSx for ONTAP environment required separately)** |
| Production (monthly) | im4gn.16xlarge × 24/7 | ~$4,190 |
| FSID DB (Option A) | RDS db.t4g.micro | ~$15/mo |
| FSID DB (Option B) | Aurora Serverless v2 | ~$5-15/mo |
| FSID DB (Option D) | SQLite on FSx for ONTAP | **$0** |

## Security

| Item | Risk | Mitigation |
|------|------|-----------|
| NFS v3 unencrypted | Plaintext in VPC | VPC-only deployment. SG restricts to VPC CIDR |
| NVMe cache | Plaintext on disk | Hardware wipe on instance termination |
| Public IP | NFS NOT exposed to internet | SG allows VPC CIDR only. Public IP for EC2 API outbound |
| FSID DB credentials | In Terraform state | `sensitive = true` + remote state recommended |

## HA / Availability

| Item | Test | Production |
|------|:---:|:---:|
| Proxy count | 1 | 2+ (ASG) |
| FSID Backend | D (SQLite) | A or B (RDS/Aurora) |
| Load balancing | None | NLB or DNS round-robin |
| AZ placement | Single AZ | Same AZ as FSx for ONTAP |
| Proxy instance | On-Demand | On-Demand (Compute clients: Spot) |

## Related Documentation

- [Demo Guide (JA)](docs/demo-guide.md) | [(EN)](docs/demo-guide.en.md)
- [Troubleshooting (JA)](docs/troubleshooting.md) | [(EN)](docs/troubleshooting.en.md)
- [FSID Backend Guide (JA)](docs/fsid-backend-options.md) | [(EN)](docs/fsid-backend-options.en.md)
- [KNFSD + S3 AP Dual-Path Architecture](../../docs/knfsd-s3ap-dual-path-architecture.md)
- [Comparison Alternatives](../../docs/comparison-alternatives.md)
- [KNFSD File Cache Official GitHub](https://github.com/awslabs/knfsd-file-cache)
- [AWS Solutions Guidance](https://docs.aws.amazon.com/solutions/knfsd-file-cache-on-aws/)
