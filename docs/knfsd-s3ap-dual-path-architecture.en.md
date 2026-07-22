# KNFSD File Cache + S3 AP Dual-Path Architecture

🌐 **Language / 言語**: [日本語](knfsd-s3ap-dual-path-architecture.md) | [English](knfsd-s3ap-dual-path-architecture.en.md)

> **Status**: KNFSD File Cache is in **Preview** as of July 2026.

> **Note**: Full English translation is in progress. For now, please refer to the Japanese version which contains the complete content including 7 industry deep dives (EDA, VFX, CAE, Genomics, Finance, Weather, Energy), throughput sizing calculations, observability integration, cost optimization analysis, and deployment considerations.

## Executive Summary

This document describes a Dual-Path architecture that optimizes both large-scale compute read workloads (via KNFSD File Cache NFS) and serverless AI/ML processing (via S3 Access Points) against the same FSx for ONTAP data source.

**Key finding**: KNFSD File Cache (NFS read acceleration) and S3 Access Points (serverless processing) are complementary — combining them enables both "high-speed NFS reads for compute" and "serverless AI/ML analysis" on the same FSx for ONTAP volume efficiently.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  FSx for ONTAP Volume (source data)                              │
│                                                                 │
│  ┌────────────────┐                       ┌──────────────────┐  │
│  │ KNFSD File     │  NFS re-export        │ Compute Fleet    │  │
│  │ Cache (EC2     │◄─────────────────────►│ (EDA/VFX/HPC)   │  │
│  │ Auto Scaling)  │  local VPC speed      │ Spot-compatible  │  │
│  └───────┬────────┘                       └──────────────────┘  │
│          │ NFS mount (source)                                    │
│          ▼                                                       │
│  ┌────────────────┐                       ┌──────────────────┐  │
│  │ FSx for ONTAP  │  S3 AP               │ Lambda / Step    │  │
│  │ File System    │◄─────────────────────►│ Functions        │  │
│  │                │  serverless access     │ (AI/ML)          │  │
│  └────────────────┘                       └──────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Target Industries

| Industry | KNFSD Role | S3 AP Role |
|----------|-----------|-----------|
| Semiconductor EDA | DRC/LVS design rule high-speed reads | Yield analysis AI |
| VFX / Animation | Texture/asset Fanout cache | Render quality AI validation |
| Automotive CAE | Shared mesh data dedup reads | Variant comparison AI |
| Life Sciences | Reference genome/dbSNP cache (hit ~100%) | Variant pathogenicity AI classification |
| Financial Risk | Market data sub-ms delivery | VaR/regulatory report AI generation |
| Weather Forecasting | GFS initial/terrain permanent cache | Extreme weather AI detection + renewables prediction |
| Energy / Seismic | Velocity model (TB) GPU cluster delivery | AI stratigraphic interpretation |

## Related Documentation

- [Demo Guide (JP)](../infrastructure/knfsd-file-cache/docs/demo-guide.md) | [(EN)](../infrastructure/knfsd-file-cache/docs/demo-guide.en.md)
- [Comparison Alternatives](comparison-alternatives.md)
- [S3 AP Performance — Bandwidth Sharing](s3ap-performance-considerations.md)
- [KNFSD File Cache GitHub](https://github.com/awslabs/knfsd-file-cache)
