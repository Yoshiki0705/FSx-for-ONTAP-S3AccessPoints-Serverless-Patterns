# 契約書・請求書自動處理 — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | 繁體中文 | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> 注意：此翻譯由 Amazon Bedrock Claude 產生。歡迎對翻譯品質提出改進建議。

## Executive Summary

本示範展示了合約書・請求書的自動處理管線。結合 OCR 文字擷取與實體擷取，從非結構化文件自動生成結構化資料。

**示範的核心訊息**：將紙本合約書・請求書自動數位化，即時擷取並結構化金額、日期、交易對象等重要資訊。

**預估時間**：3〜5 分鐘

---

## Target Audience & Persona

| 項目 | 詳細 |
|------|------|
| **職位** | 會計部門經理 / 合約管理負責人 |
| **日常業務** | 請求書處理、合約書管理、付款核准 |
| **課題** | 大量紙本文件的手動輸入耗時 |
| **期待成果** | 文件處理自動化與減少輸入錯誤 |

### Persona：山田先生（會計部門主管）

- 每月處理 200+ 件請求書
- 手動輸入造成的錯誤與延遲是課題
- 「希望請求書送達後能自動擷取金額與付款期限」

---

## Demo Scenario：請求書批次處理

### 工作流程全貌

```
文件掃描       OCR 處理        實體           結構化資料
(PDF/圖片)   →   文字擷取  →   擷取・分類   →    輸出 (JSON)
                                   (AI 解析)
```

---

## Storyboard（5 個段落 / 3〜5 分鐘）

### Section 1: Problem Statement（0:00–0:45）

**旁白要旨**:
> 每月收到 200 件以上的請求書。手動輸入金額、日期、交易對象既耗時又容易出錯。

**Key Visual**：大量 PDF 請求書檔案清單

### Section 2: Document Upload（0:45–1:30）

**旁白要旨**:
> 只需將掃描完成的文件放置到檔案伺服器，自動處理管線就會啟動。

**Key Visual**：檔案上傳 → 工作流程自動啟動

### Section 3: OCR & Extraction（1:30–2:30）

**旁白要旨**:
> 透過 OCR 擷取文字，AI 判定文件類型。自動分類請求書・合約書・收據，並從各文件擷取重要欄位。

**Key Visual**：OCR 處理進度、文件分類結果

### Section 4: Structured Output（2:30–3:45）

**旁白要旨**:
> 將擷取結果以結構化資料輸出。金額、付款期限、交易對象名稱、請求書編號等以 JSON 格式提供使用。

**Key Visual**：擷取結果表格（請求書編號、金額、期限、交易對象）

### Section 5: Validation & Report（3:45–5:00）

**旁白要旨**:
> AI 評估擷取結果的信賴度，標記低信賴度的項目。透過處理摘要報告掌握整體處理狀況。

**Key Visual**：附信賴度分數的結果、處理摘要報告

---

## Screen Capture Plan

| # | 畫面 | 段落 |
|---|------|-----------|
| 1 | 請求書 PDF 檔案清單 | Section 1 |
| 2 | 工作流程自動啟動 | Section 2 |
| 3 | OCR 處理・文件分類結果 | Section 3 |
| 4 | 結構化資料輸出（JSON/表格） | Section 4 |
| 5 | 處理摘要報告 | Section 5 |

---

## Narration Outline

| 段落 | 時間 | 關鍵訊息 |
|-----------|------|--------------|
| Problem | 0:00–0:45 | 「每月手動處理 200 件請求書已達極限」 |
| Upload | 0:45–1:30 | 「只需放置檔案即可開始自動處理」 |
| OCR | 1:30–2:30 | 「OCR + AI 進行文件分類與欄位擷取」 |
| Output | 2:30–3:45 | 「以結構化資料形式立即可用」 |
| Report | 3:45–5:00 | 「透過信賴度評估明確標示需人工確認之處」 |

---

## Sample Data Requirements

| # | 資料 | 用途 |
|---|--------|------|
| 1 | 請求書 PDF（10 件） | 主要處理對象 |
| 2 | 合約書 PDF（3 件） | 文件分類示範 |
| 3 | 收據圖片（3 件） | 圖片 OCR 示範 |
| 4 | 低品質掃描（2 件） | 信賴度評估示範 |

---

## Timeline

### 1 週內可達成

| 任務 | 所需時間 |
|--------|---------|
| 準備範例文件 | 3 小時 |
| 確認管線執行 | 2 小時 |
| 取得畫面截圖 | 2 小時 |
| 撰寫旁白稿 | 2 小時 |
| 影片編輯 | 4 小時 |

### Future Enhancements

- 與會計系統自動整合
- 整合核准工作流程
- 多語言文件支援（英語・中文）

---

## Technical Notes

| 元件 | 角色 |
|--------------|------|
| Step Functions | 工作流程編排 |
| Lambda (OCR Processor) | 透過 Textract 進行文件文字擷取 |
| Lambda (Entity Extractor) | 透過 Bedrock 進行實體擷取 |
| Lambda (Classifier) | 文件類型分類 |
| Amazon Athena | 擷取資料的彙總分析 |

