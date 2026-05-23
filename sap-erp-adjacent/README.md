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




---

## 出力サンプル (Output Sample)

SAP/ERP ファイル処理ワークフローの出力例:

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
      "summary": "受注 IDoc (ORDERS05)。取引先: 株式会社サンプル、注文番号: PO-2026-001、金額: 2,500,000 JPY",
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

> **注記**: 上記はサンプル出力であり、実際の値は環境・入力データにより異なります。ベンチマーク数値は sizing reference であり、service limit ではありません。

---

## Governance Note

> 本パターンは技術アーキテクチャガイダンスを提供します。法的・コンプライアンス・規制上の助言ではありません。組織は適格な専門家に相談してください。

---

## S3AP Compatibility

S3 Access Points for FSx for ONTAP の互換性制約、トラブルシューティング、トリガーパターンについては [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md) を参照してください。
---

## Performance Considerations

- FSx for ONTAP のスループットキャパシティは NFS/SMB/S3AP で共有されます
- S3 Access Point 経由のレイテンシは数十ミリ秒のオーバーヘッドが発生します
- 大量ファイル処理時は Step Functions Map state の MaxConcurrency で並列度を制御してください
- Lambda メモリサイズの増加はネットワーク帯域幅の向上にも寄与します

> **注記**: 本パターンのパフォーマンス数値は sizing reference であり、service limit ではありません。実環境での性能は FSx ONTAP スループットキャパシティ、ネットワーク構成、同時実行ワークロードにより異なります。
