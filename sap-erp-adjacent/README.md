# SAP/ERP Adjacent File Workflow Pattern

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
