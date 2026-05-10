# UC13: 教育 / 研究 — 論文 PDF 自動分類・引用網絡分析

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](architecture.md) | [English](architecture.en.md) | [한국어](architecture.ko.md) | [简体中文](architecture.zh-CN.md) | 繁體中文 | [Français](architecture.fr.md) | [Deutsch](architecture.de.md) | [Español](architecture.es.md)

> 注意：此翻譯由 Amazon Bedrock Claude 產生。歡迎對翻譯品質提出改進建議。

## End-to-End Architecture (Input → Output)

---

## Architecture Diagram

```mermaid
flowchart TB
    subgraph INPUT["📥 Input — FSx for NetApp ONTAP"]
        PAPERS["論文 PDF / 研究資料<br/>.pdf, .csv, .json, .xml"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject"]
    end

    subgraph TRIGGER["⏰ Trigger"]
        EB["EventBridge Scheduler<br/>rate(6 hours)"]
    end

    subgraph SFN["⚙️ Step Functions Workflow"]
        DISC["1️⃣ Discovery Lambda<br/>• VPC 內執行<br/>• S3 AP 檔案偵測<br/>• .pdf 篩選<br/>• Manifest 生成"]
        OCR["2️⃣ OCR Lambda<br/>• 透過 S3 AP 取得 PDF<br/>• Textract (跨區域)<br/>• 文字擷取<br/>• 結構化文字輸出"]
        META["3️⃣ Metadata Lambda<br/>• 標題擷取<br/>• 作者名稱擷取<br/>• DOI / ISSN 偵測<br/>• 出版年份・期刊名稱"]
        CL["4️⃣ Classification Lambda<br/>• Bedrock InvokeModel<br/>• 研究領域分類<br/>  (CS, Bio, Physics, etc.)<br/>• 關鍵字擷取<br/>• 結構化摘要"]
        CA["5️⃣ Citation Analysis Lambda<br/>• 參考文獻區段解析<br/>• 引用關係擷取<br/>• 引用網路建構<br/>• 鄰接清單 JSON 輸出"]
    end

    subgraph OUTPUT["📤 Output — S3 Bucket"]
        TEXT["ocr-text/*.txt<br/>OCR 擷取文字"]
        METADATA["metadata/*.json<br/>結構化詮釋資料"]
        CLASS["classification/*.json<br/>領域分類結果"]
        CITE["citations/*.json<br/>引用網路"]
    end

    subgraph NOTIFY["📧 Notification"]
        SNS["Amazon SNS<br/>處理完成通知"]
    end

    PAPERS --> ALIAS
    ALIAS --> DISC
    EB --> SFN
    DISC --> OCR
    OCR --> META
    META --> CL
    CL --> CA
    OCR --> TEXT
    META --> METADATA
    CL --> CLASS
    CA --> CITE
    CA --> SNS
```

---

## Data Flow Detail

### Input
| 項目 | 說明 |
|------|-------------|
| **Source** | FSx for NetApp ONTAP volume |
| **File Types** | .pdf (論文 PDF)、.csv, .json, .xml (研究資料) |
| **Access Method** | S3 Access Point (ListObjectsV2 + GetObject) |
| **Read Strategy** | 取得完整 PDF(OCR・詮釋資料擷取所需) |

### Processing
| 步驟 | 服務 | 功能 |
|------|---------|----------|
| Discovery | Lambda (VPC) | 透過 S3 AP 偵測論文 PDF、生成 Manifest |
| OCR | Lambda + Textract | PDF 文字擷取(支援跨區域) |
| Metadata | Lambda | 論文詮釋資料擷取(標題、作者、DOI、出版年份) |
| Classification | Lambda + Bedrock | 研究領域分類、關鍵字擷取、結構化摘要生成 |
| Citation Analysis | Lambda | 參考文獻解析、引用網路建構(鄰接清單) |

### Output
| 產出物 | 格式 | 說明 |
|----------|--------|-------------|
| OCR Text | `ocr-text/YYYY/MM/DD/{stem}.txt` | Textract 擷取文字 |
| Metadata | `metadata/YYYY/MM/DD/{stem}.json` | 結構化詮釋資料(title, authors, DOI, year) |
| Classification | `classification/YYYY/MM/DD/{stem}_class.json` | 領域分類・關鍵字・摘要 |
| Citation Network | `citations/YYYY/MM/DD/citation_network.json` | 引用網路(鄰接清單格式) |
| SNS Notification | Email | 處理完成通知(處理數量・分類結果摘要) |

---

## Key Design Decisions

1. **S3 AP over NFS** — Lambda 無需掛載 NFS,透過 S3 API 取得論文 PDF
2. **Textract 跨區域** — 即使在 Textract 不支援的區域也可透過跨區域呼叫對應
3. **5 階段管線** — 依 OCR → Metadata → Classification → Citation 順序逐步累積資訊
4. **透過 Bedrock 進行領域分類** — 基於預先定義的分類體系(ACM CCS 等)進行自動分類
5. **引用網路(鄰接清單)** — 以圖形結構表示引用關係,支援下游分析(PageRank、社群偵測)
6. **輪詢基礎** — 由於 S3 AP 不支援事件通知,採用定期排程執行

---

## AWS Services Used

| 服務 | 角色 |
|---------|------|
| FSx for NetApp ONTAP | 論文・研究資料儲存 |
| S3 Access Points | 對 ONTAP volume 的無伺服器存取 |
| EventBridge Scheduler | 定期觸發器 |
| Step Functions | 工作流程編排 |
| Lambda | 運算(Discovery, OCR, Metadata, Classification, Citation Analysis) |
| Amazon Textract | PDF 文字擷取(跨區域) |
| Amazon Bedrock | 領域分類・關鍵字擷取 (Claude / Nova) |
| SNS | 處理完成通知 |
| Secrets Manager | ONTAP REST API 認證資訊管理 |
| CloudWatch + X-Ray | 可觀測性 |
