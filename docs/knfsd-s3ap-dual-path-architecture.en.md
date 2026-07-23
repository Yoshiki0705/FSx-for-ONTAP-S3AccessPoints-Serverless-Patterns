# KNFSD File Cache + S3 AP Dual-Path Architecture

🌐 **Language / 言語**: [日本語](knfsd-s3ap-dual-path-architecture.md) | [English](knfsd-s3ap-dual-path-architecture.en.md)

> **Status**: KNFSD File Cache is in **Preview** as of July 2026.

## Executive Summary

This document describes a Dual-Path architecture that optimizes both large-scale compute read workloads (via KNFSD File Cache NFS) and serverless AI/ML processing (via S3 Access Points) against the same FSx for ONTAP data source.

**Key finding**: KNFSD File Cache (NFS read acceleration) and S3 Access Points (serverless processing) are complementary — combining them enables both "high-speed NFS reads for compute" and "serverless AI/ML analysis" on the same FSx for ONTAP volume efficiently.

> For the full content including 7 industry deep dives (EDA, VFX, CAE, Genomics, Finance, Weather, Energy), throughput sizing calculations, and cost optimization analysis, refer to the [Japanese version](knfsd-s3ap-dual-path-architecture.md).

---

## Verified Performance Data (Measured 2026-07-23)

> Environment: KNFSD proxy m6gd.xlarge (arm64, 16GB RAM, 237GB NVMe) / FSx for ONTAP 128 MBps Single-AZ / Client t4g.micro (916MB RAM) / NFSv4.1

### Dual-Path E2E Results

| Test | Result | Notes |
|------|:------:|-------|
| S3 AP write → KNFSD NFS read | **✅** | Immediate reflection, content match |
| NFS write → S3 AP read (MD5) | **✅** | Binary integrity verified |
| S3 AP batch 50 files → NFS bulk read | **✅** | 50 files in 107ms (2.1ms/file) |
| S3 AP multipart 50MB → NFS read | **✅** | MD5 match confirmed |

### Throughput

| Operation | Throughput | Condition |
|-----------|-----------|-----------|
| Sequential read (proxy cache hit) | **422-619 MB/s** | 500MB, client cache dropped |
| Sequential read (client page cache) | **5.0-9.1 GB/s** | 100MB, 2nd read |
| Large write (write-through) | **157-218 MB/s** | 100MB-1GB |
| S3 AP multipart upload | 36.6 MiB/s | 50MB file |

### Latency

| Operation | Latency |
|-----------|---------|
| Small file read (cached) | **1.5 ms/file** |
| S3 AP batch read via KNFSD | **2.1 ms/file** |
| Cache miss → hit (10MB) | 55ms → **2 ms** (28x) |

### Critical: NFSv4.1 Required for FSx for ONTAP

NFSv3 re-export fails on file creation due to filehandle size overflow (+22 bytes exceeds 64-byte NFSv3 limit). **Always use NFSv4.1** (128-byte limit provides sufficient headroom).

---

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
