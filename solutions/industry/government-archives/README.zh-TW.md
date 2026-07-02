# UC16：政府機關 — 公文數位典藏·FOIA 因應

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | 繁體中文 | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)
📚 **文件**: [架構](docs/architecture.md) | [示範腳本](docs/demo-guide.md) | [疑難排解](../docs/phase7-troubleshooting.md)

## 概述

以 FSx for ONTAP S3 Access Points 為基礎的政府機關公文
數位典藏以及資訊公開請求（FOIA：Freedom of Information Act）
因應自動化管線。

## 使用情境

將政府機關持有的大量公文（PDF、掃描影像、電子郵件）
自動數位化、分類、遮蔽（編修），以快速因應資訊公開請求。

### 處理流程

```
FSx for ONTAP (公文儲存 — 依部門 NTFS ACL)
  → S3 Access Point
    → Step Functions 工作流程
      → Discovery：偵測新文件（PDF, TIFF, EML, MSG）
      → OCR：使用 Textract 進行文件數位化（ap-northeast-1 不支援，故跨區域）
      → Classification：使用 Comprehend 進行文件分類（機密等級判定）
      → EntityExtraction：PII 偵測（姓名、地址、SSN、電話號碼）
      → Redaction：機密資訊自動遮蔽（編修）
      → IndexGeneration：全文檢索索引生成（OpenSearch，可停用）
      → ComplianceCheck：保存期限·銷毀排程確認（NARA GRS）
```

### 目標資料

| 資料格式 | 說明 | 典型大小 |
|-----------|------|-----------|
| PDF | 公文、報告書、合約 | 100 KB – 50 MB |
| TIFF | 掃描文件 | 1 – 100 MB |
| EML / MSG | 電子郵件典藏 | 10 KB – 10 MB |
| DOCX / XLSX | Office 文件 | 50 KB – 20 MB |

### AWS 服務

| 服務 | 用途 |
|---------|------|
| FSx for ONTAP | 公文永續儲存（依部門 NTFS ACL） |
| S3 Access Points | 從無伺服器存取文件 |
| Step Functions | 工作流程協調 |
| Lambda | 文件分類、PII 偵測、遮蔽處理 |
| Amazon Textract ⚠️ | 文件 OCR（經由 us-east-1 跨區域） |
| Amazon Comprehend | 實體擷取、文件分類、PII 偵測 |
| Amazon Bedrock | 文件摘要、FOIA 回覆草稿生成 |
| Amazon Macie | 機密資料自動偵測 |
| DynamoDB | 文件中繼資料、處理狀態管理 |
| OpenSearch Serverless | 全文檢索索引（選用，預設停用） |
| SNS | FOIA 期限警示 |

### Public Sector 適用性

- **NARA（國家檔案與記錄管理局）合規**：符合電子記錄管理要求
- **FOIA 因應**：自動追蹤 20 個工作日內的回覆期限
- **FedRAMP High**：在 AWS GovCloud 上合規
- **Section 508**：無障礙支援（OCR + 替代文字生成）
- **Records Management**：保存期限·銷毀排程的自動管理

### FOIA 因應流程

```
FOIA 請求受理
  → 目標文件檢索（OpenSearch）
  → 相關文件的機密等級判定
  → 自動遮蔽（PII、國家安全資訊）
  → 通知審閱負責人
  → 回覆期限追蹤（20 個工作日）
  → 公開文件套件生成
```

## 已驗證的畫面（螢幕截圖）

### 1. 公文儲存（經由 S3 Access Point）

資訊公開請求受理後，目標文件會儲存於 `archives/YYYY/MM/` 前綴下。

<!-- SCREENSHOT: phase7-uc16-s3-archives-uploaded.png
     內容：S3 AP 的 archives/ 前綴下的 PDF 文件清單
     遮罩：帳戶 ID、S3 AP ARN、文件名 -->
![UC16：公文儲存確認](../docs/screenshots/masked/phase7/phase7-uc16-s3-archives-uploaded.png)

### 2. 遮蔽文件的檢視

處理完成後儲存於 `redacted/` 前綴的文字中，PII 已被替換為
`[REDACTED]` 標記。**一般職員在公開前進行審閱的畫面。**

<!-- SCREENSHOT: phase7-uc16-redacted-text-preview.png
     內容：S3 主控台中的 redacted 文字預覽，[REDACTED] 標記可見
     遮罩：帳戶 ID、遮蔽目標文件名（僅顯示範例名） -->
![UC16：遮蔽文件預覽](../docs/screenshots/masked/phase7/phase7-uc16-redacted-text-preview.png)

### 3. 遮蔽中繼資料（sidecar JSON）

用於稽核的 sidecar 資料。不保存原文 PII，僅保存 SHA-256 雜湊。
記錄位移、實體類型（NAME / EMAIL / SSN 等）與信賴度。

