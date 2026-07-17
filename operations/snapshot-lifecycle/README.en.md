# OPS4: Snapshot Lifecycle Management

🌐 **Language / 言語**: [日本語](README.md) | English

---

## Overview

A serverless pattern that audits FSx for ONTAP snapshots daily, providing retention
policy compliance checks, Snapshot Policy drift detection, and Human Review based
cleanup of expired snapshots.

**Key features**:
- Regulatory retention presets (FISC / HIPAA / NARA / CUSTOM)
- MinRetentionDays safety guard (never recommends deletion of recent snapshots)
- Snapshot Policy drift detection (expected vs actual count divergence)
- Human Review approval workflow (Level 2: mandatory human approval before deletion)
- AI summary (Bedrock Nova)

---

## Architecture

```
EventBridge Scheduler (daily)
    │
    ▼
Step Functions
    ├── 1. Collect Lambda (VPC)
    │       ├── ONTAP REST API → snapshot enumeration per volume
    │       └── ONTAP REST API → Snapshot Policy definitions
    │
    ├── 2. Analyze Lambda
    │       ├── Retention compliance check (age > MaxRetentionDays = expired)
    │       ├── MinRetentionDays protection (young snapshots excluded)
    │       ├── Snapshot Policy drift detection
    │       └── Bedrock AI summary (optional)
    │
    └── 3. Report Lambda
            ├── S3 (JSON/HTML audit report)
            ├── CloudWatch (RetentionCompliancePercent, etc.)
            └── [Level 1+] SNS alert
```

---

## Retention Policy Presets

| Preset | Retention (days) | Use Case | Basis |
|--------|:----------------:|----------|-------|
| `FISC` | 2,557 (7 years) | Financial institutions | FISC Security Standards |
| `HIPAA` | 2,192 (6 years) | Healthcare | HIPAA §164.530(j) |
| `NARA` | 10,950 (30 years) | Government/archives | National Archives standards |
| `CUSTOM` | (parameter) | General enterprise | Freely configurable via MaxRetentionDays |

> **Important**: When a preset is selected, snapshots **within** the retention period are never recommended for deletion.

---

## Quick Start

```bash
cd operations/snapshot-lifecycle
cp samconfig.toml.example samconfig.toml

# DemoMode
sam build && sam deploy --parameter-overrides \
  FileSystemIds=fs-demo01 DemoMode=true EnableBedrockSummary=false

# Production (CUSTOM 90-day retention)
sam build && sam deploy --parameter-overrides \
  FileSystemIds=fs-0123456789abcdef0 \
  OntapSecretArn=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:fsxn/admin-XXXXXX \
  AutomationLevel=1 RetentionPolicy=CUSTOM MaxRetentionDays=90 \
  NotificationEmail=ops-team@example.com \
  VpcSubnetIds=subnet-xxx,subnet-yyy VpcSecurityGroupIds=sg-xxx
```

---

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `RetentionPolicy` | `CUSTOM` | Retention preset (FISC/HIPAA/NARA/CUSTOM) |
| `MaxRetentionDays` | `90` | Maximum retention days (CUSTOM mode) |
| `MinRetentionDays` | `7` | Minimum retention days (never recommend deletion within) |
| `SnapshotReserveWarningPercent` | `80` | Snapshot reserve usage warning threshold |
| `FileSystemIds` | (required) | Target FS IDs |
| `OntapSecretArn` | `""` | fsxadmin credentials |
| `AutomationLevel` | `0` | 0=report, 1=alert, 2=Human Review+delete |
| `DemoMode` | `false` | Use mock data |
| `EnableBedrockSummary` | `true` | AI recommendation generation |

---

## Outputs

### CloudWatch Custom Metrics (Namespace: `FSxOps`)

| Metric | Unit | Description |
|--------|------|-------------|
| `ExpiredSnapshotCount` | Count | Number of expired snapshots |
| `ExpiredSnapshotSizeGB` | Gigabytes | Total size of expired snapshots |
| `PolicyDriftVolumeCount` | Count | Volumes with detected policy drift |
| `RetentionCompliancePercent` | Percent | Compliance rate (100% = all within retention) |

---

## Testing

```bash
python3 -m pytest operations/snapshot-lifecycle/tests/ -v
make test-ops4
```

---

## Governance Note

**This pattern may recommend snapshot deletion, but includes these safety mechanisms**:

1. **MinRetentionDays**: Snapshots within this period are NEVER recommended for deletion
2. **Regulatory presets**: FISC/HIPAA/NARA selections automatically enforce legal retention
3. **Human Review**: At `AutomationLevel=2`, human approval is mandatory before any deletion
4. **Audit trail**: All operations logged in CloudTrail + CloudWatch Logs

> For regulated industries, always confirm `RetentionPolicy` settings with legal/compliance teams.

---

## Related Solutions

| Solution | Relationship |
|----------|-------------|
| ONTAP Snapshot Policy (native) | This pattern **audits compliance** with the policy. Policy configuration is ONTAP native. |
| [NetApp/FSx-ONTAP-monitoring](https://github.com/NetApp/FSx-ONTAP-monitoring) | Monitoring only. This pattern adds retention compliance + drift detection + AI recommendations. |
| AWS Backup | Manages backup lifecycle. This pattern is specific to ONTAP native snapshots. |
