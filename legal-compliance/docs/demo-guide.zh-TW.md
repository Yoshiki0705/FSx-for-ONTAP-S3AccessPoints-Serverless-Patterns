# 檔案伺服器權限稽核 — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | 繁體中文 | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> 注意：此翻譯由 Amazon Bedrock Claude 產生。歡迎對翻譯品質提出改進建議。

## Executive Summary

本示範展示了自動檢測檔案伺服器上過度存取權限的稽核工作流程。透過解析 NTFS ACL，識別違反最小權限原則的項目，並自動生成合規報告。

**示範核心訊息**：將手動需要數週時間的檔案伺服器權限稽核自動化，即時可視化過度權限的風險。

**預估時間**：3〜5 分鐘

---

## Target Audience & Persona

| 項目 | 詳細 |
|------|------|
| **職位** | 資訊安全負責人 / IT 合規管理者 |
| **日常業務** | 存取權限審查、稽核應對、安全政策管理 |
| **課題** | 手動確認數千個資料夾的權限並不實際 |
| **期待成果** | 早期發現過度權限並自動化合規追蹤 |

### Persona：佐藤先生（資訊安全管理者）

- 年度稽核需要審查所有共享資料夾的權限
- 希望即時檢測「Everyone 完全控制」等危險設定
- 希望有效率地製作提交給稽核法人的報告

---

## Demo Scenario：年度權限稽核的自動化

### 工作流程全貌

```
檔案伺服器     ACL 收集        權限分析          報告生成
(NTFS 共享)   →   中繼資料   →   違規檢測    →    稽核報告
                   擷取            (規則比對)      (AI 摘要)
```

---

## Storyboard（5 個章節 / 3〜5 分鐘）

### Section 1: Problem Statement（0:00–0:45）

**旁白要旨**:
> 年度稽核時期到來。需要對數千個共享資料夾進行權限審查，但手動確認需要數週時間。若放任過度權限，資訊洩漏風險將會提高。

**Key Visual**：大量資料夾結構與「手動稽核：預估 3〜4 週」的疊加顯示

### Section 2: Workflow Trigger（0:45–1:30）

**旁白要旨**:
> 指定稽核對象的磁碟區，啟動權限稽核工作流程。

**Key Visual**：Step Functions 執行畫面、對象路徑指定

### Section 3: ACL Analysis（1:30–2:30）

**旁白要旨**:
> 自動收集各資料夾的 NTFS ACL，並以下列規則檢測違規：
> - 對 Everyone / Authenticated Users 的過度權限
> - 不必要的繼承累積
> - 離職人員帳號的殘留

**Key Visual**：透過平行處理進行的 ACL 掃描進度

### Section 4: Results Review（2:30–3:45）

**旁白要旨**:
> 以 SQL 查詢檢測結果。確認違規件數、依風險等級的分布。

**Key Visual**：Athena 查詢結果 — 違規清單表格

### Section 5: Compliance Report（3:45–5:00）

**旁白要旨**:
> AI 自動生成稽核報告。呈現風險評估、建議對應、優先順序行動。

**Key Visual**：生成的稽核報告（風險摘要 + 對應建議）

---

## Screen Capture Plan

| # | 畫面 | 章節 |
|---|------|-----------|
| 1 | 檔案伺服器的資料夾結構 | Section 1 |
| 2 | 工作流程執行開始 | Section 2 |
| 3 | ACL 掃描平行處理中 | Section 3 |
| 4 | Athena 違規檢測查詢結果 | Section 4 |
| 5 | AI 生成稽核報告 | Section 5 |

---

## Narration Outline

| 章節 | 時間 | 關鍵訊息 |
|-----------|------|--------------|
| Problem | 0:00–0:45 | 「手動進行數千個資料夾的權限稽核並不實際」 |
| Trigger | 0:45–1:30 | 「指定對象磁碟區並開始稽核」 |
| Analysis | 1:30–2:30 | 「自動收集 ACL 並檢測政策違規」 |
| Results | 2:30–3:45 | 「即時掌握違規件數與風險等級」 |
| Report | 3:45–5:00 | 「自動生成稽核報告，呈現對應優先順序」 |

---

## Sample Data Requirements

| # | 資料 | 用途 |
|---|--------|------|
| 1 | 正常權限資料夾（50+） | 基準線 |
| 2 | Everyone 完全控制設定（5 件） | 高風險違規 |
| 3 | 離職人員帳號殘留（3 件） | 中風險違規 |
| 4 | 過度繼承資料夾（10 件） | 低風險違規 |

---

## Timeline

### 1 週內可達成

| 任務 | 所需時間 |
|--------|---------|
| 範例 ACL 資料生成 | 2 小時 |
| 工作流程執行確認 | 2 小時 |
| 畫面擷取取得 | 2 小時 |
| 旁白稿撰寫 | 2 小時 |
| 影片編輯 | 4 小時 |

### Future Enhancements

- 與 Active Directory 整合的離職人員自動檢測
- 即時權限變更監控
- 自動執行修正行動

---

## Technical Notes

| 元件 | 角色 |
|--------------|------|
| Step Functions | 工作流程編排 |
| Lambda (ACL Collector) | NTFS ACL 中繼資料收集 |
| Lambda (Policy Checker) | 政策違規規則比對 |
| Lambda (Report Generator) | 透過 Bedrock 生成稽核報告 |
| Amazon Athena | 違規資料的 SQL 分析 |

