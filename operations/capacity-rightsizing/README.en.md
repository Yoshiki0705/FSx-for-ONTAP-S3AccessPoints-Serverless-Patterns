# OPS1: Capacity Rightsizing

🌐 **Language / 言語**: [日本語](README.md) | English

---

## Overview

A serverless pattern that monitors FSx for ONTAP volume capacity and throughput on a daily basis, providing AI-powered action recommendations and What-If cost simulations.

**Key features**:
- Natural-language recommendations via Bedrock Nova
- What-If simulation (instant cost delta for tier changes)
- Progressive automation (Level 0: report only → Level 2: approval-based execution)
- Multi-FS cross-analysis (one stack monitors multiple file systems)
- Gen1/Gen2 auto-detection
- DemoMode (run without FSx for ONTAP)

---

## Architecture

```
EventBridge Scheduler (rate/cron)
    │
    ▼
Step Functions
    ├── 1. Collect Lambda (VPC)
    │       ├── ONTAP REST API → volume space/autosize
    │       └── CloudWatch → throughput/CPU/storage utilization
    │
    ├── 2. Analyze Lambda
    │       ├── Threshold checks (>80% → upsize / <20% → downsize)
    │       ├── Throughput tier recommendations
    │       ├── What-If scenario generation
    │       └── Bedrock Nova AI summary (optional)
    │
    └── 3. Report Lambda
            ├── S3 (JSON/HTML reports)
            ├── CloudWatch (custom metrics: FSxOps namespace)
            └── [Level 1+] SNS alerts
```

---

## Quick Start

### DemoMode (no FSx for ONTAP required)

```bash
cd operations/capacity-rightsizing
cp samconfig.toml.example samconfig.toml

# Copy shared/ modules into Lambda function directories (required before sam build)
./build.sh

sam build
sam deploy --parameter-overrides \
  FileSystemIds=fs-demo01 \
  DemoMode=true \
  EnableBedrockSummary=false
```

### Production deployment

```bash
# Edit samconfig.toml with your values (see parameter retrieval table in operations/README.md)
cp samconfig.toml.example samconfig.toml

./build.sh && sam build && sam deploy
```

---

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `FileSystemIds` | (required) | Target FS IDs (comma-separated) |
| `OntapSecretArn` | `""` | fsxadmin credentials (Secrets Manager ARN) |
| `AutomationLevel` | `0` | 0=report, 1=alert, 2=approval-execute, 3=auto |
| `ThresholdPercent` | `80` | High utilization alert threshold (%) |
| `LowUtilizationThresholdPercent` | `20` | Low utilization detection threshold (%) |
| `DemoMode` | `false` | Demo mode (use mock data) |
| `NotificationEmail` | `""` | Alert recipient |
| `ScheduleExpression` | `rate(1 day)` | Execution schedule |
| `EnableBedrockSummary` | `true` | AI recommendation generation |
| `ReportFormat` | `BOTH` | JSON / HTML / BOTH |
| `VpcSubnetIds` | `""` | Subnets for ONTAP REST API access |
| `VpcSecurityGroupIds` | `""` | Security groups for ONTAP REST API access |

---

## Outputs

### CloudWatch Custom Metrics (Namespace: `FSxOps`)

| Metric | Unit | Dimensions |
|--------|------|-----------|
| `AvgVolumeUtilizationPercent` | Percent | FileSystemId |
| `ThroughputUtilizationPercent` | Percent | FileSystemId |
| `RecommendationCount` | Count | FileSystemId |
| `MonthlyCostDeltaUSD` | None | FileSystemId |

### S3 Reports

```
s3://{stack-name}-reports-{account-id}/
  reports/2026/07/13/{fs-id}/
    ├── capacity-report.json
    └── capacity-report.html
```

---

## Relationship with Related Solutions

| Solution | Relationship |
|----------|-------------|
| [AWS FSxOntapDynamicStorageScaling](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/automate-storage-capacity-increase.html) | Focuses on SSD capacity auto-expansion. This pattern adds throughput + volume-level analysis + AI recommendations |
| [NetApp/fsxn-monitoring-auto-resizing](https://github.com/NetApp/fsxn-monitoring-auto-resizing) | Focuses on immediate resize. This pattern provides a progressive automation approach (Level 0-3) |
| [NetApp/FSx-ONTAP-monitoring](https://github.com/NetApp/FSx-ONTAP-monitoring) | Builds CloudWatch alarms + dashboards. This pattern adds analysis + What-If + Human Review as an additional layer |
| [AWS Blog: Automate monitoring at scale](https://aws.amazon.com/blogs/storage/automate-monitoring-at-scale-for-amazon-fsx-for-netapp-ontap-volumes/) | Concept article for cross-FS monitoring. This pattern implements it as a deployable template |

> If you already have these solutions deployed, this pattern can coexist as an **additional layer** (analysis + recommendations + automation).

---

## Testing

```bash
# From project root
python3 -m pytest operations/capacity-rightsizing/tests/ -v

# Or via Makefile
make test-ops1
```

---

## Governance Note

This pattern is designed for cost optimization and capacity management.
It does not override legal data retention requirements (FISC / HIPAA / NARA, etc.).

- Capacity changes at `AutomationLevel=2+` go through **Human Review** (approval workflow)
- Change freeze periods are controlled via SSM Change Calendar (Level 2/3)
- All operations are logged in CloudTrail + CloudWatch Logs

---

## Related Documentation

| Document | Content |
|----------|---------|
| [operations/docs/metrics-mapping.md](../docs/metrics-mapping.md) | CloudWatch ↔ ONTAP REST mapping |
| [operations/docs/ops-adoption-roadmap.md](../docs/ops-adoption-roadmap.md) | Progressive adoption guide |
| [operations/docs/existing-solutions-reference.md](../docs/existing-solutions-reference.md) | Existing solution comparison |
| [operations/docs/slo-definitions.md](../docs/slo-definitions.md) | SLO/SLI definitions |
