# Cost Monitoring Runbook

**Scope**: Monitoring and attributing cost per UC for the 17-UC Phase 8
deployment.

---

## Tag strategy

Every resource deployed via `*/template-deploy.yaml` is tagged with:

| Tag | Value | Purpose |
|-----|-------|---------|
| `Project` | `fsxn-s3ap-serverless-patterns` | Top-level project filter |
| `Phase` | `phase-8` | Phase correlation |
| `UseCase` | `<uc-name>` | Per-UC attribution |
| `Environment` | `demo` \| `production` | Stage separation |

Activate the tags as cost allocation tags in Billing → Cost allocation
tags. After activation it takes ~24 hours for tags to appear in Cost
Explorer.

## Cost Explorer queries

### Per-UC daily cost

1. Cost Explorer → Filters → Tag = `UseCase`
2. Group by = `Tag: UseCase`
3. Granularity = Daily
4. Time range = last 30 days

Expected baseline for a fully deployed demo run (Tokyo region,
on-demand):

| UC | Baseline / day | Notes |
|----|---------------:|-------|
| UC1 | $0.50 | Minimal Lambda + SFN |
| UC2 | $1.20 | Textract + Comprehend |
| UC3 | $2.00 | Athena queries |
| UC5 | $3.00 | Comprehend Medical |
| UC6 | $2.50 | Bedrock Nova + Athena |
| UC7 | $2.50 | Bedrock Nova + Athena |
| UC8 | $1.80 | Rekognition + Athena |
| UC9 | $1.00 | SageMaker mock mode |
| UC10 | $1.50 | Textract |
| UC11 | $1.80 | Bedrock Nova |
| UC12 | $2.00 | Textract + Rekognition |
| UC13 | $2.20 | Textract + Comprehend + Bedrock |
| UC14 | $1.20 | Textract |
| UC15 | $1.50 | Rekognition |
| UC16 | $1.80 | Textract |
| UC17 | $2.00 | Bedrock Nova |

Outliers above baseline should be investigated against Cost Explorer
Service filter.

### Per-service breakdown for a specific UC

1. Filter: `Tag: UseCase = <uc-name>`
2. Group by: Service
3. Identify the dominant service (often Bedrock, Textract, or VPC
   NAT Gateway data transfer).

## VPC / NAT Gateway cost

NAT Gateway is a flat hourly cost ($0.045/hr in ap-northeast-1 at the
time of this writing) plus $0.045/GB data processing. Running all 17
UCs simultaneously burns ~$1/day on NAT Gateway alone, even when idle.

**Strategy**: the `cleanup_generic_ucs.py` script deletes the VPC and
NAT Gateway along with each UC stack. Use the batch cleanup pattern to
keep costs bounded:

```bash
# Deploy → test → cleanup within the same day
bash scripts/deploy_generic_ucs.sh UC6 UC7 UC8
# ... run workflows and capture screenshots ...
python3 scripts/cleanup_generic_ucs.py UC6 UC7 UC8
```

## Cost anomalies

Enable AWS Cost Anomaly Detection on the `Project` tag to catch
unexpected spikes. Recommended monitor:

- Monitor type: Custom
- Monitor name: `fsxn-s3ap-phase8-monitor`
- Scope: Linked account OR Tag = `Project: fsxn-s3ap-serverless-patterns`
- Threshold: $10 for absolute value OR 40% for percentage

Notifications can be routed to the same SNS topic created by Theme N
(`observability-alarms.yaml`).

## Budget alerts

Minimum recommended budget set:

```
Monthly budget: $300 (demo usage)
Alert thresholds:
  - 50% actual spend
  - 80% actual spend
  - 100% forecasted spend
```

Replace `$300` with a realistic value once you have 30 days of
historical spend data from Cost Explorer.

## Per-execution cost estimate

For UC7 (genomics-pipeline) as an example:

```
Discovery Lambda     : 1 invoke × 512 MB × 2 s = $0.0000166
Summary Lambda       : N invokes × 512 MB × 5 s = $0.0000417 per file
Comprehend Medical   : $0.0005 per 100 chars
Bedrock Nova Lite    : ~$0.00006 per 1K input tokens + $0.00024 per 1K output tokens
Athena query         : $5 per TB scanned (typically $0.001-0.01 per run)
S3 PUT               : $0.005 per 1000 requests
S3 storage           : $0.025 per GB-month
```

For a 100-file batch run, end-to-end cost is typically $1-3 depending
on file size and Bedrock token usage.

## Monthly cost review cadence

- **Week 1 Monday**: Review previous month's Cost Explorer report
- Actions:
  - Compare UC costs against baseline.
  - Flag any UC exceeding baseline by 2× for investigation.
  - Rotate AWS Support case history if any resource failure correlates
    with a cost spike.
  - Update this runbook's baseline table if the new value is the new
    normal (not a one-off incident).
