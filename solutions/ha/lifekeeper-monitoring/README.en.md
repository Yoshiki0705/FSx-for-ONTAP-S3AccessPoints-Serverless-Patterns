# HA LifeKeeper Monitoring — FSx for ONTAP S3 AP Pattern

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

🌐 **Language / 言語**: [日本語](README.md) | English | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

## Overview

A serverless pattern that non-intrusively collects and analyzes the logs and failover events of a high availability (HA) cluster built with **SIOS LifeKeeper**, via the S3 Access Points of **Amazon FSx for NetApp ONTAP**.

**Root Cause Analysis** and **cluster health scoring** powered by Amazon Bedrock (Nova Pro) enable rapid failover root cause identification and early warning detection.

---

## Target Scenario

In enterprise environments, SAP, Oracle, and mission-critical business applications are HA-protected with SIOS LifeKeeper, and FSx for ONTAP Multi-AZ is used as shared storage.

**Challenges**:
- Identifying the root cause when a failover occurs is time-consuming
- LifeKeeper log analysis involves a lot of manual work and depends on individual expertise
- Adding a monitoring agent to HA cluster nodes increases the number of failure points
- Separating storage-layer (FSx for ONTAP) faults from application-layer (LifeKeeper) faults is difficult

**Solution**:
Use FSx for ONTAP S3 Access Points to process the logs written by LifeKeeper **non-intrusively** through a serverless analysis pipeline. AI-driven automated analysis reduces operational burden.

---

## SIOS LifeKeeper + FSx for ONTAP Combination

### Architecture Positioning

| Layer | Responsibility | HA Scope |
|---------|------|------------|
| Storage | FSx for ONTAP Multi-AZ | Data availability, AZ redundancy, automatic failover |
| Application | SIOS LifeKeeper | VIP control, service monitoring, automatic recovery |
| Analysis (this pattern) | S3 AP + Serverless + Bedrock | Non-intrusive log analysis, AI root cause analysis |

### What Is SIOS LifeKeeper

HA clustering software for Linux/Windows provided by SIOS Technology. It delivers high availability for mission-critical applications on AWS.

**Key features**:
- Application-aware Recovery Kits (directly monitor SAP S/4HANA, Oracle, NFS, IP, and more)
- Cross-AZ failover (2 AZs within a single region)
- VIP management (Elastic IP / Secondary IP)
- Split-brain prevention through redundant communication paths
- Officially available as an AWS Partner Solution

**Track record**: Astro Malaysia adopted SIOS LifeKeeper in a SAP + Oracle on AWS environment and achieved 99.99% availability.

### FSx for ONTAP Shared Disk Support (V10 and Later)

From LifeKeeper V10.0.1 onward, FSx for ONTAP can be directly protected as a shared disk. Previously only DataKeeper (block replication) was available, but the addition of a shared-disk configuration enables a simpler HA setup.

| Protocol | Required Recovery Kit | Notes |
|-----------|-------------------|------|
| iSCSI | DMMP Recovery Kit | Required when using FSx for ONTAP on AWS |
| NFS | NAS Recovery Kit | Standard NFS shared-disk configuration |

> A SIOS bcblog validation article (2026-05-08) confirms that switchover works correctly on a RHEL 9.6 + LifeKeeper v10.0.1 + FSx for ONTAP (iSCSI/NFS) configuration.

### Value Delivered by FSx for ONTAP

- **Multi-AZ shared storage**: Accessible from both LifeKeeper nodes via NFS/iSCSI
- **Automatic storage failover**: Handles storage-layer AZ failures automatically
- **Snapshot**: Preserves the data state before and after failover
- **S3 Access Points**: Non-intrusive data access path for log analysis
- **Multiprotocol**: Serves SMB + NFS + iSCSI + S3 API from a single volume, avoiding duplicate copies of data
- **Cloud-native**: Can be started directly from the AWS Management Console (no separate license required)

