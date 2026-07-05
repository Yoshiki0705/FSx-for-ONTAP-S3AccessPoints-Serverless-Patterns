# SAP/ERP Adjacent File Workflow Pattern

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | 简体中文 | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

用于处理存储在 FSx for ONTAP 上并通过 S3 Access Points 访问的 SAP IDoc 导出文件、HULFT 落地文件、EDI 落地区文件和批处理作业输出的无服务器模式。

## Use Cases

> **Scope note**: 此模式面向 SAP/ERP 相邻的文件落地区，例如 IDoc 导出、EDI 文件、HULFT 传输、审计提取和批处理输出。它并非用于替代经过认证的 SAP 集成机制或事务型 ERP 接口。有关 SAP 认证的存储集成，请参阅 [AWS SAP on FSx for ONTAP documentation](https://docs.aws.amazon.com/sap/latest/sap-hana/sap-hana-amazon-fsx.html)。

- **SAP IDoc 导出处理**：解析并汇总 IDoc 平面文件（ORDERS、INVOIC、DESADV）
- **HULFT 文件落地**：处理由 HULFT/DataSpider 传输到 FSx for ONTAP 的文件
- **EDI 入站处理**：处理落地区中的 EDI X12/EDIFACT 文档
- **批处理作业输出**：分析来自大型机批处理作业、JCL 输出或计划报表的输出
- **ERP 数据提取**：处理来自 SAP、Oracle EBS 或其他 ERP 系统的 CSV/XML 提取文件

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

1. **Discovery** — 通过 S3 Access Point 列出 FSx for ONTAP 上的文件（`ListObjectsV2`），并按前缀过滤
2. **Processing** — 对每个文件：通过 S3 AP 读取内容（`GetObject`），发送到 Amazon Bedrock 进行汇总/分类
3. **Report** — 生成执行摘要，写入 S3，并发送 SNS 通知

## Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `S3AccessPointAlias` | FSx for ONTAP 卷的 S3 AP 别名 | (必填) |
| `OntapSecretArn` | ONTAP 凭证的 Secrets Manager ARN | (必填) |
| `ScheduleExpression` | 运行频率 | `rate(1 hour)` |
| `OutputBucketName` | 用于存放结果的 S3 存储桶 | (必填) |
| `NotificationEmail` | SNS 告警的电子邮件 | (必填) |
| `FilePrefix` | 要扫描的目录前缀 | `idoc-export/` |
| `BedrockModelId` | 用于汇总的 Bedrock 模型 | `apac.amazon.nova-pro-v1:0` |
| `MaxFilesPerExecution` | 每次运行的最大文件数 | `100` |

## Deployment

```bash
# 前提条件：需要 AWS SAM CLI。sam build 会自动打包代码和共享层。
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

> **注意**：`template.yaml` 与 SAM CLI（`sam build` + `sam deploy`）配合使用。
> 若要使用 `aws cloudformation deploy` 命令直接部署，请使用 `template-deploy.yaml`（需要预先打包 Lambda zip 文件并上传到 S3）。

## Customization

### Change the file prefix for different landing zones:

- SAP IDoc: `FilePrefix=idoc-export/`
- HULFT: `FilePrefix=hulft-landing/`
- EDI: `FilePrefix=edi-inbound/`
- Batch: `FilePrefix=batch-output/`

### Adjust Bedrock prompt:

编辑 `functions/processing/index.py`，以针对您的文档类型自定义汇总提示词。

## Related

- [Enterprise Workload Examples](../docs/enterprise-workload-examples.md) — 企业模式完整列表
- [Quick Start Guide](../docs/quick-start.md) — 首次部署演练
- [Deployment Profiles](../docs/deployment-profiles.md) — 生产配置选项

---

## 成本估算（每月概算）

> **注**：以下为 ap-northeast-1 区域的概算，实际成本因使用量而异。请在 [AWS Pricing Calculator](https://calculator.aws/) 查看最新价格。

### 无服务器组件（按量计费）

| 服务 | 单价 | 预计使用量 | 每月概算 |
|---------|------|-----------|---------|
| Lambda | $0.0000166667/GB-sec | 3 个函数 × 100 files/天 | ~$1-5 |
| S3 API (GetObject/ListObjects) | $0.0047/10K requests | ~10K requests/天 | ~$1.5 |
| Step Functions | $0.025/1K state transitions | ~1K transitions/天 | ~$0.75 |
| Bedrock (Nova Lite) | $0.00006/1K input tokens | ~50K tokens/次执行 | ~$3-10 |
| Athena | $5/TB scanned | N/A | ~$0.5-2 |
| SNS | $0.50/100K notifications | ~100 notifications/天 | ~$0.15 |
| CloudWatch Logs | $0.76/GB ingested | ~1 GB/月 | ~$0.76 |

### 固定成本（FSx for ONTAP — 假设为既有环境）

| 组件 | 每月 |
|--------------|------|
| FSx for ONTAP (128 MBps, 1 TB) | ~$230 (与既有环境共享) |
| S3 Access Point | 无额外费用（仅 S3 API 费用） |

### 合计概算

| 配置 | 每月概算 |
|------|---------|
| 最小配置（每日运行 1 次） | ~$5-15 |
| 标准配置（每小时运行） | ~$15-50 |
| 大规模配置（高频率 + 告警） | ~$50-150 |

> **Governance Caveat**: 成本估算为概算，并非保证值。实际账单金额因使用模式、数据量和区域而异。

---

## 本地测试

### Prerequisites 检查

```bash
# 检查前提条件
aws --version          # AWS CLI v2
sam --version          # SAM CLI
python3 --version      # Python 3.9+
docker --version       # Docker (用于 sam local)
aws sts get-caller-identity  # AWS 凭证
```

### sam local invoke

```bash
# 构建
# 前提条件：需要 AWS SAM CLI。sam build 会自动打包代码和共享层。
sam build

# 本地运行 Discovery Lambda
sam local invoke DiscoveryFunction --event events/discovery-event.json

# 带环境变量覆盖
sam local invoke DiscoveryFunction \
  --event events/discovery-event.json \
  --env-vars env.json
```

### 单元测试

```bash
python3 -m pytest tests/ -v
```

详情请参阅 [本地测试快速入门](../docs/local-testing-quick-start.md)。

---

## 输出示例 (Output Sample)

SAP/ERP 文件处理工作流的输出示例：

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
      "summary": "销售订单 IDoc (ORDERS05)。业务伙伴: Sample Corporation, 订单号: PO-2026-001, 金额: 2,500,000 JPY",
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

> **注**：以上为示例输出，实际值因环境和输入数据而异。基准数值为 sizing reference，并非 service limit。

---

## Governance Note

> 本模式提供技术架构指导，并非法律、合规或监管方面的建议。组织应咨询合格的专业人士。

---

## S3AP Compatibility

有关 S3 Access Points for FSx for ONTAP 的兼容性约束、故障排查和触发模式，请参阅 [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md)。
---

## Performance Considerations

- FSx for ONTAP 的吞吐容量由 NFS/SMB/S3AP 共享
- 经由 S3 Access Point 的延迟会产生数十毫秒的开销
- 处理大量文件时，请使用 Step Functions Map state 的 MaxConcurrency 控制并行度
- 增大 Lambda 内存大小也有助于提升网络带宽

> **注**：本模式的性能数值为 sizing reference，并非 service limit。实际环境中的性能因 FSx for ONTAP 吞吐容量、网络配置和并发工作负载而异。
