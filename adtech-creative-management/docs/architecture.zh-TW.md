# UC19: 廣告·行銷 / 創意資產管理 — 資產編目與品牌合規檢查

🌐 **Language / 語言**: [日本語](architecture.md) | [English](architecture.en.md) | [한국어](architecture.ko.md) | [简体中文](architecture.zh-CN.md) | 繁體中文 | [Français](architecture.fr.md) | [Deutsch](architecture.de.md) | [Español](architecture.es.md)

## 端對端架構（輸入 → 輸出）

---

## 架構圖

```mermaid
flowchart TB
    subgraph INPUT["📥 輸入 — FSx for ONTAP"]
        DATA["創意資產<br/>.jpeg/.png/.tiff（圖像）<br/>.mp4/.mov（影片）<br/>.psd（設計檔案）"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject"]
    end

    subgraph TRIGGER["⏰ 觸發器"]
        EB["EventBridge Scheduler<br/>cron(0 0 * * ? *) — 每天 00:00 UTC"]
    end

    subgraph SFN["⚙️ Step Functions 工作流程"]
        DISC["1️⃣ Discovery Lambda<br/>• VPC 內執行<br/>• 媒體檔案偵測<br/>• 格式 + 大小篩選（5 GB 限制）<br/>• Manifest 產生"]
        VA["2️⃣ Visual Analyzer Lambda<br/>• 透過 S3 AP 取得資產<br/>• Rekognition DetectLabels（80% 信賴度閾值）<br/>• Rekognition DetectModerationLabels<br/>• Rekognition DetectText<br/>• 每資產最多產生 50 個標籤"]
        TC["3️⃣ Text Compliance Lambda<br/>• Textract 文字擷取（us-east-1 跨區域）<br/>• 載入品牌用語指南 JSON<br/>• Bedrock InvokeModel — 品牌合規檢查<br/>• 結果：compliant / non-compliant + 匹配用語清單"]
        RL["4️⃣ Report Lambda<br/>• 資產目錄產生（JSON + CSV）<br/>• 審核違規標記（requires-review）<br/>• CloudWatch EMF Metrics 傳送<br/>• SNS 通知"]
    end

    subgraph OUTPUT["📤 輸出 — S3 Bucket"]
        CATALOG["reports/{execution-id}/asset-catalog.json"]
        CSV["reports/{execution-id}/asset-catalog.csv"]
        FLAGGED["reports/{execution-id}/flagged-assets.json"]
        ERROUT["errors/{execution-id}/{filename}.json"]
    end

    DATA --> ALIAS
    ALIAS --> DISC
    EB --> SFN
    DISC --> VA
    DISC --> TC
    VA --> RL
    TC --> RL
    RL --> CATALOG
    RL --> CSV
    RL --> FLAGGED
    RL --> ERROUT
```

---

## 使用的 AWS 服務

| 服務 | 角色 |
|------|------|
| FSx for ONTAP | 創意資產儲存 |
| S3 Access Points | ONTAP 磁碟區的無伺服器存取 |
| EventBridge Scheduler | 每日觸發（00:00 UTC） |
| Step Functions | 工作流程編排（平行 Map State） |
| Lambda | 運算（Discovery、Visual Analyzer、Text Compliance、Report） |
| Amazon Rekognition | 視覺分析（標籤、審核、文字偵測） |
| Amazon Textract | 文字疊加擷取（us-east-1 跨區域） |
| Amazon Bedrock | 品牌指南合規檢查推論（Claude / Nova） |
| SNS | 審核違規警示通知 |
| CloudWatch + X-Ray | 可觀測性（EMF Metrics、追蹤） |