> "The major benefit is that instead of copying data to S3 to use it, you can leverage the data on FSx for ONTAP directly through the S3 API" — from the [SIOS bcblog interview article](https://bcblog.sios.jp/netapp-ontap-lifekeeper-high-availability-design/) (Content was rephrased for compliance with licensing restrictions)

### Public References

| Resource | Publisher | URL |
|------|--------|-----|
| High availability solution using SIOS LifeKeeper and Amazon FSx for NetApp ONTAP | AWS JAPAN APN Blog | https://aws.amazon.com/jp/blogs/psa/high-availability-solution-with-sios-lifekeeper-and-amazon-fsx-for-netapp-ontap/ |
| High availability design with NetApp ONTAP and LifeKeeper | SIOS Technology (bcblog) | https://bcblog.sios.jp/netapp-ontap-lifekeeper-high-availability-design/ |
| Using Amazon FSx for NetApp ONTAP as a LifeKeeper shared disk | SIOS Technology (bcblog) | https://bcblog.sios.jp/amazon-fsx-netapp-ontap-lifekeeper-shared-disk/ |
| SIOS Protection Suite for Linux on AWS | AWS Partner Solutions | https://aws.amazon.com/solutions/partners/sios-protection-suite/ |
| LifeKeeper for Linux — Architecture Guide | AWS Quick Start | https://aws-ia.github.io/cfn-ps-sios-protection-suite/ |
| Deploying HA SAP with SIOS on AWS | AWS Blog (2019) | https://aws.amazon.com/blogs/awsforsap/deploying-highly-available-sap-systems-using-sios-protection-suite-on-aws/ |
| Using SIOS to Protect your Critical Core on AWS | AWS Blog (2020) | https://aws.amazon.com/blogs/awsforsap/using-sios-to-protect-your-critical-core-on-aws/ |
| SQL Server HA with FSx for ONTAP | AWS Blog (2022) | https://aws.amazon.com/blogs/modernizing-with-aws/sql-server-high-availability-amazon-fsx-for-netapp-ontap/ |
| Oracle HA with FSx for ONTAP | AWS Blog (2025) | https://aws.amazon.com/blogs/architecture/building-highly-available-oracle-databases-with-amazon-fsx-for-netapp-ontap/ |
| Astro Malaysia 99.99% Uptime | GlobeNewsWire (2025) | https://www.globenewswire.com/news-release/2025/11/20/3191959/0/en/ |
| LifeKeeper for Linux (AWS Marketplace) | AWS Marketplace | https://aws.amazon.com/marketplace/pp/prodview-5pxfcgrksorlo |

---

## Features

### Discovery Lambda
- Discovers LifeKeeper log files via FSx for ONTAP S3 AP
- Classifies them into failover events / health checks / configuration changes / Recovery Kit logs
- Automatically evaluates severity (CRITICAL / HIGH / MEDIUM / LOW)

### Processing Lambda
- Detects LifeKeeper resource state transitions (ISP→OSF, ISS→ISP, etc.)
- Root cause analysis via Bedrock (Nova Pro)
- Computes a cluster health score (0-100)
- Separates storage-layer vs application-layer faults

### Report Lambda
- Generates Markdown health reports
- Sends SNS failover alerts based on severity thresholds
- Includes recommended actions with LifeKeeper commands (`lcdstatus`, communication path checks)

---

## Deployment

### Prerequisites

- AWS SAM CLI
- Python 3.12
- FSx for ONTAP file system + S3 Access Point (not required when DemoMode=true)
- Bedrock model access enabled (Amazon Nova Pro)

### Quick Deploy

```bash
# Deploy in DemoMode (no FSx for ONTAP required)
# Prerequisite: AWS SAM CLI required. 'sam build' packages the code and shared layer automatically.
sam build
sam deploy --guided \
  --parameter-overrides \
    DemoMode=true \
    S3AccessPointAlias=your-demo-bucket \
    OutputBucketName=your-output-bucket \
    NotificationEmail=your@email.com
```

> **Note**: `template.yaml` is used with the SAM CLI (`sam build` + `sam deploy`).
> To deploy directly with the `aws cloudformation deploy` command, use `template-deploy.yaml` instead (this requires pre-packaging the Lambda zip files and uploading them to S3).

### Production Deploy

```bash
# Prerequisite: AWS SAM CLI required. 'sam build' packages the code and shared layer automatically.
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

### Parameters

| Parameter | Default | Description |
|-----------|-----------|------|
| S3AccessPointAlias | (required) | FSx for ONTAP S3 AP alias |
| DemoMode | false | Enable demo mode |
| ScheduleExpression | rate(5 minutes) | Monitoring interval |
| TriggerMode | POLLING | POLLING / EVENT_DRIVEN / HYBRID |
| BedrockModelId | amazon.nova-pro-v1:0 | Bedrock model for analysis |
| FailoverAlertSeverity | CRITICAL | Minimum severity for SNS alerts |
| ClusterName | lifekeeper-cluster | LifeKeeper cluster name |
| OutputDestination | STANDARD_S3 | Report output target |
| LogRetentionInDays | 90 | CloudWatch Logs retention period |

---

## Testing

```bash
# Unit tests
python3 -m pytest solutions/ha/lifekeeper-monitoring/tests/ -v

# End-to-end test in DemoMode
# (place sample logs in the demo S3 bucket beforehand)
aws stepfunctions start-execution \
  --state-machine-arn <StateMachineArn> \
  --input '{"trigger": "manual", "cluster_name": "demo-cluster"}'
```

---

## Health Score

| Score | Level | Meaning | Recommended Action |
|--------|--------|------|---------------|
| 90-100 | HEALTHY | Normal | Review periodic reports |
| 70-89 | WARNING | Attention | Check communication paths and storage I/O |
| 50-69 | DEGRADED | Degraded | Verify state via LifeKeeper GUI/CLI, monitor FSx for ONTAP |
| 0-49 | CRITICAL | Critical | Immediate action. Verify state with `lcdstatus` + ONTAP management CLI |

---

## Directory Structure

```
solutions/ha/lifekeeper-monitoring/
├── template.yaml              # SAM template
├── samconfig.toml.example     # Deployment config example
├── README.md                  # This document (Japanese)
├── README.en.md               # English README + Success Metrics
├── functions/
│   ├── discovery/
│   │   └── handler.py         # LifeKeeper log discovery
│   ├── processing/
│   │   └── handler.py         # Bedrock root cause analysis
│   └── report/
│       └── handler.py         # Report generation, alerts
├── statemachine/
│   └── workflow.asl.json      # Step Functions definition
├── docs/
│   ├── architecture.md        # Architecture details
│   └── demo-guide.md          # Demo guide (DemoMode)
└── tests/
    ├── conftest.py
    └── test_discovery.py      # Unit tests
```

---

## Related Patterns

| Pattern | Relation |
|---------|--------|
| `solutions/sap/erp-adjacent/` | IDoc/batch processing of SAP environments protected by LifeKeeper |
| `solutions/event-driven/fpolicy/` | Immediate log detection via FPolicy event-driven triggers |
| `solutions/flexcache/anycast-dr/` | Reference for multi-region DR configurations |

---

## Governance Note

This pattern is intended to **assist with operational monitoring** of HA clusters. Note the following:

- AI analysis results are **reference information** for operational decisions; no automatic failover control or recovery operations are performed
- LifeKeeper configuration changes must always be made from the LifeKeeper GUI/CLI
- Failover decisions must be delegated to LifeKeeper's own health check mechanisms
- This pattern is designed on the premise of a **Human-in-the-loop**

---

## Performance Considerations

- **Monitoring interval**: A 5-minute interval incurs up to 5 minutes of detection delay. When immediacy is required, combine FPolicy event-driven triggering with `TriggerMode=HYBRID`
- **Log size**: When there are many log files, control the batch size with `MaxFilesPerExecution`
- **Bedrock cost**: In environments where failovers occur frequently, be mindful of Bedrock invocation costs. Narrow the analysis targets with `FailoverAlertSeverity`
- **S3 AP throughput**: FSx for ONTAP S3 AP shares the bandwidth of the entire file system. Consider Snapshot-based reads so that large volumes of log reads do not affect business I/O

---

## License

MIT