<!-- SCREENSHOT: phase7-uc16-redaction-metadata-json.png
     內容：redaction-metadata/*.json 的格式化檢視
     遮罩：帳戶 ID、原文件名 -->
![UC16：遮蔽中繼資料 JSON](../docs/screenshots/masked/phase7/phase7-uc16-redaction-metadata-json.png)

### 4. FOIA 期限提醒（SNS 郵件通知）

FOIA 負責人在期限前 3 個工作日收到的提醒郵件。
逾期時會發送 severity=HIGH 的 OVERDUE 通知。

<!-- SCREENSHOT: phase7-uc16-foia-reminder-email.png
     內容：在郵件用戶端中顯示 FOIA_DEADLINE_APPROACHING 郵件
     遮罩：收件者·寄件者郵件、request_id（僅顯示範例 ID） -->
![UC16：FOIA 期限提醒郵件](../docs/screenshots/masked/phase7/phase7-uc16-foia-reminder-email.png)

### 5. NARA GRS 保存排程（DynamoDB Explorer）

`fsxn-uc16-demo-retention` 資料表。每份文件都記錄 NARA GRS 代碼
（GRS 2.1 / 2.2 / 1.1）與保存年數（3 / 7 / 30 年）、預定銷毀日期。

<!-- SCREENSHOT: phase7-uc16-dynamodb-retention.png
     內容：在 DynamoDB Explorer 中的 retention 資料表項目清單
     遮罩：帳戶 ID、document_key（僅範例名） -->
![UC16：保存排程資料表](../docs/screenshots/masked/phase7/phase7-uc16-dynamodb-retention.png)


## Success Metrics

### Outcome
透過公文典藏·FOIA 因應（OCR·分類·遮蔽·保存期限管理）的自動化，加快資訊公開請求的因應。

### Metrics
| 指標 | 目標值（範例） |
|-----------|------------|
| 已處理文件數 / 執行 | > 500 documents |
| OCR 文字擷取成功率 | > 95% |
| PII 偵測精度 | > 95% |
| 遮蔽處理時間 / 文件 | < 30 秒 |
| FOIA 因應時間縮短 | > 50% |
| Human Review 必需率 | 100%（遮蔽結果需全件人工確認） |

> **100% Human Review 的理由**：由於遮蔽遺漏會直接影響資訊公開與個人資訊保護，因此必須對全件進行人工確認。

### Measurement Method
Step Functions 執行歷程、Comprehend PII 偵測結果、遮蔽前後 diff、DynamoDB 保存期限歷程、CloudWatch Metrics。審閱結果記錄至 DynamoDB，以便在稽核時可追蹤「誰·何時·確認·核准了什麼」。

### Sample Run Results (實測範例)

**環境**：FSx for ONTAP Single-AZ, 128 MBps, ap-northeast-1, S3AP Internet Origin

| 指標 | Before (手動) | After (S3AP 自動化) |
|------|-------------|-------------------|
| FOIA 因應時間 | 數天~數週 | 389 ms (10 docs, sequential) |
| 文件偵測 | 手動檢索 | 32 ms (10 documents) |
| 檔案讀取 | 個別存取 | avg 36 ms / document |
| 遮蔽品質 | 依賴負責人，存在不一致 | Comprehend PII 偵測 + 自動遮蔽 |
| Human Review | 無 or 不定期 | 100%（全件需人工確認） |
| 稽核軌跡 | 個人記錄 | DynamoDB (who/when/what) + S3 Object Lock |
| 保存期限管理 | 手動 | 自動追蹤 + 警示 |

> **備註**：UC16 的 sample run 是使用合成或非敏感範例文件進行的驗證，不代表實際的行政文件或生產資料。本 sample run 僅驗證處理路徑。遮蔽品質、Human Review 的完整性、稽核軌跡評估請在客戶特定的 PoC 中另行實施。

## 部署

### 事前驗證

```bash
bash scripts/verify_phase7_prerequisites.sh
```

### 一鍵部署

```bash
bash scripts/deploy_phase7.sh government-archives
```

### 手動部署

```bash
# 前提：需要 AWS SAM CLI。sam build 會自動打包程式碼與共用層。
sam build

sam deploy \
  --stack-name fsxn-gov-archives \
  --parameter-overrides \
    S3AccessPointAlias=<alias> \
    S3AccessPointName=<name> \
    OpenSearchMode=none \
    CrossRegion=us-east-1 \
    UseCrossRegion=true \
    OntapSecretName=<secret> \
    OntapManagementIp=<ip> \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3
```

### OpenSearch 模式

| 模式 | 用途 | 每月成本（估算） |
|--------|------|-------------------|
| `none` | 驗證·低成本運行（預設） | $0 |
| `serverless` | 可變工作負載，按量計費 | $350 – $700 |
| `managed` | 固定工作負載，價格低 | $35 – $100 |

## 目錄結構

```
government-archives/
├── template.yaml
├── template-deploy.yaml
├── functions/
│   ├── discovery/handler.py
│   ├── ocr/handler.py                # 跨區域 Textract
│   ├── classification/handler.py
│   ├── entity_extraction/handler.py
│   ├── redaction/handler.py
│   ├── index_generation/handler.py
│   ├── compliance_check/handler.py   # NARA GRS 保存期限
│   └── foia_deadline_reminder/handler.py  # 20 個工作日追蹤
├── tests/                            # 52 pytest (含 Hypothesis)
└── README.md
```


---

## AWS 文件連結

| 服務 | 文件 |
|---------|------------|
| FSx for ONTAP | [使用者指南](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/what-is-fsx-ontap.html) |
| S3 Access Points | [S3 AP for FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html) |
| Step Functions | [開發人員指南](https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html) |
| Amazon Textract | [開發人員指南](https://docs.aws.amazon.com/textract/latest/dg/what-is.html) |
| Amazon Comprehend | [開發人員指南](https://docs.aws.amazon.com/comprehend/latest/dg/what-is.html) |
| Amazon Macie | [使用者指南](https://docs.aws.amazon.com/macie/latest/user/what-is-macie.html) |
| Amazon OpenSearch | [開發人員指南](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/what-is.html) |

### Well-Architected Framework 對應

| 支柱 | 對應 |
|----|------|
| 卓越營運 | X-Ray、EMF、FOIA 截止期限追蹤、52+ 測試 |
| 安全性 | PII 編修、SHA-256 稽核 sidecar、Macie、100% Human Review |
| 可靠性 | Step Functions Retry/Catch、跨區域 OCR、resilience 測試 |
| 效能效率 | 並行 PII 偵測、OpenSearch 索引、批次處理 |
| 成本最佳化 | 無伺服器、OpenSearch Serverless、條件式索引 |
| 永續性 | NARA GRS 合規、保存期限管理、自動銷毀排程 |





---

## 成本估算（每月概算）

> **備註**：以下為 ap-northeast-1 區域的概算，實際成本因使用量而異。最新價格請於 [AWS Pricing Calculator](https://calculator.aws/) 確認。

### 無伺服器元件（按量計費）

| 服務 | 單價 | 預估使用量 | 每月概算 |
|---------|------|-----------|---------|
| Lambda | $0.0000166667/GB-sec | 8 函式 × 100 docs/日 | ~$1-5 |
| S3 API (GetObject/ListObjects) | $0.0047/10K requests | ~10K requests/日 | ~$1.5 |
| Step Functions | $0.025/1K state transitions | ~1K transitions/日 | ~$0.75 |
| Bedrock (Nova Lite) | $0.00006/1K input tokens | ~80K tokens/執行 | ~$3-10 |
| Athena | $5/TB scanned | ~50 MB/查詢 | ~$0.5-2 |
| SNS | $0.50/100K notifications | ~100 notifications/日 | ~$0.15 |
| CloudWatch Logs | $0.76/GB ingested | ~1 GB/月 | ~$0.76 |
| OpenSearch Serverless | $0.24/OCU-hour |


### 固定成本（FSx for ONTAP — 以現有環境為前提）

| 元件 | 每月 |
|--------------|------|
| FSx for ONTAP (128 MBps, 1 TB) | ~$230 (共用現有環境) |
| S3 Access Point | 無額外費用（僅 S3 API 費用） |

### 合計概算

| 組態 | 每月概算 |
|------|---------|
| 最小組態（每天執行 1 次） | ~$5-15 |
| 標準組態（每小時執行） | ~$15-50 |
| 大規模組態（高頻率 + 警示） | ~$50-150 |

> **Governance Caveat**：成本估算為概算，非保證值。實際帳單因使用模式、資料量、區域而異。

---

## 本機測試

### Prerequisites 檢查

```bash
# 確認前提條件
aws --version          # AWS CLI v2
sam --version          # SAM CLI
python3 --version      # Python 3.9+
docker --version       # Docker (sam local 用)
aws sts get-caller-identity  # AWS 認證資訊
```

### sam local invoke

```bash
# 建置
# 前提：需要 AWS SAM CLI。sam build 會自動打包程式碼與共用層。
sam build

# Discovery Lambda 的本機執行
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

公文典藏·FOIA 處理的輸出範例：

```json
{
  "discovery": {
    "status": "completed",
    "object_count": 25,
    "prefix": "archives/incoming/"
  },
  "classification": [
    {
      "key": "archives/incoming/memo-2026-001.pdf",
      "record_type": "memorandum",
      "retention_schedule": "GRS 5.2 - 7 years",
      "sensitivity": "CUI",
      "pii_detected": true
    }
  ],
  "redaction": {
    "total_redacted": 25,
    "pii_fields_removed": 89,
    "redaction_types": {"name": 34, "ssn": 12, "address": 28, "phone": 15},
    "audit_hash": "sha256:d4e5f6..."
  },
  "foia_tracking": {
    "request_id": "FOIA-2026-0042",
    "deadline_date": "2026-06-12",
    "business_days_remaining": 15,
    "status": "IN_PROCESSING"
  },
  "search_index": {
    "documents_indexed": 25,
    "opensearch_collection": "gov-archives-collection"
  }
}
```

> **備註**：以上為範例輸出，實際值因環境·輸入資料而異。基準數值為 sizing reference，而非 service limit。

---

## Governance Note

> 本模式提供技術架構指引。並非法律·合規·法規方面的建議。組織應諮詢具備資格的專業人士。

---

## S3AP Compatibility

關於 S3 Access Points for FSx for ONTAP 的相容性限制、疑難排解、觸發模式，請參閱 [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md)。