### 備援方案

| 情境 | 對應 |
|---------|------|
| ACL 收集失敗 | 使用預先取得的資料 |
| Bedrock 延遲 | 顯示預先生成的報告 |

---

*本文件為技術簡報用示範影片的製作指南。*

---

## 關於輸出目的地：FSxN S3 Access Point (Pattern A)

UC1 legal-compliance 被分類為 **Pattern A: Native S3AP Output**
（參照 `docs/output-destination-patterns.md`）。

**設計**：合約中繼資料、稽核日誌、摘要報告全部透過 FSxN S3 Access Point
寫回至與原始合約資料**相同的 FSx ONTAP 磁碟區**。不會建立標準 S3 儲存貯體
（"no data movement" 模式）。

**CloudFormation 參數**：
- `S3AccessPointAlias`：用於讀取輸入合約資料的 S3 AP Alias
- `S3AccessPointOutputAlias`：用於寫入輸出的 S3 AP Alias（可與輸入相同）

**部署範例**：
```bash
aws cloudformation deploy \
  --template-file legal-compliance/template-deploy.yaml \
  --stack-name fsxn-legal-compliance-demo \
  --parameter-overrides \
    S3AccessPointAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    S3AccessPointOutputAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    ... (其他必要參數)
```

**從 SMB/NFS 使用者的視角**：
```
/vol/contracts/
  ├── 2026/Q2/contract_ABC.pdf         # 原始合約書
  └── summaries/2026/05/                # AI 生成摘要（同一磁碟區內）
      └── contract_ABC.json
```

關於 AWS 規格上的限制，請參照
[專案 README 的「AWS 規格上的限制與因應對策」章節](../../README.md#aws-仕様上の制約と回避策)
以及 [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)。

---

## 已驗證的 UI/UX 螢幕截圖

與 Phase 7 UC15/16/17 和 UC6/11/14 的示範相同方針，以**終端使用者在日常業務中實際
看到的 UI/UX 畫面**為對象。技術人員視圖（Step Functions 圖表、CloudFormation
堆疊事件等）集中於 `docs/verification-results-*.md`。

### 此使用案例的驗證狀態

- ✅ **E2E 執行**：Phase 1-6 已確認（參照根目錄 README）
- 📸 **UI/UX 重新拍攝**：✅ 2026-05-10 重新部署驗證時已拍攝（確認 UC1 Step Functions 圖表、Lambda 執行成功）
- 🔄 **重現方法**：參照本文件末尾的「拍攝指南」

### 2026-05-10 重新部署驗證時拍攝（以 UI/UX 為中心）

#### UC1 Step Functions Graph view（SUCCEEDED）

![UC1 Step Functions Graph view（SUCCEEDED）](../../docs/screenshots/masked/uc1-demo/uc1-stepfunctions-graph.png)

Step Functions Graph view 是以顏色可視化各 Lambda / Parallel / Map 狀態執行狀況的
終端使用者最重要畫面。

### 既有螢幕截圖（來自 Phase 1-6 的相關部分）

#### UC1 CloudFormation 堆疊部署完成（2026-05-02 驗證時）

![UC1 CloudFormation 堆疊部署完成（2026-05-02 驗證時）](../../docs/screenshots/masked/phase1/phase1-cloudformation-uc1-deployed.png)

#### UC1 Step Functions SUCCEEDED（E2E 執行成功）

![UC1 Step Functions SUCCEEDED（E2E 執行成功）](../../docs/screenshots/masked/phase1/phase1-step-functions-uc1-succeeded.png)


### 重新驗證時的 UI/UX 對象畫面（建議拍攝清單）

- S3 輸出儲存貯體（audit-reports/、acl-audits/、athena-results/ 前綴）
- Athena 查詢結果（ACL 違規檢測 SQL）
- Bedrock 生成的稽核報告（合規違規摘要）
- SNS 通知郵件（稽核警示）

### 拍攝指南

1. **事前準備**：
   - `bash scripts/verify_phase7_prerequisites.sh` 確認前提（共用 VPC/S3 AP 有無）
   - `UC=legal-compliance bash scripts/package_generic_uc.sh` 打包 Lambda
   - `bash scripts/deploy_generic_ucs.sh UC1` 進行部署

2. **範例資料配置**：
   - 透過 S3 AP Alias 將範例檔案上傳至 `contracts/` 前綴
   - 啟動 Step Functions `fsxn-legal-compliance-demo-workflow`（輸入 `{}`）

3. **拍攝**（關閉 CloudShell・終端機，將瀏覽器右上角的使用者名稱塗黑）：
   - S3 輸出儲存貯體 `fsxn-legal-compliance-demo-output-<account>` 的概覽
   - AI/ML 輸出 JSON 的預覽（參考 `build/preview_*.html` 的格式）
   - SNS 郵件通知（如適用）

4. **遮罩處理**：
   - `python3 scripts/mask_uc_demos.py legal-compliance-demo` 進行自動遮罩
   - 依照 `docs/screenshots/MASK_GUIDE.md` 進行額外遮罩（如有需要）

5. **清理**：
   - `bash scripts/cleanup_generic_ucs.sh UC1` 進行刪除
   - VPC Lambda ENI 釋放需 15-30 分鐘（AWS 規格）