### 備援方案

| 情境 | 對應 |
|---------|------|
| OCR 精度下降 | 使用預先處理的文字 |
| Bedrock 延遲 | 顯示預先生成的結果 |

---

*本文件為技術簡報用示範影片的製作指南。*

---

## 關於輸出目的地：FSxN S3 Access Point (Pattern A)

UC2 financial-idp 歸類為 **Pattern A: Native S3AP Output**
（參照 `docs/output-destination-patterns.md`）。

**設計**：請求書 OCR 結果、結構化詮釋資料、BedRock 摘要全部透過 FSxN S3 Access Point
寫回至與原始請求書 PDF **相同的 FSx ONTAP 磁碟區**。不會建立標準 S3 儲存貯體
（"no data movement" 模式）。

**CloudFormation 參數**:
- `S3AccessPointAlias`：用於讀取輸入資料的 S3 AP Alias
- `S3AccessPointOutputAlias`：用於寫入輸出的 S3 AP Alias（可與輸入相同）

**部署範例**:
```bash
aws cloudformation deploy \
  --template-file financial-idp/template-deploy.yaml \
  --stack-name fsxn-financial-idp-demo \
  --parameter-overrides \
    S3AccessPointAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    S3AccessPointOutputAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    ... (其他必要參數)
```

**從 SMB/NFS 使用者的視角**:
```
/vol/invoices/
  ├── 2026/05/invoice_001.pdf          # 原始請求書
  └── summaries/2026/05/                # AI 生成摘要（同一磁碟區內）
      └── invoice_001.json
```

關於 AWS 規格上的限制，請參照
[專案 README 的「AWS 規格上的限制與因應對策」段落](../../README.md#aws-仕様上の制約と回避策)
以及 [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)。

---

## 已驗證的 UI/UX 螢幕截圖

與 Phase 7 UC15/16/17 及 UC6/11/14 的示範相同方針，以**終端使用者在日常業務中實際
看到的 UI/UX 畫面**為對象。技術人員視圖（Step Functions 圖表、CloudFormation
堆疊事件等）彙整於 `docs/verification-results-*.md`。

### 此使用案例的驗證狀態

- ⚠️ **E2E 驗證**：僅部分功能（正式環境建議追加驗證）
- 📸 **UI/UX 重新拍攝**：未實施

### 2026-05-10 重新部署驗證時拍攝（以 UI/UX 為中心）

#### UC2 Step Functions Graph view（SUCCEEDED）

![UC2 Step Functions Graph view（SUCCEEDED）](../../docs/screenshots/masked/uc2-demo/uc2-stepfunctions-graph.png)

Step Functions Graph view 以顏色視覺化各 Lambda / Parallel / Map 狀態的執行狀況，
是終端使用者最重要的畫面。

### 既有螢幕截圖（來自 Phase 1-6 的相關部分）

![UC2 Step Functions 圖表視圖 (SUCCEEDED)](../../docs/screenshots/masked/uc2-demo/step-functions-graph-succeeded.png)

### 重新驗證時的 UI/UX 對象畫面（建議拍攝清單）

- S3 輸出儲存貯體（textract-results/、comprehend-entities/、reports/）
- Textract OCR 結果 JSON（從合約書・請求書擷取的欄位）
- Comprehend 實體偵測結果（組織名稱、日期、金額）
- Bedrock 生成的摘要報告

### 拍攝指南

1. **事前準備**:
   - 執行 `bash scripts/verify_phase7_prerequisites.sh` 確認前提（共用 VPC/S3 AP 是否存在）
   - 執行 `UC=financial-idp bash scripts/package_generic_uc.sh` 打包 Lambda
   - 執行 `bash scripts/deploy_generic_ucs.sh UC2` 進行部署

2. **放置範例資料**:
   - 透過 S3 AP Alias 將範例檔案上傳至 `invoices/` 前綴
   - 啟動 Step Functions `fsxn-financial-idp-demo-workflow`（輸入 `{}`）

3. **拍攝**（關閉 CloudShell・終端機，將瀏覽器右上角的使用者名稱塗黑）:
   - S3 輸出儲存貯體 `fsxn-financial-idp-demo-output-<account>` 的概覽
   - AI/ML 輸出 JSON 的預覽（參考 `build/preview_*.html` 格式）
   - SNS 電子郵件通知（如適用）

4. **遮罩處理**:
   - 執行 `python3 scripts/mask_uc_demos.py financial-idp-demo` 進行自動遮罩
   - 依照 `docs/screenshots/MASK_GUIDE.md` 進行追加遮罩（如有需要）

5. **清理**:
   - 執行 `bash scripts/cleanup_generic_ucs.sh UC2` 進行刪除
   - VPC Lambda ENI 釋放需 15-30 分鐘（AWS 規格）
