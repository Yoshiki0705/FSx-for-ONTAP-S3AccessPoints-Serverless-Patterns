# HA LifeKeeper Monitoring — FSx for ONTAP S3 AP Pattern

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Overview

A serverless pattern that non-intrusively collects and analyzes **SIOS LifeKeeper** HA cluster logs and failover events via **Amazon FSx for NetApp ONTAP** S3 Access Points.

Provides **Root Cause Analysis** powered by Amazon Bedrock (Nova Pro) and **Cluster Health Scoring** for rapid failover diagnosis and predictive maintenance.

---

## Target Scenario

Enterprise environments running SAP, Oracle, or mission-critical applications protected by SIOS LifeKeeper, with FSx for ONTAP Multi-AZ as shared storage.

**Challenges**:
- Root cause identification after failover is time-consuming
- LifeKeeper log analysis is manual, knowledge-siloed
- Adding monitoring agents to HA nodes increases failure points
- Separating storage-layer (FSx for ONTAP) vs application-layer (LifeKeeper) faults is difficult

**Solution**:
Use FSx for ONTAP S3 Access Points to read LifeKeeper logs **non-intrusively** via a serverless analysis pipeline. AI-driven analysis reduces operational burden.

---

## Architecture

| Layer | Component | HA Scope |
|-------|-----------|----------|
| Storage | FSx for ONTAP Multi-AZ | Data availability, AZ redundancy, automatic failover |
| Application | SIOS LifeKeeper | VIP control, service monitoring, automatic recovery |
| Analysis (this pattern) | S3 AP + Serverless + Bedrock | Non-intrusive log analysis, AI root cause analysis |

---

## Features

### Discovery Lambda
- Discovers LifeKeeper log files via FSx for ONTAP S3 AP
- Classifies logs: failover events / health checks / config changes / Recovery Kit logs
- Auto-evaluates severity (CRITICAL / HIGH / MEDIUM / LOW)

### Processing Lambda
- Detects LifeKeeper resource state transitions (ISP→OSF, ISS→ISP, etc.)
- Root cause analysis via Bedrock (Nova Pro)
- Computes cluster health score (0-100)
- Separates storage-layer vs application-layer faults

### Report Lambda
- Generates Markdown health reports
- Sends SNS failover alerts based on severity thresholds
- Includes recommended LifeKeeper commands (`lcdstatus`, comm path checks)

---

## Deployment

### Prerequisites

- AWS SAM CLI
- Python 3.12
- FSx for ONTAP file system + S3 Access Point (not required when DemoMode=true)
- Bedrock model access enabled (Amazon Nova Pro)

### Quick Deploy (Demo Mode)

```bash
cd solutions/ha/lifekeeper-monitoring
sam build
sam deploy --guided \
  --parameter-overrides \
    DemoMode=true \
    S3AccessPointAlias=your-demo-bucket \
    OutputBucketName=your-output-bucket \
    NotificationEmail=your@email.com
```

### Production Deploy

```bash
sam build
sam deploy --guided \
  --parameter-overrides \
    DemoMode=false \
    S3AccessPointAlias=your-fsxn-s3ap-alias-s3alias \
    OutputBucketName=your-output-bucket \
    NotificationEmail=ops-team@company.com \
    OntapSecretArn=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:ontap-creds-XXXXXX \
    ScheduleExpression="rate(5 minutes)" \
    FailoverAlertSeverity=HIGH \
    ClusterName=prod-sap-cluster \
    TriggerMode=HYBRID
```

---

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| S3AccessPointAlias | (required) | FSx for ONTAP S3 AP alias |
| DemoMode | false | Enable demo mode |
| ScheduleExpression | rate(5 minutes) | Monitoring interval |
| TriggerMode | POLLING | POLLING / EVENT_DRIVEN / HYBRID |
| BedrockModelId | amazon.nova-pro-v1:0 | Bedrock model for analysis |
| FailoverAlertSeverity | CRITICAL | Minimum severity for SNS alerts |
| ClusterName | lifekeeper-cluster | LifeKeeper cluster name |
| OutputDestination | STANDARD_S3 | Report output target |
| LogRetentionInDays | 90 | CloudWatch Logs retention |

