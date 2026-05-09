# UC2: 金融 / 保險 — 合約與發票自動處理 (IDP)

🌐 **Language / 言語**: [日本語](architecture.md) | [English](architecture.en.md) | [한국어](architecture.ko.md) | [简体中文](architecture.zh-CN.md) | 繁體中文 | [Français](architecture.fr.md) | [Deutsch](architecture.de.md) | [Español](architecture.es.md)

## 端對端架構 (輸入 → 輸出)

---

## 高層級流程

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FSx for NetApp ONTAP                                 │
│                                                                              │
│  /vol/documents/                                                             │
│  ├── 契約書/保険契約_2024-001.pdf    (スキャン PDF)                          │
│  ├── 請求書/invoice_20240315.tiff    (複合機スキャン)                        │
│  ├── 申込書/application_form.jpeg    (手書き申込書)                          │
│  └── 見積書/quotation_v2.pdf         (電子 PDF)                             │
│                                                                              │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                      S3 Access Point (Data Path)                              │
│                                                                              │
│  Alias: fsxn-idp-vol-ext-s3alias                                             │
│  • ListObjectsV2 (document discovery)                                        │
│  • GetObject (PDF/TIFF/JPEG retrieval)                                       │
│  • No NFS/SMB mount required from Lambda                                     │
│                                                                              │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                    EventBridge Scheduler (Trigger)                            │
│                                                                              │
│  Schedule: rate(1 hour) — configurable                                       │
│  Target: Step Functions State Machine                                        │
│                                                                              │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                    AWS Step Functions (Orchestration)                         │
│                                                                              │
│  ┌─────────────┐    ┌──────────────────────┐    ┌────────────────┐          │
│  │  Discovery   │───▶│  OCR                 │───▶│Entity Extraction│         │
│  │  Lambda      │    │  Lambda              │    │ Lambda         │          │
│  │             │    │                      │    │               │          │
│  │  • VPC内     │    │  • Textract sync/    │    │  • Comprehend  │          │
│  │  • S3 AP List│    │    async API auto-   │    │  • Named Entity│          │
│  │  • PDF/TIFF  │    │    selection         │    │  • Date/Amount │          │
│  └─────────────┘    └──────────────────────┘    └───────┬────────┘          │
│                                                          │                   │
│                                                          ▼                   │
│                                                 ┌────────────────┐          │
│                                                 │    Summary      │          │
│                                                 │    Lambda       │          │
│                                                 │               │          │
│                                                 │ • Bedrock      │          │
│                                                 │ • JSON output  │          │
│                                                 └────────────────┘          │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                         Output (S3 Bucket)                                    │
│                                                                              │
│  s3://{stack}-output-{account}/                                              │
│  ├── ocr-text/YYYY/MM/DD/                                                    │
│  │   ├── 保険契約_2024-001.txt       ← OCR extracted text                   │
│  │   └── invoice_20240315.txt                                                │
│  ├── entities/YYYY/MM/DD/                                                    │
│  │   ├── 保険契約_2024-001.json      ← Extracted entities                   │
│  │   └── invoice_20240315.json                                               │
│  └── summaries/YYYY/MM/DD/                                                   │
│      ├── 保険契約_2024-001_summary.json  ← Structured summary               │
│      └── invoice_20240315_summary.json                                       │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Mermaid 圖表

