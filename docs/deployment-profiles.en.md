# Deployment Profiles — FPolicy Event-Driven Pattern

🌐 **Language / 言語**: [日本語](deployment-profiles.md) | [English](deployment-profiles.en.md)

## Overview

The FPolicy Event-Driven pattern has 3 deployment profiles based on requirements. You can progressively elevate the operational level from PoC to production to compliance-sensitive environments.

## Profile Comparison

| Dimension | PoC/Demo | Production | Compliance-sensitive |
|-----------|----------|------------|---------------------|
| **FPolicy Server** | Fargate (direct IP) | EC2 static IP or NLB | EC2 static IP + NLB |
| **is-mandatory** | `false` | `true` (ONTAP 9.15.1+) | `true` (ONTAP 9.15.1+) |
| **Persistent Store** | Not required | Recommended | Required (ONTAP 9.14.1+) |
| **Retry / Dedup** | Best-effort | DynamoDB idempotency | DynamoDB + S3 Object Lock lineage |
| **Alarm Profile** | Minimal (error only) | Full (latency + error + backlog) | Full + audit trail |
| **Event Loss Tolerance** | Acceptable | Near-zero (compensated by retry) | Zero (Persistent Store + audit) |
| **Minimum ONTAP Version** | 9.14.1+ | 9.15.1+ | 9.15.1+ |
| **Intended Use** | Functional verification, demos, PoC | Production workloads | Financial regulation, healthcare, government |

---

## Profile 1: PoC/Demo

### Features

- **Minimal configuration**: Single Fargate task, SQS, and EventBridge only
- **IP management**: IP changes on Fargate task restart; IP Updater Lambda automatically updates ONTAP external-engine
- **Event loss**: Events may be lost during Fargate task restart (~30-60 seconds)
- **Cost**: Minimal (Fargate Spot available)

### Configuration

```yaml
# template.yaml (solutions/event-driven/fpolicy/)
Parameters:
  IsMandatory:
    Default: "false"    # Do not block file operations
  EnablePersistentStore:
    Default: "false"    # Persistent Store not used
  AlarmProfile:
    Default: "minimal"  # Error alarms only
```

### Applicable Scenarios

- Initial FPolicy operation verification
- Partner demonstrations
- Development/test environments
- Non-critical workloads where event loss is acceptable

---

## Profile 2: Production

### Features

- **High availability**: EC2 static IP or NLB eliminates the need for ONTAP external-engine IP reconfiguration
- **is-mandatory=true**: File operations are blocked when FPolicy server is unavailable (prevents event loss)
- **Persistent Store recommended**: Event buffering during server disconnection
- **Idempotency guarantee**: Deduplication via DynamoDB

### Configuration

```yaml
Parameters:
  IsMandatory:
    Default: "true"     # Block file operations when server unavailable
  EnablePersistentStore:
    Default: "true"     # Event buffering enabled
  AlarmProfile:
    Default: "full"     # Latency + error + backlog
  ComputeType:
    Default: "ec2"      # Static IP
```

### is-mandatory=true Behavior

When `is-mandatory=true` (ONTAP 9.15.1+) is set:
- Target file operations are blocked when the FPolicy server is not connected
- This prevents event loss but introduces the risk of file access stopping during server failures
- Redundancy via NLB + multiple tasks is recommended for production environments

### Persistent Store Role

Persistent Store (ONTAP 9.14.1+) persists events to an SVM volume when the FPolicy server is disconnected, and sends them in order upon reconnection:

- **Target**: Asynchronous and non-mandatory FPolicy policies
- **Event ordering**: Guaranteed (replayed in occurrence order)
- **autoflush_interval**: Configurable (default PT120S)
- **Capacity estimation**: `event_rate × max_outage_duration × avg_event_size × safety_factor`

> **Reference**: A 1 GB volume can buffer approximately 2 million events (1 event ≈ 500 bytes)

### Applicable Scenarios

- Production data pipelines
- Workloads requiring near-real-time processing
- Environments with defined SLAs

---

## Profile 3: Compliance-sensitive

### Features

- **Zero event loss guarantee**: Combination of Persistent Store + is-mandatory + audit trail
- **Data lineage**: Tamper-proof lineage records with S3 Object Lock
- **RPO/RTO defined**: Clear recovery objectives
- **Audit-ready**: Processing trail retained for all events

### Configuration

```yaml
Parameters:
  IsMandatory:
    Default: "true"
  EnablePersistentStore:
    Default: "true"
  AlarmProfile:
    Default: "compliance"  # Full + audit trail + SLO violation
  EnableLineage:
    Default: "true"        # S3 Object Lock 7-year retention
  EnableReplayStormProtection:
    Default: "true"        # Rate limiting during replay storms
```

### Compliance Requirement Mapping

| Regulation/Standard | Corresponding Feature |
|--------------------|----------------------|
| FISC Security Standards | Zero event loss + audit trail + encryption |
| GDPR | Data lineage + processing records + deletion tracking |
| SOX | Tamper-proof lineage (S3 Object Lock) |
| HIPAA | Access logs + encryption + audit |
| NARA (Government Archives) | Permanent retention + integrity verification |

### RPO/RTO Design

| Metric | Target | Implementation |
|--------|--------|----------------|
| RPO (Recovery Point Objective) | 0 events | Persistent Store + is-mandatory |
| RTO (Recovery Time Objective) | < 5 min | ECS auto-recovery + IP Updater |
| Replay Recovery Time | < 30 min (100K events) | Sustainable rate: 100 events/sec |

### Applicable Scenarios

- Financial institutions (FISC compliance)
- Healthcare organizations (HIPAA compliance)
- Government agencies (NARA / FOIA compliance)
- Regulated industries in general

---

## Profile Selection Flowchart

```
Is event loss acceptable?
├── Yes → PoC/Demo
└── No
    ├── Are there regulatory/compliance requirements?
    │   ├── Yes → Compliance-sensitive
    │   └── No → Production
    └── (If unsure, start with Production and
         upgrade to Compliance-sensitive as needed)
```

## Staged Migration Path

```
PoC/Demo ──────→ Production ──────→ Compliance-sensitive
  │                  │                      │
  │ Add:             │ Add:                 │
  │ • EC2/NLB        │ • S3 Object Lock     │
  │ • Persistent     │ • Lineage v2         │
  │   Store          │ • SLO Runbooks       │
  │ • DynamoDB       │ • Replay Storm       │
  │   idempotency    │   Protection         │
  │ • Full alarms    │ • Audit trail        │
  └──────────────────┴──────────────────────┘
```

## References

- [FPolicy Persistent Store Configuration Guide](event-driven/fpolicy-persistent-store.md)
- [SLO Violation Runbooks](runbooks/)
- [Replay Storm Testing](../tests/load/)
- [ONTAP FPolicy — NetApp Documentation](https://docs.netapp.com/us-en/ontap/nas-audit/persistent-stores.html)
