# 配送傳票 OCR・庫存分析 — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | 繁體中文 | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> 注意：此翻譯由 Amazon Bedrock Claude 產生。歡迎對翻譯品質提出改進建議。

## Executive Summary

本示範展示配送單據的 OCR 處理與庫存分析管線。將紙本單據數位化，自動彙總與分析進出貨資料。

**示範核心訊息**：自動將配送單據數位化，支援即時掌握庫存狀況與需求預測。

**預估時間**：3〜5 分鐘

---

## Target Audience & Persona

| 項目 | 詳細 |
|------|------|
| **職位** | 物流經理 / 倉庫管理者 |
| **日常業務** | 進出貨管理、庫存確認、配送安排 |
| **課題** | 紙本單據手動輸入造成的延遲與錯誤 |
| **期待成果** | 單據處理自動化與庫存可視化 |

### Persona：齋藤先生（物流經理）

- 每日處理 500+ 張配送單據
- 手動輸入的時間差導致庫存資訊總是延遲
- 「希望只要掃描單據就能反映到庫存」

---

## Demo Scenario：配送單據批次處理

### 工作流程全貌

```
配送單據          OCR 處理       資料結構化       庫存分析
(掃描影像) →  文字擷取 →  欄位       →   彙總報表
                               對應          需求預測
```

---

## Storyboard（5 個段落 / 3〜5 分鐘）

### Section 1: Problem Statement（0:00–0:45）

**旁白要旨**：
> 每日 500 張以上的配送單據。手動輸入導致庫存資訊更新延遲，缺貨或過剩庫存的風險提高。

**Key Visual**：大量單據掃描影像、手動輸入的延遲意象

### Section 2: Scan & Upload（0:45–1:30）

**旁白要旨**：
> 只要將掃描的單據影像放置到資料夾，OCR 管線就會自動啟動。

**Key Visual**：單據影像上傳 → 工作流程啟動

### Section 3: OCR Processing（1:30–2:30）

**旁白要旨**：
> OCR 擷取單據文字，AI 自動對應品名、數量、收件地、日期等欄位。

**Key Visual**：OCR 處理中、欄位擷取結果

### Section 4: Inventory Analysis（2:30–3:45）

**旁白要旨**：
> 擷取資料與庫存資料庫比對。自動彙總進出貨，更新庫存狀況。

**Key Visual**：庫存彙總結果、品項別進出貨趨勢

### Section 5: Demand Report（3:45–5:00）

**旁白要旨**：
> AI 生成庫存分析報表。呈現庫存週轉率、缺貨風險品項、訂購建議。

**Key Visual**：AI 生成庫存報表（庫存摘要 + 訂購建議）

---

## Screen Capture Plan

| # | 畫面 | 段落 |
|---|------|-----------|
| 1 | 單據掃描影像清單 | Section 1 |
| 2 | 上傳・管線啟動 | Section 2 |
| 3 | OCR 擷取結果 | Section 3 |
| 4 | 庫存彙總儀表板 | Section 4 |
| 5 | AI 庫存分析報表 | Section 5 |

---

## Narration Outline

| 段落 | 時間 | 關鍵訊息 |
|-----------|------|--------------|
| Problem | 0:00–0:45 | 「手動輸入的延遲導致庫存資訊總是過時」 |
| Upload | 0:45–1:30 | 「只要放置掃描檔就能開始自動處理」 |
| OCR | 1:30–2:30 | 「AI 自動辨識單據欄位並結構化」 |
| Analysis | 2:30–3:45 | 「自動彙總進出貨並即時更新庫存」 |
| Report | 3:45–5:00 | 「AI 呈現缺貨風險與訂購建議」 |

---

## Sample Data Requirements

| # | 資料 | 用途 |
|---|--------|------|
| 1 | 進貨單據影像（10 張） | OCR 處理示範 |
| 2 | 出貨單據影像（10 張） | 庫存減算示範 |
| 3 | 手寫單據（3 張） | OCR 精度示範 |
| 4 | 庫存主檔資料 | 比對示範 |

---

## Timeline

### 1 週內可達成

| 任務 | 所需時間 |
|--------|---------|
| 準備範例單據影像 | 2 小時 |
| 管線執行確認 | 2 小時 |
| 畫面擷取取得 | 2 小時 |
| 旁白稿撰寫 | 2 小時 |
| 影片編輯 | 4 小時 |

### Future Enhancements

- 即時單據處理（相機連動）
- WMS 系統整合
- 需求預測模型整合

---

## Technical Notes

| 元件 | 角色 |
|--------------|------|
| Step Functions | 工作流程編排 |
| Lambda (OCR Processor) | 透過 Textract 進行單據文字擷取 |
| Lambda (Field Mapper) | 透過 Bedrock 進行欄位對應 |
| Lambda (Inventory Updater) | 庫存資料更新・彙總 |
| Lambda (Report Generator) | 庫存分析報表生成 |

### 備援方案

| 情境 | 對應 |
|---------|------|
| OCR 精度降低 | 使用預先處理的資料 |
| Bedrock 延遲 | 顯示預先生成的報表 |

