# SnapMirror Cross-Region DR + S3 Access Points Pattern

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

## Overview

A disaster recovery pattern that replicates data collected via S3 Access Points using SnapMirror Asynchronous to a cross-region destination, with automated failover re-attaching a new S3 AP on the destination volume.

During normal operations, data is ingested via S3 AP on the source volume. On a DR event, a Lambda function orchestrates failover in ~3 minutes: SnapMirror break → junction path → S3 AP creation.

## Architecture

```mermaid
graph TB
    subgraph "Normal Operations (Region A)"
        WRITER[Writer Lambda]
        S3AP_SRC[S3 Access Point<br/>Source]
        SRC_VOL[Source Volume<br/>vol_sm_dr_source]
    end
    subgraph "Replication"
        SM[SnapMirror Async<br/>Schedule: 5-min intervals]
    end
    subgraph "DR Failover (Region B)"
        FAILOVER[Failover Lambda]
        S3AP_DST[S3 Access Point<br/>Destination<br/>(created on failover)]
        DST_VOL[Dest Volume (DP)<br/>vol_sm_dr_dest]
        SNS[SNS Notification]
        CLIENT[Applications<br/>(switch to new S3 AP)]
    end

    WRITER -->|PutObject| S3AP_SRC
    S3AP_SRC --> SRC_VOL
    SRC_VOL -->|Incremental<br/>replication| SM
    SM --> DST_VOL
    FAILOVER -->|1. Break SM<br/>2. Set junction<br/>3. Create AP| DST_VOL
    FAILOVER --> S3AP_DST
    FAILOVER --> SNS
    SNS --> CLIENT
    CLIENT -->|S3 API| S3AP_DST
```

## Key Components

| Component | Description |
|-----------|-------------|
| Source Volume + S3 AP | Data ingestion point (Region A). Normal operations |
| SnapMirror Async | Volume-level incremental replication (RPO = schedule interval) |
| Destination Volume (DP) | Data protection volume (read-only until break). Created via FSx API (SM-VAL-009) |
| Failover Lambda | Automates: break → junction → S3 AP creation. RTO ~3 min |
| SNS Topic | Notifies applications of new S3 AP endpoint after failover |

## RTO / RPO

| Metric | Value | Notes |
|--------|:-----:|-------|
| **RTO** | ~3 minutes | SnapMirror break (instant) + junction propagation (~2 min) + S3 AP creation (~30s) |
| **RPO** | ≤ SnapMirror schedule | Default 5-minute schedule. Data since last transfer may be lost |

## Prerequisites

> 📐 **Design Guide**: For S3 AP directory design, performance characteristics, and PoC checklist, see [Design Considerations](../../docs/design-considerations-en.md).

- 2 FSx for ONTAP clusters in different regions
- VPC Peering with Cluster/SVM Peering established
- DP Destination Volume created via `aws fsx create-volume` (not ONTAP REST API alone — SM-VAL-009)
- SnapMirror relationship initialized and in `snapmirrored` state
- fsxadmin credentials in Secrets Manager (both regions)
- Lambda VPC access to destination ONTAP management IP (port 443)

## Deploy

```bash
# 1. Deploy stack (creates Source Vol, Dest DP Vol, Failover Lambda, SNS)
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name fsxn-sm-dr \
  --parameter-overrides file://params.example.json \
  --capabilities CAPABILITY_NAMED_IAM

# 2. Create Source S3 AP + SnapMirror relationship
#    (see PostDeployInstructions in stack outputs)

# 3. Test failover (dry run)
aws lambda invoke \
  --function-name fsxn-sm-dr-failover-dev \
  --payload '{"dry_run": true}' \
  /tmp/dr-dryrun.json
```

## Execute Failover

```bash
# Trigger DR failover
aws lambda invoke \
  --function-name fsxn-sm-dr-failover-dev \
  --payload '{}' \
  /tmp/dr-result.json

# Check result
cat /tmp/dr-result.json
# → {"s3_access_point": {"arn": "...", "alias": "..."}, ...}
```

## Verify

```bash
# After failover, read from destination S3 AP
aws s3api list-objects-v2 \
  --bucket <dest-s3-ap-alias>

aws s3api get-object \
  --bucket <dest-s3-ap-alias> \
  --key test/sample.txt \
  /tmp/recovered.txt
```

## Technical Constraints

| Constraint | Details |
|-----------|---------|
| SnapMirror Asynchronous only | Synchronous mode NOT supported for S3 NAS bucket volumes |
| SVM-DR not supported | SVM containing S3 NAS bucket blocks SVM-DR. Volume-level SnapMirror only |
| DP Volume via FSx API | SM-VAL-009: Volumes created only via ONTAP REST API are invisible to FSx API, blocking S3 AP |
| S3 AP not transferred | SM-002: S3 AP is an AWS-layer resource. New AP required at destination |
| Client application update | New AP has different ARN/alias. Applications must switch endpoints |
| SnapMirror schedule | FSx for ONTAP minimum: 5-minute intervals |

## Clean Up (Order Critical — SM-VAL-011)

```bash
# ⚠️ Follow exact order to prevent orphaned resources

# 1. Delete SnapMirror relationship (from DESTINATION cluster)
#    ONTAP REST: DELETE /api/snapmirror/relationships/<uuid>?destination_only=true
#    Then from SOURCE: snapmirror release (ONTAP CLI)

# 2. Delete SVM Peers (BOTH clusters) — poll both sides until num_records: 0

# 3. Delete Cluster Peers (both clusters)

# 4. Delete VPC Peering (only after step 2 confirmed)

# 5. Detach/delete S3 Access Points (source and destination if created)
aws fsx detach-and-delete-s3-access-point --s3-access-point-arn <src-arn>
aws fsx detach-and-delete-s3-access-point --s3-access-point-arn <dest-arn>

# 6. Delete CloudFormation stack
aws cloudformation delete-stack --stack-name fsxn-sm-dr
```

## References

- [NetApp Docs: S3 multiprotocol — Data protection](https://docs.netapp.com/us-en/ontap/s3-multiprotocol/index.html)
- [NetApp KB: SVM DR of S3 buckets](https://kb.netapp.com/on-prem/ontap/DP/SnapMirror-KBs/Is_SVM_Disaster_Recovery_(SVM_DR)_of_S3_buckets_supported%3F)
- [AWS Docs: FSx for ONTAP SnapMirror](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/scheduled-replication.html)
- [AWS Docs: FSx for ONTAP S3 Access Points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)
- [NetApp Docs: FlexCache supported features](https://docs.netapp.com/us-en/ontap/flexcache/supported-unsupported-features-concept.html)
