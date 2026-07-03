# SAP/ERP Adjacent File Workflow Pattern

🌐 **Language / 言語**: [日本語](README.md) | English | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

Serverless pattern for processing SAP IDoc exports, HULFT landing files, EDI landing zone files, and batch job outputs stored on FSx for ONTAP — accessed via S3 Access Points.

## Use Cases

> **Scope note**: This pattern is intended for SAP/ERP-adjacent file landing zones such as IDoc exports, EDI files, HULFT transfers, audit extracts, and batch outputs. It is not intended to replace certified SAP integration mechanisms or transactional ERP interfaces. For SAP-certified storage integration, refer to [AWS SAP on FSx for ONTAP documentation](https://docs.aws.amazon.com/sap/latest/sap-hana/sap-hana-amazon-fsx.html).

- **SAP IDoc Export Processing**: Parse and summarize IDoc flat files (ORDERS, INVOIC, DESADV)
- **HULFT File Landing**: Process files transferred by HULFT/DataSpider to FSx for ONTAP
- **EDI Inbound Processing**: Handle EDI X12/EDIFACT documents in landing zones
- **Batch Job Output**: Analyze outputs from mainframe batch jobs, JCL outputs, or scheduled reports
- **ERP Data Extract**: Process CSV/XML extracts from SAP, Oracle EBS, or other ERP systems

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  ┌──────────────┐     ┌──────────────────────────────────────────┐ │
│  │  EventBridge │     │         Step Functions Workflow           │ │
│  │  Scheduler   │────▶│                                          │ │
│  │              │     │  ┌──────────┐  ┌──────────┐  ┌────────┐ │ │
│  │ rate(1 hour) │     │  │Discovery │─▶│Processing│─▶│ Report │ │ │
│  └──────────────┘     │  │ Lambda   │  │ Lambda   │  │ Lambda │ │ │
│                       │  └────┬─────┘  └────┬─────┘  └───┬────┘ │ │
│                       └───────┼─────────────┼─────────────┼──────┘ │
│                               │             │             │        │
│                               ▼             ▼             ▼        │
│                       ┌──────────────┐ ┌─────────┐  ┌─────────┐   │
│                       │ FSx for ONTAP│ │ Amazon  │  │  Amazon │   │
│                       │ via S3 AP    │ │ Bedrock │  │   SNS   │   │
│                       │              │ │ (Nova)  │  │         │   │
│                       │ ListObjectsV2│ │Summarize│  │ Email   │   │
│                       │ GetObject    │ │Classify │  │ Notify  │   │
│                       └──────────────┘ └─────────┘  └─────────┘   │
│                                              │                     │
│                                              ▼                     │
│                                        ┌──────────┐                │
│                                        │ S3 Output│                │
│                                        │  Bucket  │                │
│                                        └──────────┘                │
└─────────────────────────────────────────────────────────────────────┘
```

## Workflow Steps

1. **Discovery** — Lists files on FSx for ONTAP via S3 Access Point (`ListObjectsV2`), filtered by prefix
2. **Processing** — For each file: reads content via S3 AP (`GetObject`), sends to Amazon Bedrock for summarization/classification
3. **Report** — Generates execution summary, writes to S3, sends SNS notification

## Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `S3AccessPointAlias` | S3 AP alias for FSx for ONTAP volume | (required) |
| `OntapSecretArn` | Secrets Manager ARN for ONTAP credentials | (required) |
| `ScheduleExpression` | How often to run | `rate(1 hour)` |
| `OutputBucketName` | S3 bucket for results | (required) |
| `NotificationEmail` | Email for SNS alerts | (required) |
| `FilePrefix` | Directory prefix to scan | `idoc-export/` |
| `BedrockModelId` | Bedrock model for summarization | `amazon.nova-pro-v1:0` |
| `MaxFilesPerExecution` | Max files per run | `100` |

## Deployment

```bash
# Prerequisite: AWS SAM CLI is required. sam build automatically packages the code and shared layers.
sam build
sam deploy --guided --stack-name fsxn-s3ap-sap-erp \
  --parameter-overrides \
    S3AccessPointAlias=my-sap-s3ap-alias \
    OntapSecretArn=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:my-secret \
    OutputBucketName=my-sap-output-bucket \
    NotificationEmail=ops-team@example.com \
    FilePrefix="idoc-export/" \
    ScheduleExpression="cron(0 */2 * * ? *)"
```

> **Note**: `template.yaml` is used with the SAM CLI (`sam build` + `sam deploy`).
> To deploy directly with the `aws cloudformation deploy` command, use `template-deploy.yaml` (which requires pre-packaging the Lambda zip files and uploading them to S3).

## Customization

### Change the file prefix for different landing zones:

- SAP IDoc: `FilePrefix=idoc-export/`
- HULFT: `FilePrefix=hulft-landing/`
- EDI: `FilePrefix=edi-inbound/`
- Batch: `FilePrefix=batch-output/`

### Adjust Bedrock prompt:

Edit `functions/processing/index.py` to customize the summarization prompt for your document types.

## Related

- [Enterprise Workload Examples](../docs/enterprise-workload-examples.md) — Full list of enterprise patterns
- [Quick Start Guide](../docs/quick-start.md) — First deployment walkthrough
- [Deployment Profiles](../docs/deployment-profiles.md) — Production configuration options

---

## Cost Estimate (Monthly Approximation)

> **Note**: The following is an approximation for the ap-northeast-1 region; actual costs vary with usage. Check the latest pricing with the [AWS Pricing Calculator](https://calculator.aws/).

### Serverless Components (Pay-as-you-go)

| Service | Unit Price | Assumed Usage | Monthly Approximation |
|---------|------|-----------|---------|
| Lambda | $0.0000166667/GB-sec | 3 functions × 100 files/day | ~$1-5 |
| S3 API (GetObject/ListObjects) | $0.0047/10K requests | ~10K requests/day | ~$1.5 |
| Step Functions | $0.025/1K state transitions | ~1K transitions/day | ~$0.75 |
| Bedrock (Nova Lite) | $0.00006/1K input tokens | ~50K tokens/execution | ~$3-10 |
| Athena | $5/TB scanned | N/A | ~$0.5-2 |
| SNS | $0.50/100K notifications | ~100 notifications/day | ~$0.15 |
| CloudWatch Logs | $0.76/GB ingested | ~1 GB/month | ~$0.76 |

### Fixed Cost (FSx for ONTAP — assumes existing environment)

| Component | Monthly |
|--------------|------|
| FSx for ONTAP (128 MBps, 1 TB) | ~$230 (shared with existing environment) |
| S3 Access Point | No additional charge (S3 API charges only) |

### Total Approximation

| Configuration | Monthly Approximation |
|------|---------|
| Minimal configuration (once daily) | ~$5-15 |
| Standard configuration (hourly) | ~$15-50 |
| Large-scale configuration (high frequency + alarms) | ~$50-150 |

> **Governance Caveat**: Cost estimates are approximations, not guaranteed values. Actual charges vary with usage patterns, data volume, and region.

---

## Local Testing

### Prerequisites Check

```bash
# Check prerequisites
aws --version          # AWS CLI v2
sam --version          # SAM CLI
python3 --version      # Python 3.9+
docker --version       # Docker (for sam local)
aws sts get-caller-identity  # AWS credentials
```

### sam local invoke

```bash
# Build
# Prerequisite: AWS SAM CLI is required. sam build automatically packages the code and shared layers.
sam build

# Run Discovery Lambda locally
sam local invoke DiscoveryFunction --event events/discovery-event.json

# With environment variable overrides
sam local invoke DiscoveryFunction \
  --event events/discovery-event.json \
  --env-vars env.json
```

### Unit Tests

```bash
python3 -m pytest tests/ -v
```

For details, see the [Local Testing Quick Start](../docs/local-testing-quick-start.md).

---

## Output Sample

Example output of the SAP/ERP file processing workflow:

```json
{
  "discovery": {
    "status": "completed",
    "object_count": 15,
    "prefix": "idoc-export/",
    "categories": {"sap_idoc": 8, "hulft_transfer": 4, "data_extract": 3}
  },
  "processing": [
    {
      "key": "idoc-export/ORDERS_20260523_001.idoc",
      "status": "completed",
      "category": "sap_idoc",
      "summary": "Sales order IDoc (ORDERS05). Business partner: Sample Corporation, order number: PO-2026-001, amount: 2,500,000 JPY",
      "document_type": "ORDERS05",
      "key_fields": ["BELNR", "KUNNR", "NETWR", "WAERK"]
    }
  ],
  "report": {
    "total_files": 15,
    "succeeded": 14,
    "failed": 1,
    "success_rate_pct": 93.3,
    "category_breakdown": {"sap_idoc": 8, "hulft_transfer": 4, "data_extract": 3},
    "report_key": "reports/sap-erp-summary-1716480000.json"
  }
}
```

> **Note**: The above is sample output; actual values vary with the environment and input data. Benchmark figures are a sizing reference, not a service limit.

---

## Governance Note

> This pattern provides technical architecture guidance. It is not legal, compliance, or regulatory advice. Organizations should consult qualified professionals.

---

## S3AP Compatibility

For compatibility constraints, troubleshooting, and trigger patterns for S3 Access Points for FSx for ONTAP, see the [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).
---

## Performance Considerations

- FSx for ONTAP throughput capacity is shared across NFS/SMB/S3AP
- Latency via the S3 Access Point incurs tens of milliseconds of overhead
- When processing large numbers of files, control the degree of parallelism with the Step Functions Map state MaxConcurrency
- Increasing the Lambda memory size also improves network bandwidth

> **Note**: The performance figures for this pattern are a sizing reference, not a service limit. Real-world performance varies with FSx for ONTAP throughput capacity, network configuration, and concurrent workloads.