```mermaid
flowchart TB
    subgraph INPUT["📥 輸入 — FSx for NetApp ONTAP"]
        DOCS["文件檔案<br/>.pdf, .tiff, .jpeg"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject"]
    end

    subgraph TRIGGER["⏰ 觸發器"]
        EB["EventBridge Scheduler<br/>rate(1 hour)"]
    end

    subgraph SFN["⚙️ Step Functions 工作流程"]
        DISC["1️⃣ Discovery Lambda<br/>• 在 VPC 內執行<br/>• S3 AP 檔案探索<br/>• .pdf/.tiff/.jpeg 過濾<br/>• 清單產生"]
        OCR["2️⃣ OCR Lambda<br/>• 透過 S3 AP 取得文件<br/>• 頁數判定<br/>• Textract sync API (≤1 頁)<br/>• Textract async API (>1 頁)<br/>• 文字擷取並輸出至 S3"]
        ENT["3️⃣ Entity Extraction Lambda<br/>• Amazon Comprehend 呼叫<br/>• 命名實體辨識<br/>• 日期、金額、組織、人物擷取<br/>• JSON 輸出至 S3"]
        SUM["4️⃣ Summary Lambda<br/>• Amazon Bedrock (Nova/Claude)<br/>• 結構化摘要產生<br/>• 合約條款、金額、當事方整理<br/>• JSON 輸出至 S3"]
    end

    subgraph OUTPUT["📤 輸出 — S3 Bucket"]
        TEXT["ocr-text/*.txt<br/>OCR 擷取文字"]
        ENTITIES["entities/*.json<br/>擷取的實體"]
        SUMMARY["summaries/*.json<br/>結構化摘要"]
    end

    subgraph NOTIFY["📧 通知"]
        SNS["Amazon SNS<br/>Email / Slack"]
    end

    DOCS --> ALIAS
    ALIAS --> DISC
    EB --> SFN
    DISC --> OCR
    OCR --> ENT
    ENT --> SUM
    OCR --> TEXT
    ENT --> ENTITIES
    SUM --> SUMMARY
    SUM --> SNS
```

---

## 資料流詳情

### 輸入
| 項目 | 說明 |
|------|------|
| **來源** | FSx for NetApp ONTAP 磁碟區 |
| **檔案類型** | .pdf, .tiff, .tif, .jpeg, .jpg (掃描及電子文件) |
| **存取方式** | S3 Access Point (ListObjectsV2 + GetObject) |
| **讀取策略** | 全檔案取得 (OCR 處理所需) |

### 處理
| 步驟 | 服務 | 功能 |
|------|------|------|
| Discovery | Lambda (VPC) | 透過 S3 AP 探索文件檔案，產生清單 |
| OCR | Lambda + Textract | 依頁數自動選擇 sync/async API 進行文字擷取 |
| Entity Extraction | Lambda + Comprehend | 命名實體辨識 (日期、金額、組織、人物) |
| Summary | Lambda + Bedrock | 結構化摘要產生 (合約條款、金額、當事方) |

### 輸出
| 產出物 | 格式 | 說明 |
|--------|------|------|
| OCR 文字 | `ocr-text/YYYY/MM/DD/{stem}.txt` | Textract 擷取文字 |
| 實體 | `entities/YYYY/MM/DD/{stem}.json` | Comprehend 擷取實體 |
| 摘要 | `summaries/YYYY/MM/DD/{stem}_summary.json` | Bedrock 結構化摘要 |
| SNS 通知 | Email | 處理完成通知 (處理數量及錯誤數量) |

---

## 關鍵設計決策

1. **S3 AP 取代 NFS** — Lambda 無需 NFS 掛載；透過 S3 API 取得文件
2. **Textract sync/async 自動選擇** — 單頁使用 sync API (低延遲)，多頁文件使用 async API (高容量)
3. **Comprehend + Bedrock 兩階段方法** — Comprehend 用於結構化實體擷取，Bedrock 用於自然語言摘要產生
4. **JSON 結構化輸出** — 便於與下游系統 (RPA、核心業務系統) 整合
5. **日期分區** — 依處理日期分割目錄，便於重新處理和歷史管理
6. **輪詢 (非事件驅動)** — S3 AP 不支援事件通知，因此使用定期排程執行

---

## 使用的 AWS 服務

| 服務 | 角色 |
|------|------|
| FSx for NetApp ONTAP | 企業檔案儲存 (合約及發票) |
| S3 Access Points | 對 ONTAP 磁碟區的無伺服器存取 |
| EventBridge Scheduler | 定期觸發 |
| Step Functions | 工作流程編排 |
| Lambda | 運算 (Discovery, OCR, Entity Extraction, Summary) |
| Amazon Textract | OCR 文字擷取 (sync/async API) |
| Amazon Comprehend | 命名實體辨識 (NER) |
| Amazon Bedrock | AI 摘要產生 (Nova / Claude) |
| SNS | 處理完成通知 |
| Secrets Manager | ONTAP REST API 憑證管理 |
| CloudWatch + X-Ray | 可觀測性 |
