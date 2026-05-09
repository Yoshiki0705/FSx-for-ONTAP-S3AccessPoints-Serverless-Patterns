# UC4: 媒體 — VFX 算繪管線

🌐 **Language / 言語**: [日本語](architecture.md) | [English](architecture.en.md) | [한국어](architecture.ko.md) | [简体中文](architecture.zh-CN.md) | 繁體中文 | [Français](architecture.fr.md) | [Deutsch](architecture.de.md) | [Español](architecture.es.md)

## 端對端架構 (輸入 → 輸出)

---

## 架構圖

```mermaid
flowchart TB
    subgraph INPUT["📥 輸入 — FSx for NetApp ONTAP"]
        VFX["VFX 專案檔案<br/>.exr, .dpx, .mov, .abc"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject / PutObject"]
    end

    subgraph TRIGGER["⏰ 觸發器"]
        EB["EventBridge Scheduler<br/>rate(30 minutes)"]
    end

    subgraph SFN["⚙️ Step Functions 工作流程"]
        DISC["1️⃣ Discovery Lambda<br/>• 在 VPC 內執行<br/>• S3 AP 檔案探索<br/>• .exr/.dpx/.mov/.abc 過濾<br/>• 清單產生"]
        JS["2️⃣ Job Submit Lambda<br/>• 透過 S3 AP 取得資產<br/>• Deadline Cloud / Batch<br/>  算繪作業提交<br/>• Job ID 追蹤"]
        QC["3️⃣ Quality Check Lambda<br/>• Rekognition DetectLabels<br/>• 偽影偵測<br/>  (雜訊、條帶、閃爍)<br/>• 品質分數計算"]
    end

    subgraph OUTPUT_PASS["✅ 輸出 — 通過"]
        PUTBACK["S3 AP PutObject<br/>寫回 FSx ONTAP"]
    end

    subgraph OUTPUT_FAIL["❌ 輸出 — 不通過"]
        SNS["Amazon SNS<br/>重新算繪通知"]
    end

    VFX --> ALIAS
    ALIAS --> DISC
    EB --> SFN
    DISC --> JS
    JS --> QC
    QC --> PUTBACK
    QC --> SNS
```

---

## 資料流詳情

### 輸入
| 項目 | 說明 |
|------|------|
| **來源** | FSx for NetApp ONTAP 磁碟區 |
| **檔案類型** | .exr, .dpx, .mov, .abc (VFX 專案檔案) |
| **存取方式** | S3 Access Point (ListObjectsV2 + GetObject) |
| **讀取策略** | 算繪目標的全資產取得 |

### 處理
| 步驟 | 服務 | 功能 |
|------|------|------|
| Discovery | Lambda (VPC) | 透過 S3 AP 探索 VFX 資產，產生清單 |
| Job Submit | Lambda + Deadline Cloud/Batch | 提交算繪作業，追蹤作業狀態 |
| Quality Check | Lambda + Rekognition | 算繪品質評估 (偽影偵測) |

### 輸出
| 產出物 | 格式 | 說明 |
|--------|------|------|
| 已核准資產 | S3 AP PutObject → FSx ONTAP | 寫回品質核准的資產 |
| QC 報告 | `qc-results/YYYY/MM/DD/{shot}_{version}.json` | 品質檢查結果 |
| SNS 通知 | Email / Slack | 不通過時的重新算繪通知 |

---

## 關鍵設計決策

1. **S3 AP 雙向存取** — GetObject 取得資產，PutObject 寫回已核准資產 (無需 NFS 掛載)
2. **Deadline Cloud / Batch 整合** — 在託管算繪農場上的可擴展作業執行
3. **Rekognition 基於品質檢查** — 自動偵測偽影 (雜訊、條帶、閃爍) 以減少人工審核負擔
4. **通過/不通過分支流程** — 品質通過時自動寫回，不通過時向藝術家發送 SNS 通知
5. **按鏡頭處理** — 遵循標準 VFX 管線鏡頭/版本管理規範
6. **輪詢 (非事件驅動)** — S3 AP 不支援事件通知，因此使用定期排程執行

---

## 使用的 AWS 服務

| 服務 | 角色 |
|------|------|
| FSx for NetApp ONTAP | VFX 專案儲存 (EXR/DPX/MOV/ABC) |
| S3 Access Points | 對 ONTAP 磁碟區的雙向無伺服器存取 |
| EventBridge Scheduler | 定期觸發 |
| Step Functions | 工作流程編排 |
| Lambda | 運算 (Discovery, Job Submit, Quality Check) |
| AWS Deadline Cloud / Batch | 算繪作業執行 |
| Amazon Rekognition | 算繪品質評估 (偽影偵測) |
| SNS | 不通過時的重新算繪通知 |
| Secrets Manager | ONTAP REST API 憑證管理 |
| CloudWatch + X-Ray | 可觀測性 |
