# FlexCache AnyCast / DR Pattern

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md)

## Overview

This pattern provides design guides, simulation demos, and operational design documents for implementing ONTAP FlexCache AnyCast and DR (Disaster Recovery) configurations combined with FSx for ONTAP × S3 Access Points × AWS Serverless services.

## Problems Solved

| Problem | Solution via FlexCache AnyCast / DR |
|---------|-------------------------------------|
| Read performance for geographically distributed teams | Serve hot data from nearest FlexCache |
| Cloud bursting for EDA/Media/HPC | On-premises Origin + Cloud FlexCache reduces WAN transfers |
| Read continuity during DR | Cache-based reads continue even during Origin failure |
| WAN transfer volume reduction | Cache only hot data, delta transfers |
| Client-side mount configuration complexity | Single mount point via AnyCast IP |

## Architecture Overview

```
Control Plane (AnyCast/VIP Control):
  Health Check Lambda → Route Decision Lambda → Route 53 / DNS

Data Plane (S3 AP Serverless Processing):
  EventBridge Scheduler → Step Functions → Discovery → Processing → Report

Storage Layer:
  Origin Volume → FlexCache A (Region/AZ A) → S3 AP A
                → FlexCache B (Region/AZ B) → S3 AP B
```

## Key Design Decisions

- **Simulation mode**: Can run without actual FlexCache infrastructure for demo/testing
- **Health check**: Lambda-based health monitoring of FlexCache volumes
- **Route decision**: DNS-based routing to nearest healthy FlexCache
- **S3 AP integration**: Serverless processing reads from nearest S3 AP

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture](docs/architecture.md) | Detailed architecture design |
| [Demo Guide](docs/demo-guide.md) | Failover simulation demo |
| [Design Patterns](docs/design-patterns.md) | FlexCache design patterns |
| [DR Patterns](docs/disaster-recovery-patterns.md) | Disaster recovery scenarios |
| [FAQ](docs/flexcache-anycast-faq.md) | Frequently asked questions |
| [Limitations](docs/limitations-and-support-matrix.md) | Constraints and compatibility |
| [Network Design](docs/network-design-bgp-vip.md) | BGP/VIP network design |
| [Operations Runbook](docs/operations-runbook.md) | Day-2 operations |
| [PoC Checklist](docs/poc-checklist.md) | Proof of concept planning |
| [Validation Results](docs/validation-results.md) | Test results |

## Related Use Cases

| Related UC | Connection |
|-----------|-----------|
| [media-vfx/](../media-vfx/) | FlexCache acceleration for render input assets |
| [manufacturing-analytics/](../manufacturing-analytics/) | FlexCache for inter-factory data sharing |
| [healthcare-dicom/](../healthcare-dicom/) | FlexCache for inter-site DICOM caching |
| [semiconductor-eda/](../semiconductor-eda/) | Cloud bursting for EDA tools/libraries |

## Success Metrics

| Metric | Target |
|--------|--------|
| Failover detection time | < 30 sec |
| DNS propagation time | < 60 sec |
| Read continuity during failover | > 99.9% |
| Cache hit rate (hot data) | > 80% |
| WAN transfer reduction | > 60% |
