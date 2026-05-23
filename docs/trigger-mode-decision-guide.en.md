# Trigger Mode Decision Guide — POLLING / EVENT_DRIVEN / HYBRID

🌐 **Language / 言語**: [日本語](trigger-mode-decision-guide.md) | [English](trigger-mode-decision-guide.en.md)

## Overview

This repository provides 3 trigger modes. Select the optimal mode based on your workload requirements.

## Decision Table

| Mode | Choose when | Avoid when |
|------|-------------|------------|
| **POLLING** | Hourly/batch processing is sufficient | Sub-minute detection is required |
| **EVENT_DRIVEN** | Near-real-time ingestion is needed and event loss during reconnection is acceptable | Compliance requires durable event capture |
| **HYBRID** | Faster detection + periodic consistency checks are needed | Simplest operational model is desired |

## Detailed Comparison

| Dimension | POLLING | EVENT_DRIVEN | HYBRID |
|-----------|---------|--------------|--------|
| **Detection Latency** | Minutes to hours (depends on schedule interval) | Seconds (immediate FPolicy event) | Seconds + periodic catch-up |
| **Cost** | Low (EventBridge Scheduler + Lambda execution only) | Medium (Fargate 24/7 operation) | Medium-High (Fargate + Scheduler) |
| **Operational Complexity** | Low (stateless, idempotent) | High (TCP listener, IP management, ONTAP configuration) | Highest (both operations + consistency logic) |
| **Event Durability** | High (no loss — full scan each time) | Medium (gaps during Fargate restart) | High (periodic scan fills gaps) |
| **Scalability** | High (Lambda parallel execution) | Medium (depends on Fargate task count) | High |
| **ONTAP Dependency** | None (S3 AP only) | High (FPolicy configuration, external-engine) | High |
| **Supported Protocols** | All (via S3 AP) | NFSv3/NFSv4.0/NFSv4.1/SMB | All |

## Details for Each Mode

### POLLING Mode

```
EventBridge Scheduler (cron/rate)
  └─→ Step Functions
       ├─→ Discovery Lambda: Detect changes via ListObjectsV2
       ├─→ Map State: Process new/updated files in parallel
       └─→ Report Lambda: Send result notifications
```

**Change Detection Method**:
- LastModified timestamp comparison
- Store previous scan timestamp in DynamoDB
- Process only new/updated files

**Advantages**:
- Works with S3 AP only (no FPolicy required)
- Stateless and idempotent
- Easy recovery from failures (just re-run)

**Disadvantages**:
- No real-time capability
- Changes during schedule intervals are not detected until next execution
- ListObjectsV2 for large file counts increases cost

### EVENT_DRIVEN Mode

```
NFS/SMB File Operation
  └─→ ONTAP FPolicy Engine
       └─→ ECS Fargate (TCP :9898)
            └─→ SQS Queue
                 └─→ Bridge Lambda
                      └─→ EventBridge Custom Bus
                           └─→ Target (Step Functions / Lambda)
```

**Advantages**:
- Sub-second event detection
- Can identify file operation types (create/write/delete/rename)
- Avoids unnecessary scanning

**Disadvantages**:
- Event gap during Fargate task restart (30-60 seconds)
- Requires ONTAP FPolicy configuration and management
- TCP listener operations (IP tracking, health checks)
- NFSv4.2 is not supported by FPolicy

### HYBRID Mode

```
[EVENT_DRIVEN path]
NFS/SMB → FPolicy → Fargate → SQS → EventBridge → Immediate processing

[POLLING path (periodic consistency check)]
EventBridge Scheduler → Step Functions → Discovery Lambda → Change detection → Gap-fill processing
```

**Advantages**:
- Real-time detection + periodic gap filling
- Minimizes event loss risk
- Both paths operate independently

**Disadvantages**:
- Highest operational complexity
- Requires duplicate processing elimination logic (DynamoDB idempotency)
- Highest cost

## Selection Flowchart

```
Is real-time detection required?
├── No → POLLING
│        (Simplest, lowest cost)
└── Yes
    ├── Is event loss acceptable?
    │   ├── Yes → EVENT_DRIVEN
    │   │        (Can operate without Persistent Store)
    │   └── No
    │       ├── Is Persistent Store (ONTAP 9.14.1+) available?
    │       │   ├── Yes → EVENT_DRIVEN + Persistent Store
    │       │   │        (Production / Compliance profile)
    │       │   └── No → HYBRID
    │       │            (Periodic gap-fill via POLLING)
    │       └── Is simplest operation a priority?
    │           ├── Yes → EVENT_DRIVEN + Persistent Store
    │           └── No → HYBRID
    └── (If unsure)
        → Start with POLLING and migrate to EVENT_DRIVEN as requirements evolve
```

## Cost Comparison (Monthly Estimate, ap-northeast-1)

| Component | POLLING (1-hour interval) | EVENT_DRIVEN | HYBRID |
|-----------|--------------------------|--------------|--------|
| EventBridge Scheduler | ~$1 | — | ~$1 |
| Lambda (Discovery) | ~$5-20 | — | ~$5-20 |
| Lambda (Processing) | Workload-dependent | Workload-dependent | Workload-dependent |
| Fargate (24/7) | — | ~$30-50 | ~$30-50 |
| SQS | — | ~$1-5 | ~$1-5 |
| DynamoDB (idempotency) | — | ~$1-5 | ~$5-10 |
| **Total (excluding processing Lambda)** | **~$6-21** | **~$32-60** | **~$42-86** |

> The above is an estimate for small-to-medium workloads (~1000 files/day). Actual costs depend on file count, size, and processing content.

## Migration Path

```
POLLING ──→ EVENT_DRIVEN ──→ HYBRID
  │              │               │
  │ Add:         │ Add:          │
  │ • FPolicy    │ • Scheduler   │
  │ • Fargate    │ • Discovery   │
  │ • SQS        │   Lambda      │
  │ • Bridge     │ • Dedup logic │
  └──────────────┴───────────────┘
```

## References

- [Streaming vs Polling Selection Guide](streaming-vs-polling-guide.md)
- [Event-Driven FPolicy Quick Start](event-driven/README.md)
- [Deployment Profiles](deployment-profiles.md)
- [FPolicy Persistent Store Configuration](event-driven/fpolicy-persistent-store.md)