---

## Success Metrics

### Business Outcome
| Metric | Target | Measurement |
|--------|--------|-------------|
| Mean Time to Identify Root Cause (MTTIRC) | < 10 min (from > 60 min manual) | Time from alert to root cause identification |
| Operational workload reduction | 70% reduction in manual log analysis hours | Monthly triage hours comparison |

### Technical KPI
| Metric | Target | Measurement |
|--------|--------|-------------|
| Log discovery completeness | 100% of LifeKeeper log files detected | Discovery output vs filesystem listing |
| Health score accuracy | > 85% correlation with actual cluster health | Validated against real failover events |
| Bedrock analysis latency | < 30s per failover event | Processing Lambda duration metric |

### Quality KPI
| Metric | Target | Measurement |
|--------|--------|-------------|
| False positive rate (alerts) | < 5% | Alerts sent vs actual issues requiring action |
| State transition detection | 100% of ISP/OSF/ISS transitions captured | Log parsing validation |

### Cost KPI
| Metric | Target | Measurement |
|--------|--------|-------------|
| Monthly monitoring cost | < $15 (at 5-min polling, 1 cluster) | CloudWatch cost dashboard |
| Per-failover analysis cost | < $0.10 | Bedrock invocation cost per event |

### Go/No-Go Criteria
- [ ] DemoMode=true deployment succeeds within 5 minutes
- [ ] Health score correctly identifies CRITICAL state from sample failover logs
- [ ] SNS alert fires within 10 seconds of health score crossing threshold
- [ ] Report contains actionable LifeKeeper commands
- [ ] No impact to production LifeKeeper cluster operations

---

## Health Score

| Score | Level | Meaning | Recommended Action |
|-------|-------|---------|-------------------|
| 90-100 | HEALTHY | Normal | Review periodic reports |
| 70-89 | WARNING | Attention needed | Check comm paths, storage I/O |
| 50-69 | DEGRADED | Degraded | Verify with LifeKeeper GUI/CLI, check FSx for ONTAP monitoring |
| 0-49 | CRITICAL | Critical | Immediate action. Run `lcdstatus` + ONTAP management CLI |

---

## Testing

```bash
# Unit tests
python3 -m pytest solutions/ha/lifekeeper-monitoring/tests/ -v

# E2E test with DemoMode
aws stepfunctions start-execution \
  --state-machine-arn <StateMachineArn> \
  --input '{"trigger": "manual", "cluster_name": "demo-cluster"}'
```

---

## Related Patterns

| Pattern | Relation |
|---------|----------|
| `solutions/sap/erp-adjacent/` | LifeKeeper-protected SAP IDoc/batch processing |
| `solutions/event-driven/fpolicy/` | FPolicy event-driven immediate log detection |
| `solutions/flexcache/anycast-dr/` | Multi-region DR reference architecture |

---

## Governance Note

This pattern is designed for **operational monitoring assistance**:

- AI analysis results are **advisory information** for operational decisions; no automatic failover control or recovery actions are performed
- LifeKeeper configuration changes must be made via LifeKeeper GUI/CLI
- Failover decisions are delegated to LifeKeeper's own health check mechanisms
- This pattern assumes a **Human-in-the-loop** design

---

## Performance Considerations

- **Monitoring interval**: 5-minute polling incurs up to 5 minutes detection delay. Use `TriggerMode=HYBRID` with FPolicy event-driven for near-real-time
- **Log volume**: For large log volumes, control batch size with `MaxFilesPerExecution`
- **Bedrock cost**: Frequent failovers increase Bedrock invocation costs. Use `FailoverAlertSeverity` to filter analysis targets
- **S3 AP throughput**: FSx for ONTAP S3 AP shares bandwidth with the file system. Consider Snapshot-based reads to avoid impacting production I/O

---

## License

MIT
