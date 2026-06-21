# UC18: 電信 / 網路分析 — CDR/網路日誌異常偵測與合規報告

🌐 **Language / 言語**: [日本語](architecture.md) | [English](architecture.en.md) | [한국어](architecture.ko.md) | [简体中文](architecture.zh-CN.md) | 繁體中文 | [Français](architecture.fr.md) | [Deutsch](architecture.de.md) | [Español](architecture.es.md)

## 端對端架構（輸入 → 輸出）

---

## 架構圖

```mermaid
flowchart TB
    subgraph INPUT["📥 輸入 — FSx for ONTAP"]
        DATA["電信資料<br/>.csv/.asn1/.parquet (CDR 檔案)<br/>syslog / SNMP trap (網路設備日誌)"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject"]
    end

    subgraph TRIGGER["⏰ 觸發器"]
        EB["EventBridge Scheduler<br/>cron(0 0 * * ? *) — 每日 00:00 UTC"]
    end

    subgraph SFN["⚙️ Step Functions 工作流程"]
        DISC["1️⃣ Discovery Lambda<br/>• VPC 內執行<br/>• CDR/syslog 檔案偵測<br/>• 後綴篩選器應用<br/>• Manifest 生成"]
        CA["2️⃣ CDR Analyzer Lambda<br/>• 透過 S3 AP 取得 CDR<br/>• 通話元資料擷取<br/>（主叫ID、被叫ID、通話時長、時間戳記、基地台ID）<br/>• Athena 流量統計查詢<br/>（時段通話量、平均時長、尖峰同時通話數）"]
        LA["3️⃣ Log Analyzer Lambda<br/>• Syslog RFC 5424 解析<br/>• SNMP trap 分析<br/>• 設備故障偵測<br/>（link-down、硬體錯誤、程序崩潰）<br/>• 容量閾值超出偵測（預設 80%）"]
        AD["4️⃣ Anomaly Detector Lambda<br/>• Bedrock InvokeModel<br/>• 7天滾動基線比較<br/>• 3σ閾值異常標記<br/>• 異常評分"]
        RL["5️⃣ Report Lambda<br/>• 每日網路健康摘要生成<br/>• 異常告警報告生成<br/>• S3 輸出（reports/daily/{YYYY-MM-DD}/）<br/>• SNS 通知<br/>• CloudWatch EMF 指標"]
    end

    subgraph OUTPUT["📤 輸出 — S3 儲存桶"]
        CDROUT["reports/daily/{YYYY-MM-DD}/cdr-stats.json<br/>CDR 流量統計"]
        LOGOUT["reports/daily/{YYYY-MM-DD}/log-analysis.json<br/>設備故障分析結果"]
        ANOMOUT["reports/daily/{YYYY-MM-DD}/anomalies.json<br/>異常偵測結果"]
        ERROUT["errors/cdr/{filename}.json<br/>CDR 解析錯誤記錄"]
    end

    subgraph NOTIFY["📧 通知"]
        SNS["Amazon SNS<br/>電郵 / Slack<br/>（重大異常和設備故障告警）"]
    end

    DATA --> ALIAS
    ALIAS --> DISC
    EB --> SFN
    DISC --> CA
    DISC --> LA
    CA --> AD
    LA --> AD
    AD --> RL
    CA --> CDROUT
    LA --> LOGOUT
    AD --> ANOMOUT
    RL --> ERROUT
    RL --> SNS
```

---

## 關鍵設計決策

1. **CDR 和 syslog 並行處理** — CDR 分析和日誌分析可以獨立執行。透過 Step Functions Map State 並行化提升吞吐量
2. **透過 Athena 進行大規模 CDR 彙整** — 使用無伺服器 SQL 高效彙整大量 CDR 記錄
3. **7天滾動基線** — 考慮工作日特徵的統計異常偵測
4. **3σ閾值異常標記** — 僅偵測統計顯著的異常。最小化誤報
5. **錯誤隔離** — CDR 解析失敗記錄在 `errors/cdr/` 下，不中斷整個批次
6. **基於輪詢** — S3 AP 不支援事件通知，因此使用 EventBridge Scheduler 每日執行

---

## 使用的 AWS 服務

| 服務 | 角色 |
|------|------|
| FSx for ONTAP | CDR/網路日誌儲存 |
| S3 Access Points | 對 ONTAP 卷的無伺服器存取 |
| EventBridge Scheduler | 每日觸發（00:00 UTC） |
| Step Functions | 工作流程編排（並行 Map State） |
| Lambda | 運算（Discovery, CDR Analyzer, Log Analyzer, Anomaly Detector, Report） |
| Amazon Athena | CDR 流量統計 SQL 查詢 |
| Amazon Bedrock | 異常偵測推論（Claude / Nova） |
| SNS | 重大異常和設備故障告警通知 |
| Secrets Manager | ONTAP REST API 憑證管理 |
| CloudWatch + X-Ray | 可觀測性（EMF 指標、鏈路追蹤） |
