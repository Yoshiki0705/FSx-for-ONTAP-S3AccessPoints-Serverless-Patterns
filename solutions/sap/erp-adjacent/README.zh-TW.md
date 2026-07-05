# SAP/ERP Adjacent File Workflow Pattern

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | 繁體中文 | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

用於處理儲存在 FSx for ONTAP 上並透過 S3 Access Points 存取的 SAP IDoc 匯出檔案、HULFT 落地檔案、EDI 落地區檔案和批次作業輸出的無伺服器模式。

## Use Cases

> **Scope note**: 此模式適用於 SAP/ERP 相鄰的檔案落地區，例如 IDoc 匯出、EDI 檔案、HULFT 傳輸、稽核擷取和批次輸出。它並非用於取代經過認證的 SAP 整合機制或交易型 ERP 介面。有關 SAP 認證的儲存整合，請參閱 [AWS SAP on FSx for ONTAP documentation](https://docs.aws.amazon.com/sap/latest/sap-hana/sap-hana-amazon-fsx.html)。

- **SAP IDoc 匯出處理**：解析並彙總 IDoc 平面檔案（ORDERS、INVOIC、DESADV）
- **HULFT 檔案落地**：處理由 HULFT/DataSpider 傳輸到 FSx for ONTAP 的檔案
- **EDI 入站處理**：處理落地區中的 EDI X12/EDIFACT 文件
- **批次作業輸出**：分析來自大型主機批次作業、JCL 輸出或排程報表的輸出
- **ERP 資料擷取**：處理來自 SAP、Oracle EBS 或其他 ERP 系統的 CSV/XML 擷取檔案

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

1. **Discovery** — 透過 S3 Access Point 列出 FSx for ONTAP 上的檔案（`ListObjectsV2`），並依前綴篩選
2. **Processing** — 對每個檔案：透過 S3 AP 讀取內容（`GetObject`），傳送到 Amazon Bedrock 進行彙總/分類
3. **Report** — 產生執行摘要，寫入 S3，並傳送 SNS 通知

## Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `S3AccessPointAlias` | FSx for ONTAP 磁碟區的 S3 AP 別名 | (必填) |
| `OntapSecretArn` | ONTAP 憑證的 Secrets Manager ARN | (必填) |
| `ScheduleExpression` | 執行頻率 | `rate(1 hour)` |
| `OutputBucketName` | 用於存放結果的 S3 儲存貯體 | (必填) |
| `NotificationEmail` | SNS 警示的電子郵件 | (必填) |
| `FilePrefix` | 要掃描的目錄前綴 | `idoc-export/` |
| `BedrockModelId` | 用於彙總的 Bedrock 模型 | `apac.amazon.nova-pro-v1:0` |
| `MaxFilesPerExecution` | 每次執行的最大檔案數 | `100` |

## Deployment

```bash
# 前提條件：需要 AWS SAM CLI。sam build 會自動打包程式碼與共用層。
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

> **注意**：`template.yaml` 與 SAM CLI（`sam build` + `sam deploy`）搭配使用。
> 若要使用 `aws cloudformation deploy` 命令直接部署，請使用 `template-deploy.yaml`（需要預先打包 Lambda zip 檔案並上傳到 S3）。

## Customization

### Change the file prefix for different landing zones:

- SAP IDoc: `FilePrefix=idoc-export/`
- HULFT: `FilePrefix=hulft-landing/`
- EDI: `FilePrefix=edi-inbound/`
- Batch: `FilePrefix=batch-output/`

### Adjust Bedrock prompt:

編輯 `functions/processing/index.py`，以針對您的文件類型自訂彙總提示詞。

## Related

- [Enterprise Workload Examples](../docs/enterprise-workload-examples.md) — 企業模式完整清單
- [Quick Start Guide](../docs/quick-start.md) — 首次部署逐步導覽
- [Deployment Profiles](../docs/deployment-profiles.md) — 生產配置選項

---

## 成本估算（每月概算）

> **注**：以下為 ap-northeast-1 區域的概算，實際成本因使用量而異。請在 [AWS Pricing Calculator](https://calculator.aws/) 查看最新價格。

### 無伺服器元件（按量計費）

| 服務 | 單價 | 預計使用量 | 每月概算 |
|---------|------|-----------|---------|
| Lambda | $0.0000166667/GB-sec | 3 個函式 × 100 files/日 | ~$1-5 |
| S3 API (GetObject/ListObjects) | $0.0047/10K requests | ~10K requests/日 | ~$1.5 |
| Step Functions | $0.025/1K state transitions | ~1K transitions/日 | ~$0.75 |
| Bedrock (Nova Lite) | $0.00006/1K input tokens | ~50K tokens/次執行 | ~$3-10 |
| Athena | $5/TB scanned | N/A | ~$0.5-2 |
| SNS | $0.50/100K notifications | ~100 notifications/日 | ~$0.15 |
| CloudWatch Logs | $0.76/GB ingested | ~1 GB/月 | ~$0.76 |

### 固定成本（FSx for ONTAP — 假設為既有環境）

| 元件 | 每月 |
|--------------|------|
| FSx for ONTAP (128 MBps, 1 TB) | ~$230 (與既有環境共用) |
| S3 Access Point | 無額外費用（僅 S3 API 費用） |

### 合計概算

| 配置 | 每月概算 |
|------|---------|
| 最小配置（每日執行 1 次） | ~$5-15 |
| 標準配置（每小時執行） | ~$15-50 |
| 大規模配置（高頻率 + 警示） | ~$50-150 |

> **Governance Caveat**: 成本估算為概算，並非保證值。實際帳單金額因使用模式、資料量和區域而異。

---

## 本機測試

### Prerequisites 檢查

```bash
# 檢查前提條件
aws --version          # AWS CLI v2
sam --version          # SAM CLI
python3 --version      # Python 3.9+
docker --version       # Docker (用於 sam local)
aws sts get-caller-identity  # AWS 憑證
```

### sam local invoke

```bash
# 建置
# 前提條件：需要 AWS SAM CLI。sam build 會自動打包程式碼與共用層。
sam build

# 本機執行 Discovery Lambda
sam local invoke DiscoveryFunction --event events/discovery-event.json

# 帶環境變數覆寫
sam local invoke DiscoveryFunction \
  --event events/discovery-event.json \
  --env-vars env.json
```

### 單元測試

```bash
python3 -m pytest tests/ -v
```

詳情請參閱 [本機測試快速入門](../docs/local-testing-quick-start.md)。

---

## 輸出範例 (Output Sample)

SAP/ERP 檔案處理工作流程的輸出範例：

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
      "summary": "銷售訂單 IDoc (ORDERS05)。業務夥伴: Sample Corporation, 訂單號: PO-2026-001, 金額: 2,500,000 JPY",
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

> **注**：以上為範例輸出，實際值因環境和輸入資料而異。基準數值為 sizing reference，並非 service limit。

---

## Governance Note

> 本模式提供技術架構指引，並非法律、合規或法規方面的建議。組織應諮詢合格的專業人士。

---

## S3AP Compatibility

有關 S3 Access Points for FSx for ONTAP 的相容性限制、疑難排解和觸發模式，請參閱 [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md)。
---

## Performance Considerations

- FSx for ONTAP 的輸送量容量由 NFS/SMB/S3AP 共用
- 經由 S3 Access Point 的延遲會產生數十毫秒的額外負擔
- 處理大量檔案時，請使用 Step Functions Map state 的 MaxConcurrency 控制平行度
- 增加 Lambda 記憶體大小也有助於提升網路頻寬

> **注**：本模式的效能數值為 sizing reference，並非 service limit。實際環境中的效能因 FSx for ONTAP 輸送量容量、網路配置和並行工作負載而異。