---

*本文件為技術簡報用示範影片的製作指南。*

---

## 關於輸出目的地：可透過 OutputDestination 選擇 (Pattern B)

UC12 logistics-ocr 在 2026-05-10 的更新中支援了 `OutputDestination` 參數
（參照 `docs/output-destination-patterns.md`）。

**對象工作負載**：配送單據 OCR / 庫存分析 / 物流報表

**2 種模式**：

### STANDARD_S3（預設，與以往相同）
建立新的 S3 儲存貯體（`${AWS::StackName}-output-${AWS::AccountId}`），
並將 AI 成果物寫入其中。

```bash
aws cloudformation deploy \
  --template-file logistics-ocr/template-deploy.yaml \
  --stack-name fsxn-logistics-ocr-demo \
  --parameter-overrides \
    OutputDestination=STANDARD_S3 \
    ... (其他必要參數)
```

### FSXN_S3AP（"no data movement" 模式）
AI 成果物透過 FSxN S3 Access Point 寫回到與原始資料**相同的 FSx ONTAP 磁碟區**。
SMB/NFS 使用者可以在業務使用的目錄結構內直接瀏覽 AI 成果物。
不會建立標準 S3 儲存貯體。

```bash
aws cloudformation deploy \
  --template-file logistics-ocr/template-deploy.yaml \
  --stack-name fsxn-logistics-ocr-demo \
  --parameter-overrides \
    OutputDestination=FSXN_S3AP \
    OutputS3APPrefix=ai-outputs/ \
    S3AccessPointName=eda-demo-s3ap \
    ... (其他必要參數)
```

**注意事項**：

- 強烈建議指定 `S3AccessPointName`（同時以 Alias 格式與 ARN 格式授予 IAM 權限）
- 超過 5GB 的物件無法透過 FSxN S3AP 處理（AWS 規格），必須使用分段上傳
- AWS 規格上的限制請參照
  [專案 README 的「AWS 規格上的限制與因應對策」段落](../../README.md#aws-仕様上の制約と回避策)
  以及 [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)

---

## 已驗證的 UI/UX 螢幕截圖

與 Phase 7 UC15/16/17 及 UC6/11/14 的示範相同方針，以**終端使用者在日常業務中實際
看到的 UI/UX 畫面**為對象。技術人員視圖（Step Functions 圖表、CloudFormation
堆疊事件等）彙整於 `docs/verification-results-*.md`。

### 此使用案例的驗證狀態

- ✅ **E2E 執行**：Phase 1-6 已確認（參照根目錄 README）
- 📸 **UI/UX 重新拍攝**：✅ 2026-05-10 重新部署驗證時已拍攝（確認 UC12 Step Functions 圖表、Lambda 執行成功）
- 🔄 **重現方法**：參照本文件末尾的「拍攝指南」

### 2026-05-10 重新部署驗證時拍攝（以 UI/UX 為中心）

#### UC12 Step Functions Graph view（SUCCEEDED）

![UC12 Step Functions Graph view（SUCCEEDED）](../../docs/screenshots/masked/uc12-demo/uc12-stepfunctions-graph.png)

Step Functions Graph view 以顏色視覺化各 Lambda / Parallel / Map 狀態的執行狀況，
是終端使用者最重要的畫面。

### 既有螢幕截圖（來自 Phase 1-6 的相關部分）

*（無相關內容。重新驗證時請新拍攝）*

### 重新驗證時的 UI/UX 對象畫面（建議拍攝清單）

- S3 輸出儲存貯體（waybills-ocr/、inventory/、reports/）
- Textract 單據 OCR 結果（跨區域）
- Rekognition 倉庫影像標籤
- 配送彙總報表

### 拍攝指南

1. **事前準備**：
   - `bash scripts/verify_phase7_prerequisites.sh` 確認前提條件（共用 VPC/S3 AP 是否存在）
   - `UC=logistics-ocr bash scripts/package_generic_uc.sh` 打包 Lambda
   - `bash scripts/deploy_generic_ucs.sh UC12` 部署

2. **放置範例資料**：
   - 透過 S3 AP Alias 將範例檔案上傳到 `waybills/` 前綴
   - 啟動 Step Functions `fsxn-logistics-ocr-demo-workflow`（輸入 `{}`）

3. **拍攝**（關閉 CloudShell・終端機，將瀏覽器右上角的使用者名稱塗黑）：
   - S3 輸出儲存貯體 `fsxn-logistics-ocr-demo-output-<account>` 的概覽
   - AI/ML 輸出 JSON 的預覽（參考 `build/preview_*.html` 的格式）
   - SNS 電子郵件通知（如適用）

4. **遮罩處理**：
   - `python3 scripts/mask_uc_demos.py logistics-ocr-demo` 自動遮罩
   - 依照 `docs/screenshots/MASK_GUIDE.md` 進行額外遮罩（如有需要）

5. **清理**：
   - `bash scripts/cleanup_generic_ucs.sh UC12` 刪除
   - VPC Lambda ENI 釋放需 15-30 分鐘（AWS 規格）
